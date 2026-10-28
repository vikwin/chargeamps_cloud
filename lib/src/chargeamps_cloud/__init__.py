"""Charge Amps Cloud API client."""

from __future__ import annotations

from .client import ChargeAmpsClient
from .const import (
    API_BASE_URL,
    CONNECTOR_MODE_OPTIONS,
    CONNECTOR_STATUS_OPTIONS,
    DEFAULT_RFID_FORMAT,
    DEFAULT_RFID_LENGTH,
    RFID_FORMAT_OPTIONS,
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
    Organisation,
    Partner,
    RfidTag,
    Schedule,
    ScheduleOverrideStatus,
    StartAuth,
    User,
)
from .portal import ChargeAmpsPortalClient

__version__ = "0.2.0"

__all__ = [
    "API_BASE_URL",
    "CONNECTOR_MODE_OPTIONS",
    "CONNECTOR_STATUS_OPTIONS",
    "DEFAULT_RFID_FORMAT",
    "DEFAULT_RFID_LENGTH",
    "RFID_FORMAT_OPTIONS",
    "ChargeAmpsApiError",
    "ChargeAmpsAuthError",
    "ChargeAmpsClient",
    "ChargeAmpsPortalClient",
    "ChargeAmpsConnectionError",
    "ChargeAmpsError",
    "ChargeAmpsForbiddenError",
    "ChargeAmpsNotFoundError",
    "ChargeAmpsRateLimitError",
    "ChargePoint",
    "ChargePointSettings",
    "ChargePointStatus",
    "ChargingSession",
    "Connector",
    "ConnectorSettings",
    "ConnectorStatus",
    "Measurement",
    "Organisation",
    "Partner",
    "RfidTag",
    "Schedule",
    "ScheduleOverrideStatus",
    "StartAuth",
    "User",
    "__version__",
]
