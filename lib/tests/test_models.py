"""Tests for the API models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from chargeamps_cloud.client import _decode_jwt_exp
from chargeamps_cloud.const import normalize_status
from chargeamps_cloud.models import (
    ChargePoint,
    ChargePointSettings,
    ChargePointStatus,
    ChargingSession,
    ConnectorSettings,
    RfidTag,
    Schedule,
    StartAuth,
    User,
)


def test_chargepoint_parsing(chargepoints_payload: list[dict[str, Any]]) -> None:
    chargepoint = ChargePoint.from_api(chargepoints_payload[0])
    assert chargepoint.name == "Driveway"
    assert chargepoint.firmware_version == "1.2.3"
    assert chargepoint.connectors[0].type == "Charger"
    assert chargepoint.is_capi is False


def test_settings_roundtrip() -> None:
    settings = ChargePointSettings.from_api(
        {"id": "cp", "dimmer": "Low", "downLight": False, "maxCurrent": 10, "installationCurrent": 16}
    )
    payload = settings.to_api()
    assert payload["dimmer"] == "Low"
    assert payload["downLight"] is False
    assert payload["maxCurrent"] == 10
    assert "installationCurrent" not in payload

    connector = ConnectorSettings.from_api(
        {
            "chargePointId": "cp",
            "connectorId": 2,
            "mode": "On",
            "rfidLock": True,
            "cableLock": False,
            "maxCurrent": 8,
            "installationCurrent": 16,
        }
    )
    assert connector.to_api()["connectorId"] == 2
    assert connector.to_api()["rfidLock"] is True
    assert "installationCurrent" not in connector.to_api()


def test_status_normalization() -> None:
    assert normalize_status("SuspendedEV") == "SuspendedEV"
    assert normalize_status("suspendedev") == "SuspendedEV"
    assert normalize_status("1") == "Charging"
    assert normalize_status(1) == "Charging"
    assert normalize_status("something new") == "Unknown"
    assert normalize_status(None) == "Unknown"


def test_connector_status(chargepoints_payload: list[dict[str, Any]], status_payload: dict[str, Any]) -> None:
    status = ChargePointStatus.from_api(status_payload)
    assert status.is_online is True
    connector = status.connector(1)
    assert connector is not None
    assert connector.status == "Charging"
    assert connector.is_plugged_in is True
    assert connector.power_w == 7360.0
    assert connector.measurement("L2", "current") == 10.5
    assert connector.measurement("L2", "voltage") == 230.0
    assert connector.measurement("L9", "voltage") is None


def test_capi_status() -> None:
    status = ChargePointStatus.from_api(
        {
            "id": "cp",
            "status": "Online",
            "connectorStatuses": [{"chargePointId": "cp", "connectorId": 1, "status": "2", "totalConsumptionKwh": 1.0}],
        }
    )
    connector = status.connector(1)
    assert connector is not None
    assert connector.status == "Connected"
    assert connector.is_plugged_in is True


def test_session_parsing(sessions_payload: list[dict[str, Any]]) -> None:
    session = ChargingSession.from_api(sessions_payload[0])
    assert session.is_active is True
    assert session.start_time == datetime(2026, 10, 27, 17, 0, tzinfo=UTC)
    assert session.rfid == "A1B2C3D4"


def test_user_prefers_active_tag() -> None:
    user = User.from_api(
        {
            "id": "u",
            "rfidTags": [
                {"active": False, "rfid": "INACTIVE"},
                {"active": True, "rfid": "ACTIVE"},
            ],
        }
    )
    tag = user.first_active_tag()
    assert tag is not None
    assert tag.rfid == "ACTIVE"
    assert user.name == "u"


def test_user_without_tags() -> None:
    user = User.from_api({"id": "u", "email": "a@b.c"})
    assert user.first_active_tag() is None
    assert user.name == "a@b.c"


def test_schedule_to_api() -> None:
    schedule = Schedule.from_api(
        {
            "id": 3,
            "chargePointId": "cp",
            "name": "Night",
            "active": True,
            "startHours": 22,
            "startMinutes": 30,
            "endHours": 6,
            "endMinutes": 0,
            "timeZone": "Europe/Berlin",
            "monday": True,
            "connectorIdList": "1",
        }
    )
    payload = schedule.to_api()
    assert payload["startHours"] == 22
    assert payload["monday"] is True
    assert payload["id"] == 3
    assert "id" not in schedule.to_api(include_id=False)


def test_start_auth_payload() -> None:
    auth = StartAuth(rfid="A1B2C3D4", rfid_length=4)
    assert auth.to_api() == {"rfid": "A1B2C3D4", "rfidFormat": "Hex", "rfidLength": 4}
    with_external = StartAuth(rfid="A1B2C3D4", external_transaction_id="tx")
    assert with_external.to_api()["externalTransactionId"] == "tx"


def test_rfid_tag_defaults() -> None:
    tag = RfidTag.from_api({"rfid": "A1B2C3D4"})
    assert tag.active is True


def test_jwt_without_exp() -> None:
    assert _decode_jwt_exp("not-a-token") is None
