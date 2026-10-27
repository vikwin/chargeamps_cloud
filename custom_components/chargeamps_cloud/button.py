"""Buttons for Charge Amps Cloud."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ChargeAmpsCoordinator
from .entity import ChargeAmpsConnectorEntity, ChargeAmpsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ChargeAmpsCoordinator = entry.runtime_data
    entities: list[ButtonEntity] = []
    for chargepoint in coordinator.data.chargepoints.values():
        entities.append(ChargeAmpsRebootButton(coordinator, chargepoint.id))
        for connector in chargepoint.connectors:
            entities.append(ChargeAmpsStartButton(coordinator, chargepoint.id, connector.connector_id))
            entities.append(ChargeAmpsStopButton(coordinator, chargepoint.id, connector.connector_id))
    async_add_entities(entities)


class ChargeAmpsStartButton(ChargeAmpsConnectorEntity, ButtonEntity):
    """Start a charging session with the configured RFID tag."""

    _attr_translation_key = "start_charging"
    _attr_icon = "mdi:play-circle"

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str, connector_id: int) -> None:
        super().__init__(coordinator, chargepoint_id, connector_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_{connector_id}_start_charging"

    async def async_press(self) -> None:
        await self.coordinator.async_start_charging(self._chargepoint_id, self._connector_id)


class ChargeAmpsStopButton(ChargeAmpsConnectorEntity, ButtonEntity):
    """Stop the current charging session."""

    _attr_translation_key = "stop_charging"
    _attr_icon = "mdi:stop-circle"

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str, connector_id: int) -> None:
        super().__init__(coordinator, chargepoint_id, connector_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_{connector_id}_stop_charging"

    async def async_press(self) -> None:
        await self.coordinator.async_stop_charging(self._chargepoint_id, self._connector_id)


class ChargeAmpsRebootButton(ChargeAmpsEntity, ButtonEntity):
    """Reboot the charge point."""

    _attr_translation_key = "reboot"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str) -> None:
        super().__init__(coordinator, chargepoint_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_reboot"

    async def async_press(self) -> None:
        await self.coordinator.async_reboot(self._chargepoint_id)
