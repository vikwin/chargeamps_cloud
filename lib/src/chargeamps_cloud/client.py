"""Asynchronous client for the Charge Amps Cloud API (eAPI v5)."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from collections.abc import Iterable, Mapping
from datetime import datetime
from types import TracebackType
from typing import Any

import aiohttp

from .const import (
    API_BASE_URL,
    API_VERSION,
    DEFAULT_RFID_FORMAT,
    DEFAULT_RFID_LENGTH,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
    PLACEHOLDER_RFID,
    TOKEN_REFRESH_MARGIN,
)
from .exceptions import (
    ChargeAmpsApiError,
    ChargeAmpsAuthError,
    ChargeAmpsConnectionError,
    ChargeAmpsForbiddenError,
    ChargeAmpsNotFoundError,
    ChargeAmpsRateLimitError,
)
from .models import (
    ChargePoint,
    ChargePointSettings,
    ChargePointStatus,
    ChargingSession,
    ConnectorSettings,
    Organisation,
    Partner,
    RfidTag,
    Schedule,
    ScheduleOverrideStatus,
    StartAuth,
    User,
)

_LOGGER = logging.getLogger(__name__)


def _decode_jwt_exp(token: str) -> int | None:
    """Read ``exp`` from a JWT without verifying it (the API signed it)."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError, json.JSONDecodeError):
        return None
    exp = data.get("exp")
    return int(exp) if isinstance(exp, (int, float)) else None


