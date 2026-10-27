"""Constants for the Charge Amps Cloud API."""

from __future__ import annotations

API_BASE_URL = "https://eapi.charge.space"
API_VERSION = "v5"

DEFAULT_TIMEOUT = 30
DEFAULT_USER_AGENT = "chargeamps-cloud/0.1.1"
TOKEN_REFRESH_MARGIN = 120

#: Placeholder tag used when the account has no RFID tag and the caller
#: explicitly allows it.
PLACEHOLDER_RFID = "00000000000000"

#: Most Charge Amps RFID tags use 4 bytes; 7 and 10 byte tags are also valid.
DEFAULT_RFID_LENGTH = 4
DEFAULT_RFID_FORMAT = "Hex"

# CAPI status codes (legacy chargers).  OCPP chargers already return names.
CAPI_STATUS_MAP = {
    "0": "Available",
    "1": "Charging",
    "2": "Connected",
    "3": "Error",
    "4": "Unknown",
}

CONNECTOR_STATUS_OPTIONS = (
    "Available",
    "Preparing",
    "Charging",
    "SuspendedEVSE",
    "SuspendedEV",
    "Finishing",
    "Reserved",
    "Unavailable",
    "Faulted",
    "Connected",
    "Error",
    "Unknown",
)

#: Statuses that mean a vehicle is physically plugged in.
PLUGGED_IN_STATUSES = frozenset(
    {
        "Preparing",
        "Charging",
        "SuspendedEVSE",
        "SuspendedEV",
        "Finishing",
        "Connected",
    }
)

ONLINE_STATUS_OPTIONS = ("Online", "Offline")
CONNECTOR_MODE_OPTIONS = ("Off", "On", "Schedule")
DIMMER_OPTIONS = ("Off", "Low", "Medium", "High")
RFID_FORMAT_OPTIONS = ("Hex", "Dec", "ReverseDec")
SESSION_TYPE_OPTIONS = ("OnePhase", "ThreePhase", "Schuko")

_STATUS_LOOKUP = {status.lower(): status for status in CONNECTOR_STATUS_OPTIONS}


def normalize_status(value: object) -> str:
    """Return a canonical connector status.

    OCPP charge points return names such as ``SuspendedEV``, while CAPI charge
    points return numeric codes.  Unknown values are mapped to ``Unknown`` so
    that Home Assistant enum sensors always see a valid option.
    """
    if value is None:
        return "Unknown"
    text = str(value).strip()
    text = CAPI_STATUS_MAP.get(text, text)
    return _STATUS_LOOKUP.get(text.lower(), "Unknown")
