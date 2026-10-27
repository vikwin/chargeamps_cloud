"""Set up the Charge Amps Cloud integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .chargeamps_cloud import ChargeAmpsAuthError, ChargeAmpsClient, ChargeAmpsConnectionError, ChargeAmpsError
from .const import (
    CONF_API_KEY,
    CONF_EMAIL,
    CONF_ORGANISATION_ID,
    CONF_PASSWORD,
    CONNECTOR_MODE_OPTIONS,
    DOMAIN,
    PLATFORMS,
    RFID_FORMAT_OPTIONS,
    SERVICE_REBOOT,
    SERVICE_REFRESH,
    SERVICE_SET_CURRENT,
    SERVICE_SET_MODE,
    SERVICE_START_CHARGING,
    SERVICE_STOP_CHARGING,
    parse_device_identifier,
)
from .coordinator import ChargeAmpsCoordinator

_LOGGER = logging.getLogger(__name__)

ChargeAmpsConfigEntry = ConfigEntry[ChargeAmpsCoordinator]

SERVICE_START_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Optional("rfid"): cv.string,
        vol.Optional("rfid_format"): vol.In(RFID_FORMAT_OPTIONS),
        vol.Optional("rfid_length"): vol.All(vol.Coerce(int), vol.In((4, 7, 10))),
    }
)
SERVICE_STOP_SCHEMA = vol.Schema({vol.Required("device_id"): cv.string})
SERVICE_SET_MODE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("mode"): vol.In(CONNECTOR_MODE_OPTIONS),
    }
)
SERVICE_SET_CURRENT_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("current"): vol.All(vol.Coerce(float), vol.Range(min=6, max=32)),
    }
)
SERVICE_DEVICE_SCHEMA = vol.Schema({vol.Required("device_id"): cv.string})
SERVICE_REFRESH_SCHEMA = vol.Schema({})


async def async_setup_entry(hass: HomeAssistant, entry: ChargeAmpsConfigEntry) -> bool:
    """Set up Charge Amps Cloud from a config entry."""
    session = async_get_clientsession(hass)
    client = ChargeAmpsClient(
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_API_KEY],
        session=session,
        organisation_id=entry.data.get(CONF_ORGANISATION_ID),
    )
    try:
        await client.login()
    except ChargeAmpsAuthError as err:
        raise ConfigEntryAuthFailed("Authentication with Charge Amps failed") from err
    except ChargeAmpsConnectionError as err:
        raise ConfigEntryNotReady(f"Could not reach Charge Amps: {err}") from err
    except ChargeAmpsError as err:
        raise ConfigEntryNotReady(f"Charge Amps API error: {err}") from err

    coordinator = ChargeAmpsCoordinator(hass, entry, client)
    entry.runtime_data = coordinator
    await coordinator.async_load_default_rfid()
    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ChargeAmpsConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and not hass.config_entries.async_entries(DOMAIN):
        for service in (
            SERVICE_START_CHARGING,
            SERVICE_STOP_CHARGING,
            SERVICE_SET_MODE,
            SERVICE_SET_CURRENT,
            SERVICE_REBOOT,
            SERVICE_REFRESH,
        ):
            if hass.services.has_service(DOMAIN, service):
                hass.services.async_remove(DOMAIN, service)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ChargeAmpsConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _resolve_device(hass: HomeAssistant, call: ServiceCall) -> tuple[ChargeAmpsCoordinator, str, int | None]:
    device_id = call.data.get("device_id")
    if not device_id:
        raise HomeAssistantError("A Charge Amps device must be selected")
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise HomeAssistantError("The selected device no longer exists")
    chargepoint_id: str | None = None
    connector_id: int | None = None
    for identifier in device.identifiers:
        parsed = parse_device_identifier(identifier)
        if parsed is not None:
            chargepoint_id, connector_id = parsed
            break
    if chargepoint_id is None:
        raise HomeAssistantError("The selected device is not a Charge Amps charge point")
    entry_ids: list[str] = []
    entry_id = getattr(device, "config_entry_id", None)
    if entry_id is not None:
        entry_ids.append(entry_id)
    else:
        entry_ids.extend(device.config_entries)
    for entry_id in entry_ids:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is not None and entry.domain == DOMAIN and entry.runtime_data is not None:
            return entry.runtime_data, chargepoint_id, connector_id
    raise HomeAssistantError("No Charge Amps entry is loaded for this device")


def _require_connector(connector_id: int | None) -> int:
    if connector_id is None:
        raise HomeAssistantError("Select a connector device, not the charger itself")
    return connector_id


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_START_CHARGING):
        return

    async def async_start_charging(call: ServiceCall) -> None:
        coordinator, chargepoint_id, connector_id = _resolve_device(hass, call)
        await coordinator.async_start_charging(
            chargepoint_id,
            _require_connector(connector_id),
            rfid=call.data.get("rfid"),
            rfid_format=call.data.get("rfid_format"),
            rfid_length=call.data.get("rfid_length"),
        )

    async def async_stop_charging(call: ServiceCall) -> None:
        coordinator, chargepoint_id, connector_id = _resolve_device(hass, call)
        await coordinator.async_stop_charging(chargepoint_id, _require_connector(connector_id))

    async def async_set_mode(call: ServiceCall) -> None:
        coordinator, chargepoint_id, connector_id = _resolve_device(hass, call)
        await coordinator.async_set_mode(chargepoint_id, _require_connector(connector_id), call.data["mode"])

    async def async_set_current(call: ServiceCall) -> None:
        coordinator, chargepoint_id, connector_id = _resolve_device(hass, call)
        await coordinator.async_set_current(chargepoint_id, _require_connector(connector_id), call.data["current"])

    async def async_reboot(call: ServiceCall) -> None:
        coordinator, chargepoint_id, _connector_id = _resolve_device(hass, call)
        await coordinator.async_reboot(chargepoint_id)

    async def async_refresh(_call: ServiceCall) -> None:
        for entry in hass.config_entries.async_entries(DOMAIN):
            coordinator: ChargeAmpsCoordinator | None = entry.runtime_data
            if coordinator is not None:
                await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_START_CHARGING, async_start_charging, schema=SERVICE_START_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_STOP_CHARGING, async_stop_charging, schema=SERVICE_STOP_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_MODE, async_set_mode, schema=SERVICE_SET_MODE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_CURRENT, async_set_current, schema=SERVICE_SET_CURRENT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REBOOT, async_reboot, schema=SERVICE_DEVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, async_refresh, schema=SERVICE_REFRESH_SCHEMA)
