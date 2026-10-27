"""Config flow tests for Charge Amps Cloud."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries, data_entry_flow

from custom_components.chargeamps_cloud.chargeamps_cloud import ChargeAmpsAuthError, User
from custom_components.chargeamps_cloud.const import CONF_API_KEY, CONF_EMAIL, CONF_PASSWORD, DOMAIN

USER_INPUT = {
    CONF_EMAIL: "test@example.com",
    CONF_PASSWORD: "secret",
    CONF_API_KEY: "api-key",
}


async def test_user_flow_creates_entry(hass, enable_custom_integrations) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is data_entry_flow.FlowResultType.FORM

    with patch("custom_components.chargeamps_cloud.config_flow.ChargeAmpsClient") as client_class:
        client = client_class.return_value
        client.login = AsyncMock()
        client.get_chargepoints = AsyncMock(return_value=[object()])
        client.user = User(id="user-1", email="test@example.com", first_name="Test")
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test"
    assert result["data"] == USER_INPUT


async def test_user_flow_rejects_invalid_auth(hass, enable_custom_integrations) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch("custom_components.chargeamps_cloud.config_flow.ChargeAmpsClient") as client_class:
        client = client_class.return_value
        client.login = AsyncMock(side_effect=ChargeAmpsAuthError("nope"))
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_requires_chargepoints(hass, enable_custom_integrations) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch("custom_components.chargeamps_cloud.config_flow.ChargeAmpsClient") as client_class:
        client = client_class.return_value
        client.login = AsyncMock()
        client.get_chargepoints = AsyncMock(return_value=[])
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "no_chargepoints"}
