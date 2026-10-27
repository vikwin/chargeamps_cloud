"""Constants for the Charge Amps Cloud integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

from .chargeamps_cloud.const import (
    CONNECTOR_MODE_OPTIONS,
    CONNECTOR_STATUS_OPTIONS,
    RFID_FORMAT_OPTIONS,
)

DOMAIN = "chargeamps_cloud"
MANUFACTURER = "Charge Amps"
CONFIGURATION_URL = "https://my.charge.space"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LOCK,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_API_KEY = "api_key"
CONF_ORGANISATION_ID = "organisation_id"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_RFID = "rfid"
CONF_RFID_FORMAT = "rfid_format"
CONF_RFID_LENGTH = "rfid_length"

DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 300
DEFAULT_RFID_FORMAT = "Hex"
DEFAULT_RFID_LENGTH = 4
SESSIONS_REFRESH_INTERVAL = timedelta(minutes=15)

EVENT_SESSION_STARTED = f"{DOMAIN}_session_started"
EVENT_SESSION_ENDED = f"{DOMAIN}_session_ended"
EVENT_CAR_CONNECTED = f"{DOMAIN}_car_connected"
EVENT_CAR_DISCONNECTED = f"{DOMAIN}_car_disconnected"

SERVICE_START_CHARGING = "start_charging"
SERVICE_STOP_CHARGING = "stop_charging"
SERVICE_SET_MODE = "set_mode"
SERVICE_SET_CURRENT = "set_current"
SERVICE_REBOOT = "reboot"
SERVICE_REFRESH = "refresh"

ATTR_CHARGEPOINT_ID = "chargepoint_id"
ATTR_CONNECTOR_ID = "connector_id"
ATTR_SESSION_ID = "session_id"
ATTR_RFID = "rfid"
ATTR_ENERGY_KWH = "energy_kwh"
ATTR_STARTED_AT = "started_at"
ATTR_ENDED_AT = "ended_at"


def charger_identifier(chargepoint_id: str) -> tuple[str, str]:
    return (DOMAIN, chargepoint_id)


def connector_identifier(chargepoint_id: str, connector_id: int) -> tuple[str, str]:
    return (DOMAIN, f"{chargepoint_id}:{connector_id}")


def parse_device_identifier(identifier: tuple[str, str]) -> tuple[str, int | None] | None:
    """Return ``(chargepoint_id, connector_id)`` for a Charge Amps identifier."""
    domain, value = identifier
    if domain != DOMAIN:
        return None
    if ":" not in value:
        return value, None
    chargepoint_id, connector_id = value.rsplit(":", 1)
    try:
        return chargepoint_id, int(connector_id)
    except ValueError:
        return chargepoint_id, None


__all__ = [
    "CONNECTOR_MODE_OPTIONS",
    "CONNECTOR_STATUS_OPTIONS",
    "RFID_FORMAT_OPTIONS",
]
