"""Number entities for Charge Amps Cloud."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent
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
    entities: list[NumberEntity] = []
    for chargepoint in coordinator.data.chargepoints.values():
        for connector in chargepoint.connectors:
            entities.append(ChargeAmpsMaxCurrentNumber(coordinator, chargepoint.id, connector.connector_id))
    async_add_entities(entities)


class ChargeAmpsMaxCurrentNumber(ChargeAmpsConnectorEntity, NumberEntity):
    """Maximum charging current for a connector."""

    _attr_translation_key = "max_current"
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_native_min_value = 6
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:current-ac"

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str, connector_id: int) -> None:
        super().__init__(coordinator, chargepoint_id, connector_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_{connector_id}_max_current"

    @property
    def native_max_value(self) -> float:
        settings = self.connector_settings
        return float(settings.installation_current or 32) if settings else 32

    @property
    def native_value(self) -> float | None:
        settings = self.connector_settings
        return settings.max_current if settings else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_current(self._chargepoint_id, self._connector_id, value)
