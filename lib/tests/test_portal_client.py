"""Tests for the portal-session client."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from chargeamps_cloud import ChargeAmpsPortalClient
from chargeamps_cloud.models import ConnectorSettings

PORTAL = "/api"
LOGIN = f"{PORTAL}/auth/login"
CURRENT = f"{PORTAL}/auth/current"
CSRF = f"{PORTAL}/csrf/handshake"
OWNED = f"{PORTAL}/users/chargepoints/owned"
DETAIL = f"{PORTAL}/chargepoints/cp-1"
START = f"{PORTAL}/chargepoints/cp-1/1/remotestart"
STOP = f"{PORTAL}/chargepoints/cp-1/1/remotestop"
TAGS = f"{PORTAL}/chargepoints/cp-1/1/remotestart/tags"
SESSIONS = f"{PORTAL}/chargepoints/cp-1/chargingsessions"
CHARGE_POINT: dict[str, Any] = {
    "id": "cp-1",
    "name": "Driveway",
    "productName": "Halo",
    "productType": "Halo1",
    "installedFirmwareVersion": "1.2.3",
    "hardwareVersion": "Halo",
    "isOcpp": True,
    "ownerReadOnly": False,
    "chargePointStatus": "Charging",
    "dimmer": 2,
    "downLight": True,
    "connectors": [
        {
            "connectorId": 1,
            "connectorFunctionType": "Charger",
            "mode": "On",
            "nfcLocked": True,
            "cableLocked": False,
            "userCurrent": 16,
            "installationCurrent": 16,
            "current1": 10.6,
            "voltage1": 231,
            "current2": 10.5,
            "voltage2": 230,
            "current3": 10.7,
            "voltage3": 232,
            "totalConsumptionKwh": 5.42,
            "isCharging": True,
            "ocppStatus": "Charging",
            "sessionType": "ThreePhase",
            "defaultNfcTagId": "A1B2C3D4",
        }
    ],
}
AUTH_CURRENT = {
    "user": {
        "id": "user-1",
        "firstName": "Test",
        "lastName": "User",
        "email": "test@example.com",
    },
    "csrfRequired": True,
    "expiresAtUtc": "2026-10-28T22:00:00Z",
}


def add_login(api: Any) -> None:
    api.add(
        "POST",
        LOGIN,
        body="",
        headers={"Set-Cookie": "portal-session=abc; Path=/; HttpOnly"},
    )
    api.add("GET", CURRENT, payload=AUTH_CURRENT)
    api.add("GET", CSRF, body="", headers={"X-CSRF-TOKEN": "csrf-token"})


async def test_portal_login_and_chargepoint(api: Any) -> None:
    add_login(api)
    api.add("GET", OWNED, payload=[CHARGE_POINT])
    api.add("GET", DETAIL, payload=CHARGE_POINT)
    async with ChargeAmpsPortalClient("test@example.com", "secret", base_url=f"{api.base_url}{PORTAL}") as client:
        assert client.user is not None
        assert client.user.email == "test@example.com"
        chargepoints = await client.get_chargepoints()
        assert chargepoints[0].id == "cp-1"
        assert chargepoints[0].connectors[0].connector_id == 1
        assert chargepoints[0].ocpp_version == "OCPP"

        status = await client.get_chargepoint_status("cp-1")
        connector = status.connector(1)
        assert connector is not None
        assert connector.status == "Charging"
        assert connector.is_plugged_in is True
        assert connector.power_w == 7346.0
        assert connector.total_consumption_kwh == 5.42

        settings = await client.get_connector_settings("cp-1", 1)
        assert settings.mode == "On"
        assert settings.rfid_lock is True
        assert settings.max_current == 16

    login_request = api.last("POST", LOGIN)
    assert login_request.headers["Origin"] == "https://my.charge.space"


async def test_portal_settings_update(api: Any) -> None:
    add_login(api)
    api.add("GET", DETAIL, payload=CHARGE_POINT, repeat=2)
    api.add("PUT", f"{PORTAL}/chargepoints", body="")
    async with ChargeAmpsPortalClient("e", "p", base_url=f"{api.base_url}{PORTAL}") as client:
        settings = ConnectorSettings.from_api(
            {
                "chargePointId": "cp-1",
                "connectorId": 1,
                "mode": "Off",
                "rfidLock": False,
                "cableLock": True,
                "maxCurrent": 10,
            }
        )
        await client.set_connector_settings(settings)

    request = api.last("PUT", f"{PORTAL}/chargepoints")
    assert request.headers["X-CSRF-TOKEN"] == "csrf-token"
    connector = request.json["connectors"][0]
    assert connector["mode"] == "Off"
    assert connector["nfcLocked"] is False
    assert connector["cableLocked"] is True
    assert connector["userCurrent"] == 10


async def test_portal_remote_start_uses_default_tag(api: Any) -> None:
    add_login(api)
    api.add("GET", DETAIL, payload=CHARGE_POINT, repeat=2)
    api.add("PUT", START, body="")
    async with ChargeAmpsPortalClient("e", "p", base_url=f"{api.base_url}{PORTAL}") as client:
        start = await client.remote_start("cp-1", 1)
    assert start.rfid == "A1B2C3D4"
    assert api.last("PUT", START).query["rfidTag"] == "A1B2C3D4"


async def test_portal_remote_start_with_explicit_tag(api: Any) -> None:
    add_login(api)
    api.add("PUT", START, body="")
    async with ChargeAmpsPortalClient("e", "p", base_url=f"{api.base_url}{PORTAL}") as client:
        await client.remote_start("cp-1", 1, rfid="BEEF")
    assert api.last("PUT", START).query["rfidTag"] == "BEEF"


async def test_portal_sessions_and_tags(api: Any) -> None:
    add_login(api)
    api.add(
        "GET",
        SESSIONS,
        payload={
            "totalCount": 1,
            "sessions": [
                {
                    "id": 42,
                    "chargePointId": "cp-1",
                    "connectorId": 1,
                    "userId": "user-1",
                    "nfcUid": "A1B2C3D4",
                    "sessionType": "ThreePhase",
                    "startTime": "2026-10-27T18:00:00+01:00",
                    "endTime": None,
                    "totalConsumptionKwh": 5.42,
                }
            ],
        },
    )
    api.add("GET", f"{PORTAL}/users/nfctags/own", payload=[{"id": "A1B2C3D4", "active": True}])
    async with ChargeAmpsPortalClient("e", "p", base_url=f"{api.base_url}{PORTAL}") as client:
        sessions = await client.get_charging_sessions("cp-1")
        assert sessions[0].rfid == "A1B2C3D4"
        assert sessions[0].is_active is True
        tags = await client.get_rfids()
        assert tags[0].rfid == "A1B2C3D4"


async def test_portal_remote_stop(api: Any) -> None:
    add_login(api)
    api.add("PUT", STOP, body="")
    async with ChargeAmpsPortalClient("e", "p", base_url=f"{api.base_url}{PORTAL}") as client:
        await client.remote_stop("cp-1", 1)
    assert api.last("PUT", STOP).headers["X-CSRF-TOKEN"] == "csrf-token"


async def test_portal_login_uses_bearer_token(api: Any) -> None:
    api.add(
        "POST",
        LOGIN,
        payload={
            "message": "Login succeeded",
            "token": "portal-jwt",
            "refreshToken": "portal-refresh",
            "user": AUTH_CURRENT["user"],
        },
    )
    api.add("GET", OWNED, payload=[CHARGE_POINT])
    async with ChargeAmpsPortalClient("e", "p", base_url=f"{api.base_url}{PORTAL}") as client:
        assert client.user is not None
        await client.get_chargepoints()
    assert api.last("GET", OWNED).headers["Authorization"] == "Bearer portal-jwt"
    assert not api.requests_for("GET", CSRF)


async def test_portal_remote_start_ignores_placeholder_default(api: Any) -> None:
    chargepoint = deepcopy(CHARGE_POINT)
    chargepoint["connectors"][0]["defaultNfcTagId"] = "00000000000000"
    add_login(api)
    api.add("GET", DETAIL, payload=chargepoint, repeat=2)
    api.add("GET", TAGS, payload=[{"id": "REALTAG", "active": True}])
    api.add("PUT", START, body="")
    async with ChargeAmpsPortalClient("e", "p", base_url=f"{api.base_url}{PORTAL}") as client:
        start = await client.remote_start("cp-1", 1)
    assert start.rfid == "REALTAG"
    assert api.last("PUT", START).query["rfidTag"] == "REALTAG"
