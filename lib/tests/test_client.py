"""Tests for the Charge Amps Cloud client."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from chargeamps_cloud import (
    ChargeAmpsAuthError,
    ChargeAmpsClient,
    ChargeAmpsForbiddenError,
    ChargeAmpsNotFoundError,
    ChargeAmpsRateLimitError,
)
from chargeamps_cloud.models import ConnectorSettings

TEST_API_KEY = "test-api-key"
BASE = "/api/v5"
LOGIN = f"{BASE}/auth/login"
REFRESH = f"{BASE}/auth/refreshtoken"
OWNED = f"{BASE}/chargepoints/owned"


def make_client(api: Any, login_payload: dict[str, Any]) -> ChargeAmpsClient:
    api.add("POST", LOGIN, payload=login_payload)
    return ChargeAmpsClient("test@example.com", "secret", TEST_API_KEY, base_url=api.base_url)


async def test_login_sends_api_key_and_parses_user(api: Any, login_payload: dict[str, Any]) -> None:
    async with make_client(api, login_payload) as client:
        assert client.user is not None
        assert client.user.email == "test@example.com"
        assert client.user.rfid_tags[0].rfid == "A1B2C3D4"

    request = api.last("POST", LOGIN)
    assert request.headers["apiKey"] == TEST_API_KEY
    assert request.json == {"email": "test@example.com", "password": "secret"}


async def test_api_key_is_required() -> None:
    with pytest.raises(ValueError, match="API key"):
        ChargeAmpsClient("test@example.com", "secret", "")


async def test_login_without_api_key_is_rejected(api: Any) -> None:
    api.add("POST", LOGIN, status=401, body="API key is missing in headers!")
    with pytest.raises(ChargeAmpsAuthError, match="API key is missing"):
        async with ChargeAmpsClient("test@example.com", "secret", TEST_API_KEY, base_url=api.base_url):
            pass


async def test_chargepoints_are_parsed(
    api: Any, login_payload: dict[str, Any], chargepoints_payload: list[dict[str, Any]]
) -> None:
    api.add("GET", OWNED, payload=chargepoints_payload)
    async with make_client(api, login_payload) as client:
        chargepoints = await client.get_chargepoints()
    assert len(chargepoints) == 1
    assert chargepoints[0].name == "Driveway"
    assert chargepoints[0].connectors[0].connector_id == 1
    assert chargepoints[0].ocpp_version == "1.6"


async def test_chargepoints_fall_back_to_organisations(
    api: Any, login_payload: dict[str, Any], chargepoints_payload: list[dict[str, Any]]
) -> None:
    api.add("GET", OWNED, payload=[])
    api.add("GET", f"{BASE}/organisations", payload=[{"id": "org-1", "name": "Housing"}])
    api.add("GET", f"{BASE}/organisations/org-1/chargepoints", payload=chargepoints_payload)
    async with make_client(api, login_payload) as client:
        chargepoints = await client.get_chargepoints()
    assert [chargepoint.id for chargepoint in chargepoints] == [chargepoints_payload[0]["id"]]


async def test_refresh_is_used_when_token_expires(
    api: Any, login_payload: dict[str, Any], chargepoints_payload: list[dict[str, Any]]
) -> None:
    new_token = "header.eyJleHAiOjQxMDI0NDQ4MDB9.new"
    api.add("POST", REFRESH, payload={"token": new_token, "refreshToken": "refresh-token-2"})
    api.add("GET", OWNED, payload=chargepoints_payload)
    async with make_client(api, login_payload) as client:
        client._token_expires_at = 0  # type: ignore[attr-defined]
        await client.get_chargepoints()
    refresh_request = api.last("POST", REFRESH)
    assert refresh_request.json == {
        "token": login_payload["token"],
        "refreshToken": login_payload["refreshToken"],
    }
    assert api.last("GET", OWNED).headers["Authorization"] == f"Bearer {new_token}"


async def test_401_triggers_a_new_login(
    api: Any, login_payload: dict[str, Any], chargepoints_payload: list[dict[str, Any]]
) -> None:
    api.add("GET", OWNED, status=401, body="expired")
    api.add("POST", LOGIN, payload=login_payload)
    api.add("GET", OWNED, payload=chargepoints_payload)
    async with make_client(api, login_payload) as client:
        chargepoints = await client.get_chargepoints()
    assert chargepoints
    assert len(api.requests_for("POST", LOGIN)) == 2


async def test_remote_start_uses_first_active_tag(api: Any, login_payload: dict[str, Any]) -> None:
    url = f"{BASE}/chargepoints/cp-1/connectors/1/remotestart"
    api.add("PUT", url, body="")
    async with make_client(api, login_payload) as client:
        start = await client.remote_start("cp-1", 1)
    assert start.rfid == "A1B2C3D4"
    assert api.last("PUT", url).json == {
        "rfid": "A1B2C3D4",
        "rfidFormat": "Hex",
        "rfidLength": 4,
    }


async def test_remote_start_can_use_placeholder_tag(api: Any, login_payload: dict[str, Any]) -> None:
    login_payload["user"]["rfidTags"] = []
    url = f"{BASE}/chargepoints/cp-1/connectors/1/remotestart"
    api.add("GET", f"{BASE}/users/{login_payload['user']['id']}", payload=login_payload["user"])
    api.add("PUT", url, body="")
    async with make_client(api, login_payload) as client:
        start = await client.remote_start("cp-1", 1)
    assert start.rfid == "00000000000000"


async def test_connector_settings_put(
    api: Any, login_payload: dict[str, Any], connector_settings_payload: dict[str, Any]
) -> None:
    url = f"{BASE}/chargepoints/{connector_settings_payload['chargePointId']}/connectors/1/settings"
    api.add("PUT", url, body="")
    async with make_client(api, login_payload) as client:
        settings = ConnectorSettings.from_api(connector_settings_payload)
        settings.max_current = 10
        await client.set_connector_settings(settings)
    assert api.last("PUT", url).json["maxCurrent"] == 10


async def test_not_found_and_forbidden_are_mapped(api: Any, login_payload: dict[str, Any]) -> None:
    api.add("GET", OWNED, status=403, body="forbidden")
    async with make_client(api, login_payload) as client:
        with pytest.raises(ChargeAmpsForbiddenError):
            await client.get_owned_chargepoints()

    api.add("GET", OWNED, status=404, body="not found")
    async with make_client(api, login_payload) as client:
        with pytest.raises(ChargeAmpsNotFoundError):
            await client.get_owned_chargepoints()


async def test_rate_limit_keeps_retry_after(api: Any, login_payload: dict[str, Any]) -> None:
    api.add("GET", OWNED, status=429, body="slow down", headers={"Retry-After": "60"})
    async with make_client(api, login_payload) as client:
        with pytest.raises(ChargeAmpsRateLimitError) as error:
            await client.get_owned_chargepoints()
    assert error.value.retry_after == 60


async def test_sessions_parse_times(
    api: Any, login_payload: dict[str, Any], sessions_payload: list[dict[str, Any]]
) -> None:
    url = f"{BASE}/chargepoints/cp-1/chargingsessions"
    api.add("GET", url, payload=sessions_payload)
    async with make_client(api, login_payload) as client:
        sessions = await client.get_charging_sessions("cp-1", start_time=datetime(2026, 10, 1, tzinfo=UTC))
    assert sessions[0].start_time == datetime(2026, 10, 27, 17, 0, tzinfo=UTC)
    assert sessions[0].is_active is True
    assert sessions[0].rfid == "A1B2C3D4"
    assert "startTime" in api.last("GET", url).query


async def test_request_sends_json(api: Any, login_payload: dict[str, Any]) -> None:
    url = f"{BASE}/chargepoints/cp-1/reboot"
    api.add("PUT", url, body="")
    async with make_client(api, login_payload) as client:
        await client.reboot("cp-1")
    assert api.last("PUT", url).json == {}
