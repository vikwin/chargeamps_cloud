"""Portal-session client for the Charge Amps web API.

The web portal (``my.charge.space``) exposes a separate REST API that
authenticates with the account email/password and a cookie session.  It does
not require an API key.  The API is internal to the portal and may change, so
the API-key client remains the primary interface.
"""

from __future__ import annotations

import copy
import json
import logging
import time
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from types import TracebackType
from typing import Any

import aiohttp

from .const import (
    DEFAULT_RFID_FORMAT,
    DEFAULT_RFID_LENGTH,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
    PLACEHOLDER_RFID,
    normalize_status,
)
from .exceptions import (
    ChargeAmpsApiError,
    ChargeAmpsAuthError,
    ChargeAmpsConnectionError,
    ChargeAmpsError,
    ChargeAmpsForbiddenError,
    ChargeAmpsNotFoundError,
    ChargeAmpsRateLimitError,
)
from .models import (
    ChargePoint,
    ChargePointSettings,
    ChargePointStatus,
    ChargingSession,
    Connector,
    ConnectorSettings,
    ConnectorStatus,
    Measurement,
    RfidTag,
    StartAuth,
    User,
)

_LOGGER = logging.getLogger(__name__)

PORTAL_BASE_URL = "https://my.charge.space/api"
PORTAL_ORIGIN = "https://my.charge.space"
PORTAL_REFERER = "https://my.charge.space/userapp/"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
PAGE_SIZE = 100
DETAIL_CACHE_SECONDS = 5

_DIMMER_MAP = {0: "Off", 8: "Low", 64: "Medium", 255: "High"}
_DIMMER_VALUES = {"Off": 0, "Low": 8, "Medium": 64, "High": 255}

_EV_STATE_MAP = {
    "a1notconnected": "Available",
    "a2notconnected": "Available",
    "b1connected": "Preparing",
    "b2connected": "Preparing",
    "b1nodiode": "Preparing",
    "c1connectedrequestingcharge": "Charging",
    "c2connectedcharging": "Charging",
    "c1waitstop": "Finishing",
    "c2waitlock": "Finishing",
    "drequestingventilation": "Faulted",
    "epilotshortcircuit": "Faulted",
    "fminus12volt": "Faulted",
}


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any, default: bool = False) -> bool:
    return default if value is None else bool(value)


def _datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _connector_status(connector: Mapping[str, Any]) -> str:
    """Map portal connector fields to a canonical connector status."""
    ocpp = connector.get("ocppStatus")
    if ocpp:
        return normalize_status(ocpp)
    ev_state = connector.get("evConnectorState")
    if ev_state:
        mapped = _EV_STATE_MAP.get(str(ev_state).lower())
        if mapped:
            return mapped
    if _bool(connector.get("isCharging")):
        return "Charging"
    if _bool(connector.get("activeSession")):
        return "Connected"
    return "Available"


def _power_w(connector: Mapping[str, Any]) -> float | None:
    total = 0.0
    found = False
    for index in (1, 2, 3):
        current = _float(connector.get(f"current{index}"))
        voltage = _float(connector.get(f"voltage{index}"))
        if current is not None and voltage is not None:
            total += current * voltage
            found = True
    return round(total, 1) if found else None


def _measurements(connector: Mapping[str, Any]) -> list[Measurement]:
    measurements: list[Measurement] = []
    for index in (1, 2, 3):
        current = _float(connector.get(f"current{index}"))
        voltage = _float(connector.get(f"voltage{index}"))
        if current is not None or voltage is not None:
            measurements.append(Measurement(phase=f"L{index}", current=current, voltage=voltage))
    return measurements


def _map_user(data: Mapping[str, Any], tags: Iterable[Mapping[str, Any]] = ()) -> User:
    return User(
        id=str(data.get("id") or ""),
        first_name=_text(data.get("firstName")),
        last_name=_text(data.get("lastName")),
        email=_text(data.get("email")),
        mobile=_text(data.get("mobile")),
        rfid_tags=[
            RfidTag(active=_bool(tag.get("active"), default=True), rfid=_text(tag.get("id")))
            for tag in tags
            if tag.get("id")
        ],
    )


