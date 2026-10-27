"""Binary sensors for Charge Amps Cloud."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    entities: list[BinarySensorEntity] = []
    for chargepoint in coordinator.data.chargepoints.values():
        entities.append(ChargeAmpsOnlineSensor(coordinator, chargepoint.id))
        for connector in chargepoint.connectors:
            entities.append(ChargeAmpsCarConnectedSensor(coordinator, chargepoint.id, connector.connector_id))
            entities.append(ChargeAmpsChargingSensor(coordinator, chargepoint.id, connector.connector_id))
    async_add_entities(entities)


class ChargeAmpsOnlineSensor(ChargeAmpsEntity, BinarySensorEntity):
    """Whether the charge point is online."""

    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str) -> None:
        super().__init__(coordinator, chargepoint_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_online"

    @property
    def is_on(self) -> bool | None:
        status = self.chargepoint_status
        return status.is_online if status else None


class ChargeAmpsCarConnectedSensor(ChargeAmpsConnectorEntity, BinarySensorEntity):
    """Whether a vehicle is plugged into the connector."""

    _attr_translation_key = "car_connected"
    _attr_device_class = BinarySensorDeviceClass.PLUG

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str, connector_id: int) -> None:
        super().__init__(coordinator, chargepoint_id, connector_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_{connector_id}_car_connected"

    @property
    def is_on(self) -> bool | None:
        status = self.connector_status
        return status.is_plugged_in if status else None


class ChargeAmpsChargingSensor(ChargeAmpsConnectorEntity, BinarySensorEntity):
    """Whether the connector is charging."""

    _attr_translation_key = "charging"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str, connector_id: int) -> None:
        super().__init__(coordinator, chargepoint_id, connector_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_{connector_id}_charging_active"

    @property
    def is_on(self) -> bool | None:
        status = self.connector_status
        return status.status == "Charging" if status else None
