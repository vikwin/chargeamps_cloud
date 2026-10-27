"""Diagnostics for Charge Amps Cloud."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY, CONF_EMAIL, CONF_PASSWORD, DOMAIN

TO_REDACT = {CONF_EMAIL, CONF_PASSWORD, CONF_API_KEY, "token", "refreshToken", "refresh_token"}


def _dump(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _dump(item) for key, item in asdict(value).items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _dump(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_dump(item) for item in value]
    return value


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
            "version": entry.version,
        },
        "chargepoints": _dump(list(data.chargepoints.values())),
        "status": _dump(data.status),
        "settings": _dump(data.settings),
        "connector_settings": _dump(
            {
                f"{chargepoint_id}:{connector_id}": settings
                for (chargepoint_id, connector_id), settings in data.connector_settings.items()
            }
        ),
        "total_energy": data.total_energy,
        "sessions": _dump(data.sessions),
        "domain": DOMAIN,
    }