class ChargeAmpsPortalClient:
    """Client using the Charge Amps portal session (no API key)."""

    auth_mode = "portal"

    def __init__(
        self,
        email: str,
        password: str,
        *,
        session: aiohttp.ClientSession | None = None,
        base_url: str = PORTAL_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self._email = email
        self._password = password
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._user_agent = user_agent
        self._session = session
        self._owns_session = session is None
        self._user: User | None = None
        self._token: str | None = None
        self._csrf: str | None = None
        self._csrf_required = False
        self._expires_at: datetime | None = None
        self._detail_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    async def __aenter__(self) -> ChargeAmpsPortalClient:
        try:
            await self.login()
        except Exception:
            await self.close()
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    @property
    def user(self) -> User | None:
        return self._user

    @property
    def api_key(self) -> None:
        return None

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            jar = aiohttp.CookieJar()
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._timeout),
                headers={"User-Agent": self._user_agent},
                cookie_jar=jar,
            )
            self._owns_session = True
        return self._session

    def _headers(self, *, csrf: bool = False) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Origin": PORTAL_ORIGIN,
            "Referer": PORTAL_REFERER,
            "User-Agent": self._user_agent,
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if csrf and self._csrf:
            headers["X-CSRF-TOKEN"] = self._csrf
        return headers

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
        auth: bool = True,
        retry_auth: bool = True,
        retry_csrf: bool = True,
    ) -> Any:
        session = self._ensure_session()
        method_upper = method.upper()
        if auth and self._user is None:
            await self.login()
        if auth and method_upper in UNSAFE_METHODS and self._csrf_required and not self._csrf:
            await self._refresh_csrf()

        url = self._url(path)
        try:
            async with session.request(
                method_upper,
                url,
                headers=self._headers(csrf=method_upper in UNSAFE_METHODS),
                params=params,
                json=json_body,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as response:
                body = await response.text()
                if response.status == 401 and auth and retry_auth:
                    _LOGGER.debug("Portal session expired, logging in again")
                    await self.login()
                    return await self._request(
                        method,
                        path,
                        params=params,
                        json_body=json_body,
                        auth=auth,
                        retry_auth=False,
                        retry_csrf=retry_csrf,
                    )
                if response.status in (400, 403) and auth and method_upper in UNSAFE_METHODS and retry_csrf:
                    _LOGGER.debug("Portal CSRF token rejected, refreshing it")
                    await self._refresh_csrf(force=True)
                    return await self._request(
                        method,
                        path,
                        params=params,
                        json_body=json_body,
                        auth=auth,
                        retry_auth=retry_auth,
                        retry_csrf=False,
                    )
                if response.status >= 400:
                    self._raise_for_status(response, body, method_upper, url)
                if not body:
                    return None
                if "json" in response.headers.get("Content-Type", ""):
                    return json.loads(body)
                return body
        except aiohttp.ClientError as err:
            raise ChargeAmpsConnectionError(f"Could not reach the Charge Amps portal: {err}") from err
        except TimeoutError as err:
            raise ChargeAmpsConnectionError("The Charge Amps portal request timed out") from err

    def _raise_for_status(self, response: aiohttp.ClientResponse, body: str, method: str, url: str) -> None:
        message = body.strip()
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            payload = None
        if isinstance(payload, Mapping):
            message = str(payload.get("detail") or payload.get("title") or payload.get("message") or message)
        if response.status == 401:
            raise ChargeAmpsAuthError(message or "Authentication failed")
        if response.status == 403:
            raise ChargeAmpsForbiddenError(message or "Forbidden")
        if response.status == 404:
            raise ChargeAmpsNotFoundError(message or "Not found")
        if response.status == 429:
            retry_after = response.headers.get("Retry-After")
            raise ChargeAmpsRateLimitError(
                message or "Rate limit exceeded",
                retry_after=float(retry_after) if retry_after else None,
            )
        raise ChargeAmpsApiError(response.status, message, method=method, url=url)

    async def _refresh_csrf(self, *, force: bool = False) -> None:
        if self._csrf and not force:
            return
        session = self._ensure_session()
        url = self._url("csrf/handshake")
        async with session.get(
            url,
            headers=self._headers(),
            timeout=aiohttp.ClientTimeout(total=self._timeout),
        ) as response:
            body = await response.text()
            if response.status == 401:
                self._user = None
                raise ChargeAmpsAuthError("The portal session expired")
            if response.status >= 400:
                self._raise_for_status(response, body, "GET", url)
            token = response.headers.get("X-CSRF-TOKEN") or response.headers.get("x-csrf-token")
            if not token and body:
                try:
                    payload = json.loads(body)
                except ValueError:
                    payload = None
                if isinstance(payload, Mapping):
                    token = payload.get("token") or payload.get("csrfToken")
            if not token:
                raise ChargeAmpsAuthError("The portal did not return a CSRF token")
            self._csrf = str(token)

    async def login(self) -> User:
        """Create a portal session and load the current user."""
        session = self._ensure_session()
        session.cookie_jar.clear()
        self._user = None
        self._token = None
        self._csrf = None
        self._csrf_required = False
        payload = await self._request(
            "POST",
            "auth/login",
            json_body={"email": self._email, "password": self._password},
            auth=False,
            retry_auth=False,
        )
        current: Mapping[str, Any] | None = None
        token = None
        if isinstance(payload, Mapping) and (payload.get("user") or payload.get("token")):
            current = payload
            token = payload.get("token")
        if current is None:
            current_payload = await self._request(
                "GET",
                "auth/current",
                auth=False,
                retry_auth=False,
            )
            if isinstance(current_payload, Mapping):
                current = current_payload
                token = current_payload.get("token")
        if not current or not current.get("user"):
            raise ChargeAmpsAuthError("The portal login did not return a user")
        self._user = _map_user(current["user"])
        self._token = str(token) if token else None
        # A bearer-token session does not require CSRF.  Cookie-based sessions
        # announce csrfRequired=true; the handshake is then performed lazily.
        self._csrf_required = _bool(current.get("csrfRequired"), default=False)
        self._expires_at = _datetime(current.get("expiresAtUtc"))
        if self._csrf_required:
            await self._refresh_csrf(force=True)
        _LOGGER.debug("Portal login successful for %s", self._user.email)
        return self._user

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    async def _detail(self, charge_point_id: str, *, fresh: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        cached = self._detail_cache.get(charge_point_id)
        if not fresh and cached and now - cached[0] < DETAIL_CACHE_SECONDS:
            return copy.deepcopy(cached[1])
        payload = await self._request("GET", f"chargepoints/{charge_point_id}")
        if not isinstance(payload, Mapping):
            raise ChargeAmpsNotFoundError(f"Charge point {charge_point_id} was not returned")
        raw = dict(payload)
        self._detail_cache[charge_point_id] = (now, raw)
        return copy.deepcopy(raw)

    def _invalidate(self, charge_point_id: str | None = None) -> None:
        if charge_point_id is None:
            self._detail_cache.clear()
        else:
            self._detail_cache.pop(charge_point_id, None)

    def _map_chargepoint(self, raw: Mapping[str, Any]) -> ChargePoint:
        connector_models = []
        raw_connectors = [item for item in raw.get("connectors") or [] if isinstance(item, Mapping)]
        for connector in raw_connectors:
            connector_models.append(
                Connector(
                    connector_id=_int(connector.get("connectorId")) or 0,
                    charge_point_id=_text(raw.get("id")),
                    type=_text(connector.get("connectorFunctionType")),
                )
            )
        max_current = next(
            (_float(item.get("userCurrent")) for item in raw_connectors if item.get("userCurrent") is not None),
            None,
        )
        installation_current = next(
            (
                _int(item.get("installationCurrent"))
                for item in raw_connectors
                if item.get("installationCurrent") is not None
            ),
            None,
        )
        settings = ChargePointSettings(
            id=str(raw.get("id") or ""),
            dimmer=_DIMMER_MAP.get(_int(raw.get("dimmer")) or 0, "Off"),
            down_light=None if raw.get("downLight") is None else _bool(raw.get("downLight")),
            max_current=max_current,
            installation_current=installation_current,
        )
        return ChargePoint(
            id=str(raw.get("id") or ""),
            name=_text(raw.get("name")),
            type=_text(raw.get("productName") or raw.get("productType")),
            is_loadbalanced=bool(raw.get("loadBalancerGroupId") or raw.get("inActiveLoadBalancerGroup")),
            firmware_version=_text(raw.get("installedFirmwareVersion")),
            hardware_version=_text(raw.get("hardwareVersion")),
            owner_read_only=_bool(raw.get("ownerReadOnly")),
            ocpp_version="OCPP" if _bool(raw.get("isOcpp")) else "CAPI",
            settings=settings,
            connectors=connector_models,
        )

    async def get_owned_chargepoints(self) -> list[ChargePoint]:
        payload = await self._request("GET", "users/chargepoints/owned")
        if not isinstance(payload, list):
            return []
        result: list[ChargePoint] = []
        for item in payload:
            if not isinstance(item, Mapping):
                continue
            raw = dict(item)
            chargepoint_id = str(raw.get("id") or "")
            if not raw.get("connectors"):
                try:
                    raw = await self._detail(chargepoint_id)
                except ChargeAmpsError:
                    _LOGGER.debug("Could not load detail for charge point %s", chargepoint_id)
            elif chargepoint_id:
                # The list response contains more connectors than the detail
                # response on some firmware versions, and it is fresh enough
                # for the subsequent status/settings calls in the same poll.
                self._detail_cache[chargepoint_id] = (time.monotonic(), raw)
            result.append(self._map_chargepoint(raw))
        return result

    async def get_chargepoints(self) -> list[ChargePoint]:
        return await self.get_owned_chargepoints()

    async def get_chargepoint(self, charge_point_id: str) -> ChargePoint:
        return self._map_chargepoint(await self._detail(charge_point_id))

    async def get_chargepoint_status(self, charge_point_id: str) -> ChargePointStatus:
        raw = await self._detail(charge_point_id)
        overall = str(raw.get("chargePointStatus") or ("Offline" if raw.get("offlineSince") else "Online"))
        connector_statuses: list[ConnectorStatus] = []
        for connector in raw.get("connectors") or []:
            if not isinstance(connector, Mapping):
                continue
            power = _power_w(connector)
            connector_statuses.append(
                ConnectorStatus(
                    charge_point_id=charge_point_id,
                    connector_id=_int(connector.get("connectorId")) or 0,
                    status=_connector_status(connector),
                    total_consumption_kwh=_float(connector.get("totalConsumptionKwh")) or 0.0,
                    charging_power_kw=power / 1000 if power is not None else None,
                    session_type=_text(connector.get("sessionType")),
                    measurements=_measurements(connector),
                )
            )
        return ChargePointStatus(
            id=charge_point_id,
            status="Offline" if overall == "Offline" else "Online",
            connector_statuses=connector_statuses,
        )

    async def get_chargepoint_settings(self, charge_point_id: str) -> ChargePointSettings:
        raw = await self._detail(charge_point_id)
        connectors = [item for item in raw.get("connectors") or [] if isinstance(item, Mapping)]
        return ChargePointSettings(
            id=charge_point_id,
            dimmer=_DIMMER_MAP.get(_int(raw.get("dimmer")) or 0, "Off"),
            down_light=None if raw.get("downLight") is None else _bool(raw.get("downLight")),
            max_current=next(
                (_float(item.get("userCurrent")) for item in connectors if item.get("userCurrent") is not None),
                None,
            ),
            installation_current=next(
                (
                    _int(item.get("installationCurrent"))
                    for item in connectors
                    if item.get("installationCurrent") is not None
                ),
                None,
            ),
        )

    async def set_chargepoint_settings(self, settings: ChargePointSettings) -> None:
        raw = await self._detail(settings.id, fresh=True)
        if settings.down_light is not None:
            raw["downLight"] = settings.down_light
        raw["dimmer"] = _DIMMER_VALUES.get(settings.dimmer, 0)
        await self._request("PUT", "chargepoints", json_body=raw)
        self._invalidate(settings.id)

    async def get_connector_settings(self, charge_point_id: str, connector_id: int) -> ConnectorSettings:
        raw = await self._detail(charge_point_id)
        connector = next(
            (
                item
                for item in raw.get("connectors") or []
                if isinstance(item, Mapping) and _int(item.get("connectorId")) == connector_id
            ),
            {},
        )
        return ConnectorSettings(
            charge_point_id=charge_point_id,
            connector_id=connector_id,
            mode=str(connector.get("mode") or "Off"),
            rfid_lock=_bool(connector.get("nfcLocked")),
            cable_lock=_bool(connector.get("cableLocked")),
            max_current=_float(connector.get("userCurrent") or connector.get("installationCurrent")),
            installation_current=_int(connector.get("installationCurrent")),
        )

    async def set_connector_settings(self, settings: ConnectorSettings) -> None:
        if not settings.charge_point_id:
            raise ValueError("ConnectorSettings.charge_point_id is required")
        cached = self._detail_cache.get(settings.charge_point_id)
        raw = await self._detail(settings.charge_point_id, fresh=True)

        def has_connector(data: Mapping[str, Any]) -> bool:
            return any(
                isinstance(item, Mapping) and _int(item.get("connectorId")) == settings.connector_id
                for item in data.get("connectors") or []
            )

        if not has_connector(raw) and cached is not None:
            # The detail endpoint omits the Schuko connector on some models;
            # fall back to the owned-chargepoints payload which includes it.
            raw = copy.deepcopy(cached[1])
        for connector in raw.get("connectors") or []:
            if not isinstance(connector, Mapping):
                continue
            if _int(connector.get("connectorId")) != settings.connector_id:
                continue
            connector["mode"] = settings.mode
            connector["nfcLocked"] = settings.rfid_lock
            connector["cableLocked"] = settings.cable_lock
            if settings.max_current is not None:
                connector["userCurrent"] = settings.max_current
            break
        else:
            raise ChargeAmpsNotFoundError(f"Connector {settings.connector_id} not found on {settings.charge_point_id}")
        await self._request("PUT", "chargepoints", json_body=raw)
        self._invalidate(settings.charge_point_id)

    async def reboot(self, charge_point_id: str) -> None:
        await self._request("PUT", f"chargepoints/{charge_point_id}/reboot")
        self._invalidate(charge_point_id)

    # ------------------------------------------------------------------
    # Charging sessions
    # ------------------------------------------------------------------
    def _map_session(self, data: Mapping[str, Any]) -> ChargingSession:
        return ChargingSession(
            id=_int(data.get("id")) or 0,
            charge_point_id=_text(data.get("chargePointId")),
            connector_id=_int(data.get("connectorId")) or 0,
            user_id=_text(data.get("userId")),
            rfid=_text(data.get("nfcUid")),
            session_type=_text(data.get("sessionType")),
            start_time=_datetime(data.get("startTime")),
            end_time=_datetime(data.get("endTime")),
            total_consumption_kwh=_float(data.get("totalConsumptionKwh")) or 0.0,
            external_transaction_id=_text(data.get("ocppTransactionId")),
        )

    async def get_charging_sessions(
        self,
        charge_point_id: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[ChargingSession]:
        # The portal uses pagination; start/end filtering is done client-side
        # because the endpoint does not expose time bounds.
        sessions: list[ChargingSession] = []
        offset = 0
        while True:
            payload = await self._request(
                "GET",
                f"chargepoints/{charge_point_id}/chargingsessions",
                params={"Offset": offset, "NoOfItems": PAGE_SIZE, "filterZero": "true"},
            )
            if not isinstance(payload, Mapping):
                break
            page = payload.get("sessions") or []
            sessions.extend(self._map_session(item) for item in page if isinstance(item, Mapping))
            offset += len(page)
            total = _int(payload.get("totalCount")) or 0
            if not page or offset >= total:
                break
        if start_time is not None:
            sessions = [session for session in sessions if session.start_time and session.start_time >= start_time]
        if end_time is not None:
            sessions = [session for session in sessions if session.start_time and session.start_time <= end_time]
        return sessions

    async def get_charging_session(self, charge_point_id: str, session_id: int) -> ChargingSession:
        # The portal has no GET endpoint for a single session, so resolve it
        # from the charge point's session history.
        for session in await self.get_charging_sessions(charge_point_id):
            if session.id == session_id:
                return session
        raise ChargeAmpsNotFoundError(f"Session {session_id} was not found")

    async def get_connector_sessions(self, charge_point_id: str, connector_id: int) -> list[ChargingSession]:
        sessions = await self.get_charging_sessions(charge_point_id)
        return [session for session in sessions if session.connector_id == connector_id]

    # ------------------------------------------------------------------
    # Charging control
    # ------------------------------------------------------------------
    async def _start_tag(self, charge_point_id: str, connector_id: int) -> str | None:
        raw = await self._detail(charge_point_id)
        connector = next(
            (
                item
                for item in raw.get("connectors") or []
                if isinstance(item, Mapping) and _int(item.get("connectorId")) == connector_id
            ),
            {},
        )
        default = _text(connector.get("defaultNfcTagId"))
        if not _bool(connector.get("nfcLocked")) and default and default != PLACEHOLDER_RFID:
            return default
        try:
            tags = await self._request(
                "GET",
                f"chargepoints/{charge_point_id}/{connector_id}/remotestart/tags",
            )
        except ChargeAmpsError:
            tags = None
        if isinstance(tags, list):
            for item in tags:
                if isinstance(item, Mapping) and item.get("id") and item.get("id") != PLACEHOLDER_RFID:
                    return str(item["id"])
        if default and default != PLACEHOLDER_RFID:
            return default
        fallback = await self.get_default_rfid(allow_placeholder=False)
        return fallback.rfid if fallback else None

    async def remote_start(
        self,
        charge_point_id: str,
        connector_id: int,
        *,
        rfid: str | None = None,
        rfid_format: str | None = None,
        rfid_length: int | None = None,
        external_transaction_id: str | None = None,
        allow_placeholder_tag: bool = True,
    ) -> StartAuth:
        del rfid_format, rfid_length, external_transaction_id, allow_placeholder_tag
        tag = rfid or await self._start_tag(charge_point_id, connector_id)
        params = {"rfidTag": tag} if tag else None
        await self._request(
            "PUT",
            f"chargepoints/{charge_point_id}/{connector_id}/remotestart",
            params=params,
        )
        self._invalidate(charge_point_id)
        return StartAuth(rfid=tag or "", rfid_format=DEFAULT_RFID_FORMAT, rfid_length=DEFAULT_RFID_LENGTH)

    async def remote_stop(self, charge_point_id: str, connector_id: int) -> None:
        await self._request(
            "PUT",
            f"chargepoints/{charge_point_id}/{connector_id}/remotestop",
        )
        self._invalidate(charge_point_id)

    # ------------------------------------------------------------------
    # Users and RFID
    # ------------------------------------------------------------------
    async def get_user(self, user_id: str) -> User:
        payload = await self._request("GET", f"users/{user_id}")
        return _map_user(payload if isinstance(payload, Mapping) else {})

    async def get_current_user(self) -> User:
        if self._user is None:
            raise ChargeAmpsAuthError("Not logged in")
        return self._user

    async def get_rfids(self) -> list[RfidTag]:
        try:
            payload = await self._request("GET", "users/nfctags/own")
        except ChargeAmpsError:
            return []
        if not isinstance(payload, list):
            return []
        return [
            RfidTag(active=_bool(item.get("active"), default=True), rfid=_text(item.get("id")))
            for item in payload
            if isinstance(item, Mapping) and item.get("id")
        ]

    async def get_default_rfid(self, *, allow_placeholder: bool = True) -> RfidTag | None:
        del allow_placeholder
        tags = await self.get_rfids()
        for tag in tags:
            if tag.active and tag.rfid:
                return tag
        return tags[0] if tags else None

    # ------------------------------------------------------------------
    # Unsupported API-key endpoints
    # ------------------------------------------------------------------
    async def get_organisations(self) -> list[Any]:
        return []

    async def enable_callbacks(self, charge_point_ids: Iterable[str]) -> None:
        raise NotImplementedError("Callbacks are not available in portal mode")

    async def disable_callbacks(self, charge_point_ids: Iterable[str]) -> None:
        raise NotImplementedError("Callbacks are not available in portal mode")

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Escape hatch for portal endpoints."""
        return await self._request(method, path, **kwargs)
