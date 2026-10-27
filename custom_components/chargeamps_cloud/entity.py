"""Base entities for Charge Amps Cloud."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .chargeamps_cloud import ChargePoint, ChargePointStatus, ConnectorSettings, ConnectorStatus
from .const import (
    CONFIGURATION_URL,
    DOMAIN,
    MANUFACTURER,
    charger_identifier,
    connector_identifier,
)
from .coordinator import ChargeAmpsCoordinator


class ChargeAmpsEntity(CoordinatorEntity[ChargeAmpsCoordinator]):
    """Base entity for a charge point."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str) -> None:
        super().__init__(coordinator)
        self._chargepoint_id = chargepoint_id
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}"

    @property
    def chargepoint(self) -> ChargePoint:
        return self.coordinator.data.chargepoints[self._chargepoint_id]

    @property
    def chargepoint_status(self) -> ChargePointStatus | None:
        return self.coordinator.data.status.get(self._chargepoint_id)

    @property
    def device_info(self) -> DeviceInfo:
        chargepoint = self.chargepoint
        return DeviceInfo(
            identifiers={charger_identifier(chargepoint.id)},
            manufacturer=MANUFACTURER,
            name=chargepoint.label,
            model=chargepoint.type,
            sw_version=chargepoint.firmware_version,
            hw_version=chargepoint.hardware_version,
            configuration_url=CONFIGURATION_URL,
        )


class ChargeAmpsConnectorEntity(ChargeAmpsEntity):
    """Base entity for a connector on a charge point."""

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str, connector_id: int) -> None:
        super().__init__(coordinator, chargepoint_id)
        self._connector_id = connector_id

    @property
    def connector_status(self) -> ConnectorStatus | None:
        status = self.chargepoint_status
        return status.connector(self._connector_id) if status else None

    @property
    def connector_settings(self) -> ConnectorSettings | None:
        return self.coordinator.data.connector_settings.get((self._chargepoint_id, self._connector_id))

    @property
    def device_info(self) -> DeviceInfo:
        chargepoint = self.chargepoint
        connector = next(
            (item for item in chargepoint.connectors if item.connector_id == self._connector_id),
            None,
        )
        label = connector.type if connector and connector.type else f"Connector {self._connector_id}"
        parent = dr.async_get(self.hass).async_get_device_by_identifier(
            charger_identifier(chargepoint.id),
            self.coordinator.config_entry.entry_id,
        )
        device_info = DeviceInfo(
            identifiers={connector_identifier(chargepoint.id, self._connector_id)},
            manufacturer=MANUFACTURER,
            name=f"{chargepoint.label} {label}",
            model=connector.type if connector else None,
        )
        if parent is not None:
            device_info["via_device_id"] = parent.id
        else:
            device_info["via_device"] = charger_identifier(chargepoint.id)
        return device_info
