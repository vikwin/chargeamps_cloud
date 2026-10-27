"""Typed data models for the Charge Amps Cloud API."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .const import normalize_status


def _value(data: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    """Return the first present key from an API payload."""
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def _text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return bool(value)


def _datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _as_dict(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


@dataclass(slots=True)
class Measurement:
    """One phase measurement."""

    phase: str
    current: float | None = None
    voltage: float | None = None

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> Measurement:
        return cls(
            phase=str(_value(data, "phase", default="")),
            current=_float(_value(data, "current")),
            voltage=_float(_value(data, "voltage")),
        )


@dataclass(slots=True)
class ConnectorSettings:
    """Settings of a single connector."""

    connector_id: int
    charge_point_id: str | None = None
    mode: str = "Off"
    rfid_lock: bool = False
    cable_lock: bool = False
    max_current: float | None = None
    installation_current: int | None = None

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> ConnectorSettings:
        return cls(
            connector_id=_int(_value(data, "connectorId")) or 0,
            charge_point_id=_text(_value(data, "chargePointId")),
            mode=str(_value(data, "mode", default="Off")),
            rfid_lock=_bool(_value(data, "rfidLock")),
            cable_lock=_bool(_value(data, "cableLock")),
            max_current=_float(_value(data, "maxCurrent")),
            installation_current=_int(_value(data, "installationCurrent")),
        )

    def to_api(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chargePointId": self.charge_point_id,
            "connectorId": self.connector_id,
            "mode": self.mode,
            "rfidLock": self.rfid_lock,
            "cableLock": self.cable_lock,
        }
        if self.max_current is not None:
            payload["maxCurrent"] = self.max_current
        return payload


@dataclass(slots=True)
class ChargePointSettings:
    """Charger-wide settings."""

    id: str
    dimmer: str = "Off"
    down_light: bool | None = None
    max_current: float | None = None
    installation_current: int | None = None

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> ChargePointSettings:
        return cls(
            id=str(_value(data, "id", default="")),
            dimmer=str(_value(data, "dimmer", default="Off")),
            down_light=None if _value(data, "downLight") is None else _bool(_value(data, "downLight")),
            max_current=_float(_value(data, "maxCurrent")),
            installation_current=_int(_value(data, "installationCurrent")),
        )

    def to_api(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "dimmer": self.dimmer,
        }
        if self.down_light is not None:
            payload["downLight"] = self.down_light
        if self.max_current is not None:
            payload["maxCurrent"] = self.max_current
        return payload


@dataclass(slots=True)
class Connector:
    """A connector on a charge point."""

    connector_id: int
    charge_point_id: str | None = None
    type: str | None = None
    settings: ConnectorSettings | None = None
    connector_user_id: str | None = None

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> Connector:
        settings = _value(data, "settings")
        return cls(
            connector_id=_int(_value(data, "connectorId")) or 0,
            charge_point_id=_text(_value(data, "chargePointId")),
            type=_text(_value(data, "type")),
            settings=ConnectorSettings.from_api(_as_dict(settings)) if isinstance(settings, Mapping) else None,
            connector_user_id=_text(_value(data, "connectorUserId")),
        )


@dataclass(slots=True)
class ChargePoint:
    """A Charge Amps charge point."""

    id: str
    name: str | None = None
    password: str | None = None
    type: str | None = None
    is_loadbalanced: bool = False
    firmware_version: str | None = None
    hardware_version: str | None = None
    owner_read_only: bool = False
    ocpp_version: str | None = None
    settings: ChargePointSettings | None = None
    connectors: list[Connector] = field(default_factory=list)

    @property
    def is_capi(self) -> bool:
        """Return True for legacy CAPI chargers."""
        return not self.ocpp_version or self.ocpp_version.upper() == "CAPI"

    @property
    def label(self) -> str:
        return self.name or self.id

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> ChargePoint:
        settings = _value(data, "settings")
        connectors = _value(data, "connectors", default=[])
        return cls(
            id=str(_value(data, "id", default="")),
            name=_text(_value(data, "name")),
            password=_text(_value(data, "password")),
            type=_text(_value(data, "type")),
            is_loadbalanced=_bool(_value(data, "isLoadbalanced")),
            firmware_version=_text(_value(data, "firmwareVersion")),
            hardware_version=_text(_value(data, "hardwareVersion")),
            owner_read_only=_bool(_value(data, "ownerReadOnly")),
            ocpp_version=_text(_value(data, "ocppVersion")),
            settings=ChargePointSettings.from_api(_as_dict(settings)) if isinstance(settings, Mapping) else None,
            connectors=[
                Connector.from_api(_as_dict(connector)) for connector in connectors if isinstance(connector, Mapping)
            ],
        )


@dataclass(slots=True)
class ConnectorStatus:
    """Live status of a single connector."""

    charge_point_id: str | None
    connector_id: int
    status: str = "Unknown"
    total_consumption_kwh: float = 0.0
    charging_power_kw: float | None = None
    session_type: str | None = None
    measurements: list[Measurement] = field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None
    session_id: int | None = None

    @property
    def power_w(self) -> float | None:
        if self.charging_power_kw is None:
            return None
        return round(self.charging_power_kw * 1000, 1)

    @property
    def is_plugged_in(self) -> bool:
        from .const import PLUGGED_IN_STATUSES

        return self.status in PLUGGED_IN_STATUSES

    @property
    def phase(self) -> dict[str, tuple[float | None, float | None]]:
        """Return ``{phase: (current, voltage)}``."""
        return {measurement.phase: (measurement.current, measurement.voltage) for measurement in self.measurements}

    def measurement(self, phase: str, kind: str) -> float | None:
        for measurement in self.measurements:
            if measurement.phase.lower() == phase.lower():
                return measurement.current if kind == "current" else measurement.voltage
        return None

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> ConnectorStatus:
        measurements = _value(data, "measurements", default=[])
        return cls(
            charge_point_id=_text(_value(data, "chargePointId")),
            connector_id=_int(_value(data, "connectorId")) or 0,
            status=normalize_status(_value(data, "status")),
            total_consumption_kwh=_float(_value(data, "totalConsumptionKwh")) or 0.0,
            charging_power_kw=_float(_value(data, "chargingPowerKw")),
            session_type=_text(_value(data, "sessionType")),
            measurements=[
                Measurement.from_api(_as_dict(measurement))
                for measurement in measurements
                if isinstance(measurement, Mapping)
            ],
            start_time=_datetime(_value(data, "startTime")),
            end_time=_datetime(_value(data, "endTime")),
            session_id=_int(_value(data, "sessionId")),
        )


@dataclass(slots=True)
class ChargePointStatus:
    """Status of a charge point including all connectors."""

    id: str
    status: str
    connector_statuses: list[ConnectorStatus] = field(default_factory=list)

    @property
    def is_online(self) -> bool:
        return self.status.lower() == "online"

    def connector(self, connector_id: int) -> ConnectorStatus | None:
        for status in self.connector_statuses:
            if status.connector_id == connector_id:
                return status
        return None

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> ChargePointStatus:
        statuses = _value(data, "connectorStatuses", default=[])
        return cls(
            id=str(_value(data, "id", default="")),
            status=str(_value(data, "status", default="Offline")),
            connector_statuses=[
                ConnectorStatus.from_api(_as_dict(status)) for status in statuses if isinstance(status, Mapping)
            ],
        )


@dataclass(slots=True)
class ChargingSession:
    """A charging session from the session history."""

    id: int
    charge_point_id: str | None = None
    connector_id: int = 0
    user_id: str | None = None
    rfid: str | None = None
    rfid_dec: str | None = None
    rfid_dec_reverse: str | None = None
    organisation_id: str | None = None
    session_type: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    external_transaction_id: str | None = None
    total_consumption_kwh: float = 0.0
    external_id: str | None = None

    @property
    def is_active(self) -> bool:
        return self.end_time is None

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> ChargingSession:
        return cls(
            id=_int(_value(data, "id")) or 0,
            charge_point_id=_text(_value(data, "chargePointId")),
            connector_id=_int(_value(data, "connectorId")) or 0,
            user_id=_text(_value(data, "userId")),
            rfid=_text(_value(data, "rfid")),
            rfid_dec=_text(_value(data, "rfidDec")),
            rfid_dec_reverse=_text(_value(data, "rfidDecReverse")),
            organisation_id=_text(_value(data, "organisationId")),
            session_type=_text(_value(data, "sessionType")),
            start_time=_datetime(_value(data, "startTime")),
            end_time=_datetime(_value(data, "endTime")),
            external_transaction_id=_text(_value(data, "externalTransactionId")),
            total_consumption_kwh=_float(_value(data, "totalConsumptionKwh")) or 0.0,
            external_id=_text(_value(data, "externalId")),
        )


@dataclass(slots=True)
class RfidTag:
    """An RFID tag stored on a user or organisation."""

    active: bool = True
    rfid: str | None = None
    rfid_dec: str | None = None
    rfid_dec_reverse: str | None = None

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> RfidTag:
        return cls(
            active=_bool(_value(data, "active"), default=True),
            rfid=_text(_value(data, "rfid")),
            rfid_dec=_text(_value(data, "rfidDec")),
            rfid_dec_reverse=_text(_value(data, "rfidDecReverse")),
        )


@dataclass(slots=True)
class User:
    """A Charge Amps user."""

    id: str
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    mobile: str | None = None
    rfid_tags: list[RfidTag] = field(default_factory=list)
    user_status: str | None = None

    @property
    def name(self) -> str:
        parts = [self.first_name, self.last_name]
        return " ".join(part for part in parts if part) or self.email or self.id

    def first_active_tag(self) -> RfidTag | None:
        for tag in self.rfid_tags:
            if tag.active and tag.rfid:
                return tag
        for tag in self.rfid_tags:
            if tag.rfid:
                return tag
        return None

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> User:
        tags = _value(data, "rfidTags", default=[])
        return cls(
            id=str(_value(data, "id", default="")),
            first_name=_text(_value(data, "firstName")),
            last_name=_text(_value(data, "lastName")),
            email=_text(_value(data, "email")),
            mobile=_text(_value(data, "mobile")),
            rfid_tags=[RfidTag.from_api(_as_dict(tag)) for tag in tags if isinstance(tag, Mapping)],
            user_status=_text(_value(data, "userStatus")),
        )


@dataclass(slots=True)
class Organisation:
    """A Charge Amps organisation."""

    id: str
    name: str | None = None
    description: str | None = None

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> Organisation:
        return cls(
            id=str(_value(data, "id", default="")),
            name=_text(_value(data, "name")),
            description=_text(_value(data, "description")),
        )


@dataclass(slots=True)
class Partner:
    """A partner connected to a charge point or organisation."""

    id: str
    name: str | None = None
    description: str | None = None
    email: str | None = None
    phone: str | None = None

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> Partner:
        return cls(
            id=str(_value(data, "id", default="")),
            name=_text(_value(data, "name")),
            description=_text(_value(data, "description")),
            email=_text(_value(data, "email")),
            phone=_text(_value(data, "phone")),
        )


@dataclass(slots=True)
class Schedule:
    """A weekly charging schedule."""

    id: int
    charge_point_id: str | None = None
    name: str | None = None
    active: bool = True
    start_hours: int = 0
    start_minutes: int = 0
    end_hours: int = 0
    end_minutes: int = 0
    time_zone: str | None = None
    monday: bool = False
    tuesday: bool = False
    wednesday: bool = False
    thursday: bool = False
    friday: bool = False
    saturday: bool = False
    sunday: bool = False
    connector_id_list: str | None = None

    def to_api(self, *, include_id: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chargePointId": self.charge_point_id,
            "name": self.name,
            "active": self.active,
            "startHours": self.start_hours,
            "startMinutes": self.start_minutes,
            "endHours": self.end_hours,
            "endMinutes": self.end_minutes,
            "timeZone": self.time_zone,
            "monday": self.monday,
            "tuesday": self.tuesday,
            "wednesday": self.wednesday,
            "thursday": self.thursday,
            "friday": self.friday,
            "saturday": self.saturday,
            "sunday": self.sunday,
            "connectorIdList": self.connector_id_list,
        }
        if include_id and self.id:
            payload["id"] = self.id
        return payload

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> Schedule:
        return cls(
            id=_int(_value(data, "id")) or 0,
            charge_point_id=_text(_value(data, "chargePointId")),
            name=_text(_value(data, "name")),
            active=_bool(_value(data, "active"), default=True),
            start_hours=_int(_value(data, "startHours")) or 0,
            start_minutes=_int(_value(data, "startMinutes")) or 0,
            end_hours=_int(_value(data, "endHours")) or 0,
            end_minutes=_int(_value(data, "endMinutes")) or 0,
            time_zone=_text(_value(data, "timeZone")),
            monday=_bool(_value(data, "monday")),
            tuesday=_bool(_value(data, "tuesday")),
            wednesday=_bool(_value(data, "wednesday")),
            thursday=_bool(_value(data, "thursday")),
            friday=_bool(_value(data, "friday")),
            saturday=_bool(_value(data, "saturday")),
            sunday=_bool(_value(data, "sunday")),
            connector_id_list=_text(_value(data, "connectorIdList")),
        )


@dataclass(slots=True)
class ScheduleOverrideStatus:
    """Whether a connector currently overrides its schedule."""

    connector_id: int
    is_overridden: bool = False

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> ScheduleOverrideStatus:
        return cls(
            connector_id=_int(_value(data, "connectorId")) or 0,
            is_overridden=_bool(_value(data, "isOverridden")),
        )


@dataclass(slots=True)
class StartAuth:
    """Payload for a remote start."""

    rfid: str
    rfid_format: str = "Hex"
    rfid_length: int = 4
    external_transaction_id: str | None = None

    def to_api(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "rfid": self.rfid,
            "rfidFormat": self.rfid_format,
            "rfidLength": self.rfid_length,
        }
        if self.external_transaction_id:
            payload["externalTransactionId"] = self.external_transaction_id
        return payload
