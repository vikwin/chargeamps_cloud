"""Sensors for Charge Amps Cloud."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .chargeamps_cloud import ChargingSession
from .chargeamps_cloud.const import (
    CONNECTOR_MODE_OPTIONS,
    CONNECTOR_STATUS_OPTIONS,
    ONLINE_STATUS_OPTIONS,
)
from .const import DOMAIN
from .coordinator import ChargeAmpsCoordinator
from .entity import ChargeAmpsConnectorEntity, ChargeAmpsEntity

PHASES = ("L1", "L2", "L3")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ChargeAmpsCoordinator = entry.runtime_data
    entities: list[SensorEntity] = []
    for chargepoint in coordinator.data.chargepoints.values():
        entities.append(ChargeAmpsChargerStatusSensor(coordinator, chargepoint.id))
        entities.append(ChargeAmpsFirmwareSensor(coordinator, chargepoint.id))
        entities.append(ChargeAmpsTotalEnergySensor(coordinator, chargepoint.id))
        for connector in chargepoint.connectors:
            connector_id = connector.connector_id
            entities.extend(
                [
                    ChargeAmpsConnectorStatusSensor(coordinator, chargepoint.id, connector_id),
                    ChargeAmpsPowerSensor(coordinator, chargepoint.id, connector_id),
                    ChargeAmpsSessionEnergySensor(coordinator, chargepoint.id, connector_id),
                    ChargeAmpsSessionStartedSensor(coordinator, chargepoint.id, connector_id),
                    ChargeAmpsSessionDurationSensor(coordinator, chargepoint.id, connector_id),
                    ChargeAmpsSessionRfidSensor(coordinator, chargepoint.id, connector_id),
                    ChargeAmpsLastSessionEnergySensor(coordinator, chargepoint.id, connector_id),
                    ChargeAmpsModeSensor(coordinator, chargepoint.id, connector_id),
                ]
            )
            for phase in PHASES:
                entities.append(ChargeAmpsCurrentSensor(coordinator, chargepoint.id, connector_id, phase))
                entities.append(ChargeAmpsVoltageSensor(coordinator, chargepoint.id, connector_id, phase))
    async_add_entities(entities)


class ChargeAmpsChargerStatusSensor(ChargeAmpsEntity, SensorEntity):
    """Online/offline status of the charge point."""

    _attr_translation_key = "charger_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(ONLINE_STATUS_OPTIONS)

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str) -> None:
        super().__init__(coordinator, chargepoint_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_charger_status"

    @property
    def native_value(self) -> str | None:
        status = self.chargepoint_status
        if status is None:
            return None
        value = status.status.title()
        return value if value in ONLINE_STATUS_OPTIONS else "Offline"


class ChargeAmpsConnectorStatusSensor(ChargeAmpsConnectorEntity, SensorEntity):
    """Detailed connector state (Available, Preparing, Charging, ...)."""

    _attr_translation_key = "connector_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(CONNECTOR_STATUS_OPTIONS)

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str, connector_id: int) -> None:
        super().__init__(coordinator, chargepoint_id, connector_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_{connector_id}_connector_status"

    @property
    def native_value(self) -> str | None:
        status = self.connector_status
        return status.status if status else None


class ChargeAmpsFirmwareSensor(ChargeAmpsEntity, SensorEntity):
    """Firmware version of the charge point."""

    _attr_translation_key = "firmware"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chip"

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str) -> None:
        super().__init__(coordinator, chargepoint_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_firmware"

    @property
    def native_value(self) -> str | None:
        return self.chargepoint.firmware_version


class ChargeAmpsTotalEnergySensor(ChargeAmpsEntity, SensorEntity):
    """Lifetime energy of all recorded sessions."""

    _attr_translation_key = "total_energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str) -> None:
        super().__init__(coordinator, chargepoint_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_total_energy"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.total_energy.get(self._chargepoint_id)


class _ConnectorSensor(ChargeAmpsConnectorEntity, SensorEntity):
    """Base class for connector sensors."""

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str, connector_id: int) -> None:
        super().__init__(coordinator, chargepoint_id, connector_id)

    def _session(self) -> ChargingSession | None:
        status = self.connector_status
        if status is None or status.session_id is None:
            return None
        for session in self.coordinator.data.sessions.get(self._chargepoint_id, []):
            if session.id == status.session_id:
                return session
        return None


class ChargeAmpsPowerSensor(_ConnectorSensor):
    """Instantaneous charging power."""

    _attr_translation_key = "power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str, connector_id: int) -> None:
        super().__init__(coordinator, chargepoint_id, connector_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_{connector_id}_power"

    @property
    def native_value(self) -> float | None:
        status = self.connector_status
        return status.power_w if status else None


class ChargeAmpsSessionEnergySensor(_ConnectorSensor):
    """Energy of the current session."""

    _attr_translation_key = "session_energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str, connector_id: int) -> None:
        super().__init__(coordinator, chargepoint_id, connector_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_{connector_id}_session_energy"

    @property
    def native_value(self) -> float | None:
        status = self.connector_status
        return round(status.total_consumption_kwh, 2) if status else None


class ChargeAmpsCurrentSensor(_ConnectorSensor):
    """Per-phase current."""

    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_suggested_display_precision = 1

    def __init__(
        self,
        coordinator: ChargeAmpsCoordinator,
        chargepoint_id: str,
        connector_id: int,
        phase: str,
    ) -> None:
        super().__init__(coordinator, chargepoint_id, connector_id)
        self._phase = phase
        self._attr_translation_key = f"current_{phase.lower()}"
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_{connector_id}_current_{phase.lower()}"

    @property
    def native_value(self) -> float | None:
        status = self.connector_status
        return status.measurement(self._phase, "current") if status else None


class ChargeAmpsVoltageSensor(_ConnectorSensor):
    """Per-phase voltage."""

    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        coordinator: ChargeAmpsCoordinator,
        chargepoint_id: str,
        connector_id: int,
        phase: str,
    ) -> None:
        super().__init__(coordinator, chargepoint_id, connector_id)
        self._phase = phase
        self._attr_translation_key = f"voltage_{phase.lower()}"
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_{connector_id}_voltage_{phase.lower()}"

    @property
    def native_value(self) -> float | None:
        status = self.connector_status
        return status.measurement(self._phase, "voltage") if status else None


class ChargeAmpsSessionStartedSensor(_ConnectorSensor):
    """Start time of the current session."""

    _attr_translation_key = "session_started"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str, connector_id: int) -> None:
        super().__init__(coordinator, chargepoint_id, connector_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_{connector_id}_session_started"

    @property
    def native_value(self) -> datetime | None:
        status = self.connector_status
        return status.start_time if status else None


class ChargeAmpsSessionDurationSensor(_ConnectorSensor):
    """Duration of the current session."""

    _attr_translation_key = "session_duration"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str, connector_id: int) -> None:
        super().__init__(coordinator, chargepoint_id, connector_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_{connector_id}_session_duration"

    @property
    def native_value(self) -> int | None:
        status = self.connector_status
        if status is None or status.start_time is None:
            return None
        end = status.end_time or dt_util.utcnow()
        return max(0, int((end - status.start_time).total_seconds()))


class ChargeAmpsSessionRfidSensor(_ConnectorSensor):
    """RFID tag that started the current session."""

    _attr_translation_key = "session_rfid"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:card-account-details"

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str, connector_id: int) -> None:
        super().__init__(coordinator, chargepoint_id, connector_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_{connector_id}_session_rfid"

    @property
    def native_value(self) -> str | None:
        session = self._session()
        return session.rfid if session else None


class ChargeAmpsLastSessionEnergySensor(_ConnectorSensor):
    """Energy of the last completed session."""

    _attr_translation_key = "last_session_energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str, connector_id: int) -> None:
        super().__init__(coordinator, chargepoint_id, connector_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_{connector_id}_last_session_energy"

    @property
    def native_value(self) -> float | None:
        session = self.coordinator.data.last_sessions.get((self._chargepoint_id, self._connector_id))
        return round(session.total_consumption_kwh, 2) if session else None


class ChargeAmpsModeSensor(_ConnectorSensor):
    """Charging mode of the connector."""

    _attr_translation_key = "mode"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(CONNECTOR_MODE_OPTIONS)
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ChargeAmpsCoordinator, chargepoint_id: str, connector_id: int) -> None:
        super().__init__(coordinator, chargepoint_id, connector_id)
        self._attr_unique_id = f"{DOMAIN}_{chargepoint_id}_{connector_id}_mode"

    @property
    def native_value(self) -> str | None:
        settings = self.connector_settings
        return settings.mode if settings else None
