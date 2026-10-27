"""Lock entities for Charge Amps Cloud."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
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
    entities: list[LockEntity] = []
    for chargepoint in coordinator.data.chargepoints.values():
        for connector in chargepoint.connectors:
            entities.append(ChargeAmpsCableLock(coordinator, chargepoint.id, connector.connector_id))
    async_add_entities(entities)


class ChargeAmpsCableLock(ChargeAmpsConnectorEntity, LockEntity):
    """Lock or unlock the charging cable."""

    _attr_translation_key = "cable_lock"
    _attr_icon = "mdi:lock"

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str, connector_id: int) -> None:
        super().__init__(coordinator, chargepoint_id, connector_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_{connector_id}_cable_lock"

    @property
    def is_locked(self) -> bool | None:
        settings = self.connector_settings
        return settings.cable_lock if settings else None

    async def async_lock(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_cable_lock(self._chargepoint_id, self._connector_id, True)

    async def async_unlock(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_cable_lock(self._chargepoint_id, self._connector_id, False)
