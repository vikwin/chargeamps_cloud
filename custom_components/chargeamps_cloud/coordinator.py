"""Data update coordinator for the Charge Amps Cloud integration."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .chargeamps_cloud import (
    ChargeAmpsAuthError,
    ChargeAmpsClient,
    ChargeAmpsConnectionError,
    ChargeAmpsError,
    ChargeAmpsPortalClient,
    ChargePoint,
    ChargePointSettings,
    ChargePointStatus,
    ChargingSession,
    ConnectorSettings,
    RfidTag,
)
from .const import (
    ATTR_CHARGEPOINT_ID,
    ATTR_CONNECTOR_ID,
    ATTR_ENDED_AT,
    ATTR_ENERGY_KWH,
    ATTR_RFID,
    ATTR_SESSION_ID,
    ATTR_STARTED_AT,
    CONF_RFID,
    CONF_RFID_FORMAT,
    CONF_RFID_LENGTH,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_CAR_CONNECTED,
    EVENT_CAR_DISCONNECTED,
    EVENT_SESSION_ENDED,
    EVENT_SESSION_STARTED,
    SESSIONS_REFRESH_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ChargeAmpsData:
    """Data fetched from the Charge Amps API."""

    chargepoints: dict[str, ChargePoint]
    status: dict[str, ChargePointStatus]
    settings: dict[str, ChargePointSettings]
    connector_settings: dict[tuple[str, int], ConnectorSettings]
    sessions: dict[str, list[ChargingSession]]
    total_energy: dict[str, float]
    last_sessions: dict[tuple[str, int], ChargingSession]


class ChargeAmpsCoordinator(DataUpdateCoordinator[ChargeAmpsData]):
    """Coordinate polling and actions for all charge points of one account."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: ChargeAmpsClient | ChargeAmpsPortalClient,
    ) -> None:
        self.client = client
        self._sessions: dict[str, list[ChargingSession]] = {}
        self._sessions_updated_at: datetime | None = None
        self._sessions_interval = (
            timedelta(minutes=2) if getattr(client, "auth_mode", "api_key") == "portal" else SESSIONS_REFRESH_INTERVAL
        )
        self._session_details: set[int] = set()
        self._ended_sessions: set[int] = set()
        self._previous: dict[tuple[str, int], tuple[int | None, bool, bool]] = {}
        self._default_rfid: RfidTag | None = None
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )

    async def async_load_default_rfid(self) -> None:
        """Resolve the tag used for remote start."""
        configured = self.config_entry.options.get(CONF_RFID)
        if configured:
            self._default_rfid = RfidTag(active=True, rfid=str(configured))
            return
        try:
            self._default_rfid = await self.client.get_default_rfid(allow_placeholder=False)
        except ChargeAmpsError as err:
            _LOGGER.debug("Could not load the default RFID tag: %s", err)
            self._default_rfid = None

    async def _async_update_data(self) -> ChargeAmpsData:
        try:
            chargepoint_list = await self.client.get_chargepoints()
            chargepoints = {chargepoint.id: chargepoint for chargepoint in chargepoint_list}

            results = await asyncio.gather(
                *(self._fetch_chargepoint(chargepoint) for chargepoint in chargepoints.values())
            )
        except ChargeAmpsAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise ConfigEntryAuthFailed("Authentication with Charge Amps failed") from err
        except ChargeAmpsConnectionError as err:
            raise UpdateFailed(f"Could not reach Charge Amps: {err}") from err
        except ChargeAmpsError as err:
            raise UpdateFailed(f"Charge Amps API error: {err}") from err

        statuses: dict[str, ChargePointStatus] = {}
        settings: dict[str, ChargePointSettings] = {}
        connector_settings: dict[tuple[str, int], ConnectorSettings] = {}
        for chargepoint_id, status, chargepoint_settings, connector_settings_map in results:
            statuses[chargepoint_id] = status
            settings[chargepoint_id] = chargepoint_settings
            connector_settings.update(connector_settings_map)

        await self._refresh_sessions(chargepoints, statuses)
        self._enrich_status_from_sessions(statuses)
        for chargepoint_id, status in statuses.items():
            await self._load_active_session_details(chargepoint_id, status)

        total_energy: dict[str, float] = {}
        last_sessions: dict[tuple[str, int], ChargingSession] = {}
        for chargepoint_id, sessions in self._sessions.items():
            completed = [session for session in sessions if session.end_time is not None]
            completed_ids = {session.id for session in completed}
            completed_total = sum(session.total_consumption_kwh for session in completed)
            status = statuses.get(chargepoint_id)
            active_total = 0.0
            if status:
                active_total = sum(
                    connector.total_consumption_kwh
                    for connector in status.connector_statuses
                    if connector.session_id and connector.session_id not in completed_ids
                )
            total_energy[chargepoint_id] = round(completed_total + active_total, 2)
            for session in completed:
                key = (chargepoint_id, session.connector_id)
                current = last_sessions.get(key)
                if current is None or _session_sort_key(session) > _session_sort_key(current):
                    last_sessions[key] = session

        data = ChargeAmpsData(
            chargepoints=chargepoints,
            status=statuses,
            settings=settings,
            connector_settings=connector_settings,
            sessions=self._sessions,
            total_energy=total_energy,
            last_sessions=last_sessions,
        )
        self._fire_events(data)
        return data

    async def _fetch_chargepoint(
        self, chargepoint: ChargePoint
    ) -> tuple[str, ChargePointStatus, ChargePointSettings, dict[tuple[str, int], ConnectorSettings]]:
        status, settings = await asyncio.gather(
            self.client.get_chargepoint_status(chargepoint.id),
            self.client.get_chargepoint_settings(chargepoint.id),
        )
        connector_settings: dict[tuple[str, int], ConnectorSettings] = {}
        for connector in chargepoint.connectors:
            connector_settings[(chargepoint.id, connector.connector_id)] = await self.client.get_connector_settings(
                chargepoint.id, connector.connector_id
            )
        return chargepoint.id, status, settings, connector_settings

    async def _refresh_sessions(
        self, chargepoints: dict[str, ChargePoint], statuses: dict[str, ChargePointStatus]
    ) -> None:
        now = dt_util.utcnow()
        if self._sessions_updated_at is not None and now - self._sessions_updated_at < self._sessions_interval:
            return
        for chargepoint_id in chargepoints:
            try:
                self._sessions[chargepoint_id] = await self.client.get_charging_sessions(chargepoint_id)
            except ChargeAmpsError as err:
                _LOGGER.warning("Could not fetch sessions for %s: %s", chargepoint_id, err)
                self._sessions.setdefault(chargepoint_id, [])
        self._sessions_updated_at = now

    def _enrich_status_from_sessions(self, statuses: dict[str, ChargePointStatus]) -> None:
        """Fill session details that the portal API keeps in the session list."""
        for chargepoint_id, status in statuses.items():
            for connector in status.connector_statuses:
                if connector.session_id is not None:
                    continue
                active = next(
                    (
                        session
                        for session in self._sessions.get(chargepoint_id, [])
                        if session.connector_id == connector.connector_id and session.end_time is None
                    ),
                    None,
                )
                if active is not None:
                    connector.session_id = active.id
                    connector.start_time = active.start_time
                    connector.end_time = active.end_time
                    if getattr(self.client, "auth_mode", "api_key") == "portal":
                        connector.total_consumption_kwh = active.total_consumption_kwh

    async def _load_active_session_details(self, chargepoint_id: str, status: ChargePointStatus) -> None:
        sessions = self._sessions.setdefault(chargepoint_id, [])
        known_ids = {session.id for session in sessions}
        for connector in status.connector_statuses:
            session_id = connector.session_id
            if session_id is None or session_id in known_ids or session_id in self._session_details:
                continue
            self._session_details.add(session_id)
            try:
                session = await self.client.get_charging_session(chargepoint_id, session_id)
            except ChargeAmpsError as err:
                _LOGGER.debug("Could not fetch active session %s: %s", session_id, err)
                continue
            sessions.append(session)
            known_ids.add(session_id)

    def _fire_events(self, data: ChargeAmpsData) -> None:
        for chargepoint_id, status in data.status.items():
            for connector in status.connector_statuses:
                key = (chargepoint_id, connector.connector_id)
                plugged = connector.is_plugged_in
                previous = self._previous.get(key)
                if previous is not None:
                    previous_session_id, previous_plugged, _ = previous
                    if plugged and not previous_plugged:
                        self.hass.bus.async_fire(
                            EVENT_CAR_CONNECTED,
                            {ATTR_CHARGEPOINT_ID: chargepoint_id, ATTR_CONNECTOR_ID: connector.connector_id},
                        )
                    if previous_plugged and not plugged:
                        self.hass.bus.async_fire(
                            EVENT_CAR_DISCONNECTED,
                            {ATTR_CHARGEPOINT_ID: chargepoint_id, ATTR_CONNECTOR_ID: connector.connector_id},
                        )
                    if connector.session_id and connector.session_id != previous_session_id:
                        session = self._find_session(chargepoint_id, connector.session_id)
                        self.hass.bus.async_fire(
                            EVENT_SESSION_STARTED,
                            {
                                ATTR_CHARGEPOINT_ID: chargepoint_id,
                                ATTR_CONNECTOR_ID: connector.connector_id,
                                ATTR_SESSION_ID: connector.session_id,
                                ATTR_RFID: session.rfid if session else None,
                                ATTR_STARTED_AT: connector.start_time.isoformat() if connector.start_time else None,
                            },
                        )
                    if (
                        previous_session_id
                        and previous_session_id not in self._ended_sessions
                        and (not connector.session_id or connector.end_time is not None)
                    ):
                        self._ended_sessions.add(previous_session_id)
                        session = self._find_session(chargepoint_id, previous_session_id)
                        self.hass.bus.async_fire(
                            EVENT_SESSION_ENDED,
                            {
                                ATTR_CHARGEPOINT_ID: chargepoint_id,
                                ATTR_CONNECTOR_ID: connector.connector_id,
                                ATTR_SESSION_ID: previous_session_id,
                                ATTR_RFID: session.rfid if session else None,
                                ATTR_ENERGY_KWH: round(
                                    session.total_consumption_kwh if session else connector.total_consumption_kwh, 2
                                ),
                                ATTR_ENDED_AT: connector.end_time.isoformat() if connector.end_time else None,
                            },
                        )
                self._previous[key] = (connector.session_id, plugged, connector.status == "Charging")

    def _find_session(self, chargepoint_id: str, session_id: int) -> ChargingSession | None:
        for session in self._sessions.get(chargepoint_id, []):
            if session.id == session_id:
                return session
        return None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    async def async_start_charging(
        self,
        charge_point_id: str,
        connector_id: int,
        *,
        rfid: str | None = None,
        rfid_format: str | None = None,
        rfid_length: int | None = None,
    ) -> None:
        options = self.config_entry.options
        tag = rfid or options.get(CONF_RFID)
        if not tag and getattr(self.client, "auth_mode", "api_key") != "portal":
            tag = self._default_rfid.rfid if self._default_rfid else None
        if not tag and getattr(self.client, "auth_mode", "api_key") != "portal":
            raise HomeAssistantError("No RFID tag is configured for remote start")
        try:
            await self.client.remote_start(
                charge_point_id,
                connector_id,
                rfid=tag or None,
                rfid_format=rfid_format or options.get(CONF_RFID_FORMAT) or "Hex",
                rfid_length=rfid_length or _option_int(options.get(CONF_RFID_LENGTH)),
                allow_placeholder_tag=False,
            )
        except ChargeAmpsError as err:
            raise HomeAssistantError(f"Could not start charging: {err}") from err
        await self.async_request_refresh()

    async def async_stop_charging(self, charge_point_id: str, connector_id: int) -> None:
        try:
            await self.client.remote_stop(charge_point_id, connector_id)
        except ChargeAmpsError as err:
            raise HomeAssistantError(f"Could not stop charging: {err}") from err
        await self.async_request_refresh()

    async def async_set_mode(self, charge_point_id: str, connector_id: int, mode: str) -> None:
        settings = self.data.connector_settings.get((charge_point_id, connector_id))
        if settings is None:
            raise HomeAssistantError("Connector settings are not loaded")
        settings.mode = mode
        try:
            await self.client.set_connector_settings(settings)
        except ChargeAmpsError as err:
            raise HomeAssistantError(f"Could not set the charging mode: {err}") from err
        await self.async_request_refresh()

    async def async_set_current(self, charge_point_id: str, connector_id: int, current: float) -> None:
        settings = self.data.connector_settings.get((charge_point_id, connector_id))
        if settings is None:
            raise HomeAssistantError("Connector settings are not loaded")
        settings.max_current = current
        try:
            await self.client.set_connector_settings(settings)
        except ChargeAmpsError as err:
            raise HomeAssistantError(f"Could not set the current limit: {err}") from err
        await self.async_request_refresh()

    async def async_set_cable_lock(self, charge_point_id: str, connector_id: int, locked: bool) -> None:
        settings = self.data.connector_settings.get((charge_point_id, connector_id))
        if settings is None:
            raise HomeAssistantError("Connector settings are not loaded")
        settings.cable_lock = locked
        try:
            await self.client.set_connector_settings(settings)
        except ChargeAmpsError as err:
            raise HomeAssistantError(f"Could not change the cable lock: {err}") from err
        await self.async_request_refresh()

    async def async_set_rfid_lock(self, charge_point_id: str, connector_id: int, locked: bool) -> None:
        settings = self.data.connector_settings.get((charge_point_id, connector_id))
        if settings is None:
            raise HomeAssistantError("Connector settings are not loaded")
        settings.rfid_lock = locked
        try:
            await self.client.set_connector_settings(settings)
        except ChargeAmpsError as err:
            raise HomeAssistantError(f"Could not change the RFID lock: {err}") from err
        await self.async_request_refresh()

    async def async_reboot(self, charge_point_id: str) -> None:
        try:
            await self.client.reboot(charge_point_id)
        except ChargeAmpsError as err:
            raise HomeAssistantError(f"Could not reboot the charger: {err}") from err
        await self.async_request_refresh()


def _session_sort_key(session: ChargingSession) -> datetime:
    return session.start_time or datetime.min.replace(tzinfo=UTC)


def _option_int(value: object) -> int | None:
    if value in (None, "", "auto", "Auto"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
