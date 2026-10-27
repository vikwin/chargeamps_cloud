"""Switches for Charge Amps Cloud."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ChargeAmpsCoordinator
from .entity import ChargeAmpsConnectorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ChargeAmpsCoordinator = entry.runtime_data
    entities: list[SwitchEntity] = []
    for chargepoint in coordinator.data.chargepoints.values():
        for connector in chargepoint.connectors:
            entities.append(ChargeAmpsChargingSwitch(coordinator, chargepoint.id, connector.connector_id))
            entities.append(ChargeAmpsRfidLockSwitch(coordinator, chargepoint.id, connector.connector_id))
    async_add_entities(entities)


class ChargeAmpsChargingSwitch(ChargeAmpsConnectorEntity, SwitchEntity):
    """Enable or disable charging on a connector."""

    _attr_translation_key = "charging_enabled"
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str, connector_id: int) -> None:
        super().__init__(coordinator, chargepoint_id, connector_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_{connector_id}_charging_enabled"

    @property
    def is_on(self) -> bool | None:
        settings = self.connector_settings
        if settings is None:
            return None
        return settings.mode in ("On", "Schedule")

    async def async_turn_on(self, **kwargs: Any) -> None:
        settings = self.connector_settings
        if settings is not None and settings.mode == "Schedule":
            return
        await self.coordinator.async_set_mode(self._chargepoint_id, self._connector_id, "On")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_mode(self._chargepoint_id, self._connector_id, "Off")


class ChargeAmpsRfidLockSwitch(ChargeAmpsConnectorEntity, SwitchEntity):
    """Enable or disable RFID authorization on a connector."""

    _attr_translation_key = "rfid_lock"
    _attr_icon = "mdi:card-account-details"

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str, connector_id: int) -> None:
        super().__init__(coordinator, chargepoint_id, connector_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_{connector_id}_rfid_lock"

    @property
    def is_on(self) -> bool | None:
        settings = self.connector_settings
        return settings.rfid_lock if settings else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_rfid_lock(self._chargepoint_id, self._connector_id, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_rfid_lock(self._chargepoint_id, self._connector_id, False)
