"""Setup tests for Charge Amps Cloud."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chargeamps_cloud.chargeamps_cloud import (
    ChargePoint,
    ChargePointSettings,
    ChargePointStatus,
    ChargingSession,
    Connector,
    ConnectorSettings,
    ConnectorStatus,
    Measurement,
    RfidTag,
    User,
)
from custom_components.chargeamps_cloud.const import CONF_API_KEY, CONF_EMAIL, CONF_PASSWORD, DOMAIN

CHARGE_POINT_ID = "cp-1"
START = datetime(2026, 10, 27, 18, 0, tzinfo=UTC)


class FakeClient:
    """Minimal stand-in for ChargeAmpsClient."""

    def __init__(self, *args, **kwargs) -> None:
        self.user = User(
            id="user-1",
            email="test@example.com",
            first_name="Test",
            rfid_tags=[RfidTag(active=True, rfid="A1B2C3D4")],
        )
        self.chargepoint = ChargePoint(
            id=CHARGE_POINT_ID,
            name="Driveway",
            type="Halo",
            firmware_version="1.2.3",
            ocpp_version="1.6",
            connectors=[Connector(connector_id=1, charge_point_id=CHARGE_POINT_ID, type="Charger")],
        )
        self.status = ChargePointStatus(
            id=CHARGE_POINT_ID,
            status="Online",
            connector_statuses=[
                ConnectorStatus(
                    charge_point_id=CHARGE_POINT_ID,
                    connector_id=1,
                    status="Charging",
                    total_consumption_kwh=5.42,
                    charging_power_kw=7.36,
                    session_type="ThreePhase",
                    measurements=[
                        Measurement(phase="L1", current=10.6, voltage=231),
                        Measurement(phase="L2", current=10.5, voltage=230),
                        Measurement(phase="L3", current=10.7, voltage=232),
                    ],
                    start_time=START,
                    session_id=42,
                )
            ],
        )
        self.session = ChargingSession(
            id=42,
            charge_point_id=CHARGE_POINT_ID,
            connector_id=1,
            rfid="A1B2C3D4",
            start_time=START,
            total_consumption_kwh=5.42,
        )
        self.settings = ChargePointSettings(id=CHARGE_POINT_ID, dimmer="Medium", max_current=16)
        self.connector_settings = ConnectorSettings(
            charge_point_id=CHARGE_POINT_ID,
            connector_id=1,
            mode="On",
            rfid_lock=True,
            cable_lock=False,
            max_current=16,
            installation_current=16,
        )
        self.calls: list[tuple[str, tuple, dict]] = []

    async def login(self):
        return self.user

    async def get_chargepoints(self):
        return [self.chargepoint]

    async def get_chargepoint_status(self, chargepoint_id):
        return self.status

    async def get_chargepoint_settings(self, chargepoint_id):
        return self.settings

    async def get_connector_settings(self, chargepoint_id, connector_id):
        return self.connector_settings

    async def get_charging_sessions(self, chargepoint_id, **kwargs):
        return [self.session]

    async def get_charging_session(self, chargepoint_id, session_id):
        return self.session

    async def get_default_rfid(self, allow_placeholder=True):
        return self.user.rfid_tags[0]

    async def remote_start(self, *args, **kwargs):
        self.calls.append(("remote_start", args, kwargs))

    async def remote_stop(self, *args, **kwargs):
        self.calls.append(("remote_stop", args, kwargs))

    async def set_connector_settings(self, settings):
        self.calls.append(("set_connector_settings", (settings,), {}))

    async def reboot(self, chargepoint_id):
        self.calls.append(("reboot", (chargepoint_id,), {}))

    async def close(self):
        pass


async def test_setup_creates_entities(hass, enable_custom_integrations) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: "test@example.com", CONF_PASSWORD: "secret", CONF_API_KEY: "api-key"},
        options={},
        unique_id="user-1",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.chargeamps_cloud.ChargeAmpsClient", FakeClient):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.driveway_status").state == "Online"
    assert hass.states.get("binary_sensor.driveway_charger_car_connected").state == "on"
    assert hass.states.get("sensor.driveway_charger_connector_status").state == "Charging"
    assert hass.states.get("sensor.driveway_charger_power").state == "7360.0"
    assert hass.states.get("sensor.driveway_charger_session_energy").state == "5.42"
    assert hass.states.get("sensor.driveway_charger_current_l1").state == "10.6"
    assert hass.states.get("sensor.driveway_charger_voltage_l3").state == "232"
    assert hass.states.get("sensor.driveway_charger_session_rfid").state == "A1B2C3D4"
    assert hass.states.get("switch.driveway_charger_charging_enabled").state == "on"
    assert hass.states.get("switch.driveway_charger_rfid_lock").state == "on"
    assert hass.states.get("number.driveway_charger_maximum_current").state == "16"
    assert hass.states.get("lock.driveway_charger_cable_lock").state == "unlocked"
    assert hass.states.get("button.driveway_charger_start_charging") is not None
    assert hass.services.has_service(DOMAIN, "start_charging")

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_services_target_connector(hass, enable_custom_integrations) -> None:
    from homeassistant.helpers import device_registry as dr

    from custom_components.chargeamps_cloud.const import connector_identifier

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: "test@example.com", CONF_PASSWORD: "secret", CONF_API_KEY: "api-key"},
        options={},
        unique_id="user-1",
    )
    entry.add_to_hass(hass)
    client = FakeClient()
    with patch("custom_components.chargeamps_cloud.ChargeAmpsClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        registry = dr.async_get(hass)
        identifier = connector_identifier(CHARGE_POINT_ID, 1)
        if hasattr(registry, "async_get_device_by_identifier"):
            connector_device = registry.async_get_device_by_identifier(identifier, entry.entry_id)
        else:
            connector_device = registry.async_get_device(identifiers={identifier})
        assert connector_device is not None

        await hass.services.async_call(DOMAIN, "start_charging", {"device_id": connector_device.id}, blocking=True)
        assert client.calls[-1][0] == "remote_start"
        assert client.calls[-1][2]["rfid"] == "A1B2C3D4"

        await hass.services.async_call(
            DOMAIN, "set_current", {"device_id": connector_device.id, "current": 10}, blocking=True
        )
        assert client.calls[-1][0] == "set_connector_settings"
        assert client.calls[-1][1][0].max_current == 10

        await hass.services.async_call(
            DOMAIN, "set_mode", {"device_id": connector_device.id, "mode": "Off"}, blocking=True
        )
        assert client.calls[-1][1][0].mode == "Off"

        await hass.services.async_call(DOMAIN, "stop_charging", {"device_id": connector_device.id}, blocking=True)
        assert client.calls[-1][0] == "remote_stop"

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_uses_portal_without_api_key(hass, enable_custom_integrations) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: "test@example.com", CONF_PASSWORD: "secret", CONF_API_KEY: ""},
        options={},
        unique_id="user-1",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.chargeamps_cloud.ChargeAmpsPortalClient", FakeClient):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.driveway_status").state == "Online"

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