class ChargeAmpsClient:
    """Client for the Charge Amps Cloud API.

    The client authenticates with the account email, password, and an API key.
    Tokens are refreshed automatically and a lost token results in one
    re-login attempt.
    """

    def __init__(
        self,
        email: str,
        password: str,
        api_key: str,
        *,
        session: aiohttp.ClientSession | None = None,
        base_url: str = API_BASE_URL,
        api_version: str = API_VERSION,
        organisation_id: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        if not api_key:
            raise ValueError("An API key is required")
        self._email = email
        self._password = password
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._api_version = api_version
        self._organisation_id = organisation_id
        self._timeout = timeout
        self._user_agent = user_agent
        self._session = session
        self._owns_session = session is None
        self._token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires_at: float = 0
        self._token_lock = asyncio.Lock()
        self._user: User | None = None
        self._user_tags_loaded = False
        self._discovered_organisation_ids: list[str] | None = None
        self._default_rfid: RfidTag | None = None

    async def __aenter__(self) -> ChargeAmpsClient:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._timeout),
                headers={"User-Agent": self._user_agent},
            )
            self._owns_session = True
        await self.login()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the HTTP session if the client created it."""
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    @property
    def user(self) -> User | None:
        """The user returned by the last successful login."""
        return self._user

    @property
    def api_key(self) -> str:
        return self._api_key

    @property
    def base_url(self) -> str:
        return self._base_url

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    async def login(self) -> User:
        """Authenticate and store the bearer and refresh tokens."""
        payload = await self._request(
            "POST",
            "auth/login",
            json_body={"email": self._email, "password": self._password},
            auth=False,
            retry_auth=False,
        )
        if not isinstance(payload, Mapping):
            raise ChargeAmpsAuthError("Login returned an unexpected response")
        token = payload.get("token")
        refresh_token = payload.get("refreshToken")
        if not token:
            message = payload.get("message") or "Login failed"
            raise ChargeAmpsAuthError(str(message))
        self._set_token(str(token), str(refresh_token) if refresh_token else None)
        user = payload.get("user")
        self._user = User.from_api(user) if isinstance(user, Mapping) else None
        self._user_tags_loaded = bool(self._user and self._user.rfid_tags)
        self._default_rfid = None
        _LOGGER.debug("Logged in as %s", self._user.email if self._user else self._email)
        return self._user or User(id="", email=self._email)

    async def refresh(self) -> None:
        """Refresh the bearer token using the stored refresh token."""
        if not self._token or not self._refresh_token:
            raise ChargeAmpsAuthError("No refresh token available")
        payload = await self._request(
            "POST",
            "auth/refreshtoken",
            json_body={"token": self._token, "refreshToken": self._refresh_token},
            auth=False,
            retry_auth=False,
        )
        if not isinstance(payload, Mapping) or not payload.get("token"):
            raise ChargeAmpsAuthError("Token refresh failed")
        self._set_token(
            str(payload["token"]),
            str(payload["refreshToken"]) if payload.get("refreshToken") else self._refresh_token,
        )
        _LOGGER.debug("Refreshed API token")

    def _set_token(self, token: str, refresh_token: str | None) -> None:
        self._token = token
        self._refresh_token = refresh_token
        exp = _decode_jwt_exp(token)
        self._token_expires_at = float(exp) if exp else time.time() + 110 * 60

    async def _ensure_token(self) -> None:
        if self._token and self._token_expires_at - TOKEN_REFRESH_MARGIN > time.time():
            return
        async with self._token_lock:
            if self._token and self._token_expires_at - TOKEN_REFRESH_MARGIN > time.time():
                return
            if self._token and self._refresh_token:
                try:
                    await self.refresh()
                    return
                except ChargeAmpsAuthError:
                    _LOGGER.debug("Token refresh rejected, logging in again")
                self._token = None
                self._refresh_token = None
            await self.login()

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------
    def _url(self, path: str) -> str:
        return f"{self._base_url}/api/{self._api_version}/{path.lstrip('/')}"

    def _headers(self, authenticated: bool) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": self._user_agent,
            "apiKey": self._api_key,
        }
        if authenticated and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
        data: Any = None,
        auth: bool = True,
        retry_auth: bool = True,
        expected_status: Iterable[int] = (),
    ) -> Any:
        """Perform an HTTP request and return decoded JSON (or text)."""
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._timeout),
                headers={"User-Agent": self._user_agent},
            )
            self._owns_session = True
        if auth:
            await self._ensure_token()

        url = self._url(path)
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers(auth),
                params=params,
                json=json_body,
                data=data,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as response:
                body = await response.text()
                if response.status == 401 and auth and retry_auth:
                    _LOGGER.debug("API returned 401, forcing a new login")
                    self._token = None
                    self._refresh_token = None
                    await self._ensure_token()
                    return await self._request(
                        method,
                        path,
                        params=params,
                        json_body=json_body,
                        data=data,
                        auth=auth,
                        retry_auth=False,
                        expected_status=expected_status,
                    )
                if response.status >= 400:
                    if response.status in expected_status:
                        return None
                    self._raise_for_status(response, body, method, url)
                if not body:
                    return None
                content_type = response.headers.get("Content-Type", "")
                if "json" in content_type:
                    return json.loads(body)
                return body
        except aiohttp.ClientError as err:
            raise ChargeAmpsConnectionError(f"Could not reach the Charge Amps API: {err}") from err
        except TimeoutError as err:
            raise ChargeAmpsConnectionError("The Charge Amps API request timed out") from err

    def _raise_for_status(
        self,
        response: aiohttp.ClientResponse,
        body: str,
        method: str,
        url: str,
    ) -> None:
        message = body.strip()
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            payload = None
        if isinstance(payload, Mapping):
            message = str(payload.get("message") or payload.get("error") or message)
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

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Escape hatch for endpoints the client does not model."""
        return await self._request(method, path, **kwargs)

    # ------------------------------------------------------------------
    # User and RFID
    # ------------------------------------------------------------------
    async def get_user(self, user_id: str) -> User:
        payload = await self._request("GET", f"users/{user_id}")
        user = User.from_api(payload if isinstance(payload, Mapping) else {})
        if self._user and self._user.id == user.id:
            self._user = user
            self._user_tags_loaded = True
        return user

    async def get_current_user(self) -> User:
        if self._user is None:
            raise ChargeAmpsAuthError("Not logged in")
        return await self.get_user(self._user.id) if self._user.id else self._user

    async def get_default_rfid(self, *, allow_placeholder: bool = True) -> RfidTag | None:
        """Return the first active RFID tag on the account.

        If the account has no tag, a placeholder tag is returned when
        ``allow_placeholder`` is true; only use that on chargers which accept it.
        """
        if self._default_rfid is not None:
            return self._default_rfid
        user = self._user
        if user is None:
            user = await self.get_current_user()
        if user and not user.rfid_tags and user.id and not self._user_tags_loaded:
            user = await self.get_user(user.id)
        tag = user.first_active_tag() if user else None
        if tag is None and allow_placeholder:
            tag = RfidTag(active=True, rfid=PLACEHOLDER_RFID)
        self._default_rfid = tag
        return tag

    # ------------------------------------------------------------------
    # Charge points
    # ------------------------------------------------------------------
    async def get_owned_chargepoints(self) -> list[ChargePoint]:
        payload = await self._request("GET", "chargepoints/owned")
        return [ChargePoint.from_api(item) for item in payload or [] if isinstance(item, Mapping)]

    async def get_organisation_chargepoints(self, organisation_id: str) -> list[ChargePoint]:
        payload = await self._request("GET", f"organisations/{organisation_id}/chargepoints")
        return [ChargePoint.from_api(item) for item in payload or [] if isinstance(item, Mapping)]

    async def get_organisations(self) -> list[Organisation]:
        try:
            payload = await self._request(
                "GET",
                "organisations",
                expected_status=(401, 403, 404),
                retry_auth=False,
            )
        except (ChargeAmpsAuthError, ChargeAmpsForbiddenError, ChargeAmpsNotFoundError):
            return []
        return [Organisation.from_api(item) for item in payload or [] if isinstance(item, Mapping)]

    async def get_chargepoints(self) -> list[ChargePoint]:
        """Return all charge points the account can see."""
        if self._organisation_id:
            return await self.get_organisation_chargepoints(self._organisation_id)

        chargepoints = await self.get_owned_chargepoints()
        if chargepoints:
            return chargepoints

        if self._discovered_organisation_ids is None:
            organisations = await self.get_organisations()
            self._discovered_organisation_ids = [organisation.id for organisation in organisations]

        by_id: dict[str, ChargePoint] = {}
        for organisation_id in self._discovered_organisation_ids:
            try:
                found = await self.get_organisation_chargepoints(organisation_id)
            except (ChargeAmpsAuthError, ChargeAmpsForbiddenError, ChargeAmpsNotFoundError):
                continue
            for chargepoint in found:
                by_id.setdefault(chargepoint.id, chargepoint)
        return list(by_id.values())

    async def get_chargepoint(self, charge_point_id: str) -> ChargePoint:
        payload = await self._request("GET", f"chargepoints/{charge_point_id}")
        return ChargePoint.from_api(payload if isinstance(payload, Mapping) else {})

    async def get_chargepoint_partner(self, charge_point_id: str) -> Partner:
        payload = await self._request("GET", f"chargepoints/{charge_point_id}/partner")
        return Partner.from_api(payload if isinstance(payload, Mapping) else {})

    async def get_chargepoint_status(self, charge_point_id: str) -> ChargePointStatus:
        payload = await self._request("GET", f"chargepoints/{charge_point_id}/status")
        return ChargePointStatus.from_api(payload if isinstance(payload, Mapping) else {})

    async def get_chargepoint_settings(self, charge_point_id: str) -> ChargePointSettings:
        payload = await self._request("GET", f"chargepoints/{charge_point_id}/settings")
        return ChargePointSettings.from_api(payload if isinstance(payload, Mapping) else {})

    async def set_chargepoint_settings(self, settings: ChargePointSettings) -> None:
        await self._request(
            "PUT",
            f"chargepoints/{settings.id}/settings",
            json_body=settings.to_api(),
        )

    async def get_connector_settings(self, charge_point_id: str, connector_id: int) -> ConnectorSettings:
        payload = await self._request(
            "GET",
            f"chargepoints/{charge_point_id}/connectors/{connector_id}/settings",
        )
        return ConnectorSettings.from_api(payload if isinstance(payload, Mapping) else {})

    async def set_connector_settings(self, settings: ConnectorSettings) -> None:
        if not settings.charge_point_id:
            raise ValueError("ConnectorSettings.charge_point_id is required")
        await self._request(
            "PUT",
            f"chargepoints/{settings.charge_point_id}/connectors/{settings.connector_id}/settings",
            json_body=settings.to_api(),
        )

    async def reboot(self, charge_point_id: str) -> None:
        await self._request("PUT", f"chargepoints/{charge_point_id}/reboot", json_body={})

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
        """Start charging remotely.

        If no tag is supplied, the first active tag on the account is used.
        """
        tag_text = rfid
        if tag_text is None:
            tag = await self.get_default_rfid(allow_placeholder=allow_placeholder_tag)
            if tag is None or not tag.rfid:
                raise ChargeAmpsAuthError("No RFID tag is configured on this account")
            tag_text = tag.rfid
        start_auth = StartAuth(
            rfid=tag_text,
            rfid_format=rfid_format or DEFAULT_RFID_FORMAT,
            rfid_length=rfid_length or DEFAULT_RFID_LENGTH,
            external_transaction_id=external_transaction_id,
        )
        await self._request(
            "PUT",
            f"chargepoints/{charge_point_id}/connectors/{connector_id}/remotestart",
            json_body=start_auth.to_api(),
        )
        return start_auth

    async def remote_stop(self, charge_point_id: str, connector_id: int) -> None:
        await self._request(
            "PUT",
            f"chargepoints/{charge_point_id}/connectors/{connector_id}/remotestop",
            json_body={},
        )

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------
    async def get_charging_sessions(
        self,
        charge_point_id: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[ChargingSession]:
        params: dict[str, Any] = {}
        if start_time:
            params["startTime"] = start_time.isoformat()
        if end_time:
            params["endTime"] = end_time.isoformat()
        payload = await self._request(
            "GET",
            f"chargepoints/{charge_point_id}/chargingsessions",
            params=params or None,
        )
        return [ChargingSession.from_api(item) for item in payload or [] if isinstance(item, Mapping)]

    async def get_charging_session(self, charge_point_id: str, session_id: int) -> ChargingSession:
        payload = await self._request(
            "GET",
            f"chargepoints/{charge_point_id}/chargingsessions/{session_id}",
        )
        return ChargingSession.from_api(payload if isinstance(payload, Mapping) else {})

    async def get_connector_sessions(self, charge_point_id: str, connector_id: int) -> list[ChargingSession]:
        payload = await self._request(
            "GET",
            f"chargepoints/{charge_point_id}/connectors/{connector_id}/chargingsessions",
        )
        return [ChargingSession.from_api(item) for item in payload or [] if isinstance(item, Mapping)]

    # ------------------------------------------------------------------
    # Schedules (CAPI only on v5)
    # ------------------------------------------------------------------
    async def get_schedules(self, charge_point_id: str) -> list[Schedule]:
        payload = await self._request("GET", f"chargepoints/{charge_point_id}/schedules")
        return [Schedule.from_api(item) for item in payload or [] if isinstance(item, Mapping)]

    async def create_schedule(self, schedule: Schedule) -> Schedule:
        payload = await self._request(
            "POST",
            f"chargepoints/{schedule.charge_point_id}/schedules",
            json_body=schedule.to_api(include_id=False),
        )
        return Schedule.from_api(payload if isinstance(payload, Mapping) else {})

    async def update_schedule(self, schedule: Schedule) -> None:
        await self._request(
            "PUT",
            f"chargepoints/{schedule.charge_point_id}/schedules",
            json_body=schedule.to_api(),
        )

    async def get_schedule(self, charge_point_id: str, schedule_id: int) -> Schedule:
        payload = await self._request(
            "GET",
            f"chargepoints/{charge_point_id}/schedules/{schedule_id}",
        )
        return Schedule.from_api(payload if isinstance(payload, Mapping) else {})

    async def delete_schedule(self, charge_point_id: str, schedule_id: int) -> None:
        await self._request("DELETE", f"chargepoints/{charge_point_id}/schedules/{schedule_id}")

    async def get_schedule_override_status(self, charge_point_id: str) -> list[ScheduleOverrideStatus]:
        payload = await self._request(
            "GET",
            f"chargepoints/{charge_point_id}/schedule/override/status",
        )
        return [ScheduleOverrideStatus.from_api(item) for item in payload or [] if isinstance(item, Mapping)]

    async def override_schedule(self, charge_point_id: str, connector_id: int) -> None:
        await self._request(
            "PUT",
            f"chargepoints/{charge_point_id}/connectors/{connector_id}/schedule/override",
            json_body={},
        )

    # ------------------------------------------------------------------
    # Callbacks and registration
    # ------------------------------------------------------------------
    async def enable_callbacks(self, charge_point_ids: Iterable[str]) -> None:
        await self._request(
            "PUT",
            "chargepoints/callbacks/enable",
            json_body={"chargePointIds": list(charge_point_ids)},
        )

    async def disable_callbacks(self, charge_point_ids: Iterable[str]) -> None:
        await self._request(
            "PUT",
            "chargepoints/callbacks/disable",
            json_body={"chargePointIds": list(charge_point_ids)},
        )

    async def register_chargepoint(
        self,
        charge_point_id: str,
        password: str,
        *,
        name: str | None = None,
    ) -> None:
        body: dict[str, Any] = {"chargePointId": charge_point_id, "password": password}
        if name:
            body["chargePointName"] = name
        await self._request("PUT", f"chargepoints/{charge_point_id}/register", json_body=body)

    async def unregister_chargepoint(self, charge_point_id: str, password: str) -> None:
        await self._request(
            "PUT",
            f"chargepoints/{charge_point_id}/unregister",
            json_body={"chargePointId": charge_point_id, "password": password},
        )

    # ------------------------------------------------------------------
    # Organisations and partners
    # ------------------------------------------------------------------
    async def get_organisation(self, organisation_id: str) -> Organisation:
        payload = await self._request("GET", f"organisations/{organisation_id}")
        return Organisation.from_api(payload if isinstance(payload, Mapping) else {})

    async def get_organisation_statuses(self, organisation_id: str) -> list[ChargePointStatus]:
        payload = await self._request("GET", f"organisations/{organisation_id}/chargepoints/statuses")
        return [ChargePointStatus.from_api(item) for item in payload or [] if isinstance(item, Mapping)]

    async def get_organisation_sessions(
        self,
        organisation_id: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[ChargingSession]:
        params: dict[str, Any] = {}
        if start_time:
            params["startTime"] = start_time.isoformat()
        if end_time:
            params["endTime"] = end_time.isoformat()
        payload = await self._request(
            "GET",
            f"organisations/{organisation_id}/chargingsessions",
            params=params or None,
        )
        return [ChargingSession.from_api(item) for item in payload or [] if isinstance(item, Mapping)]

    async def get_organisation_users(self, organisation_id: str) -> list[User]:
        payload = await self._request("GET", f"organisations/{organisation_id}/users")
        return [User.from_api(item) for item in payload or [] if isinstance(item, Mapping)]

    async def get_organisation_user(self, organisation_id: str, user_id: str) -> User:
        payload = await self._request("GET", f"organisations/{organisation_id}/users/{user_id}")
        return User.from_api(payload if isinstance(payload, Mapping) else {})

    async def create_organisation_user(self, organisation_id: str, user: Mapping[str, Any]) -> User:
        payload = await self._request(
            "POST",
            f"organisations/{organisation_id}/users",
            json_body=dict(user),
        )
        return User.from_api(payload if isinstance(payload, Mapping) else {})

    async def get_organisation_rfids(self, organisation_id: str) -> list[RfidTag]:
        payload = await self._request("GET", f"organisations/{organisation_id}/rfids")
        return [RfidTag.from_api(item) for item in payload or [] if isinstance(item, Mapping)]

    async def create_organisation_rfid(self, organisation_id: str, tag: RfidTag) -> None:
        await self._request(
            "POST",
            f"organisations/{organisation_id}/rfids",
            json_body={"rfid": tag.rfid, "rfidFormat": "Hex"},
        )

    async def revoke_organisation_rfid(self, organisation_id: str, rfid: str) -> None:
        await self._request("PUT", f"organisations/{organisation_id}/rfids/{rfid}/revoke", json_body={})

    async def get_partner_rfids(self, partner_id: str) -> list[RfidTag]:
        payload = await self._request("GET", f"partners/{partner_id}/rfids")
        return [RfidTag.from_api(item) for item in payload or [] if isinstance(item, Mapping)]

    async def create_partner_rfid(self, partner_id: str, tag: RfidTag) -> None:
        await self._request(
            "POST",
            f"partners/{partner_id}/rfids",
            json_body={"rfid": tag.rfid, "rfidFormat": "Hex"},
        )

    async def revoke_partner_rfid(self, partner_id: str, rfid: str) -> None:
        await self._request("PUT", f"partners/{partner_id}/rfids/{rfid}/revoke", json_body={})
