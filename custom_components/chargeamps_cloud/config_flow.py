"""Config flow for Charge Amps Cloud."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .chargeamps_cloud import ChargeAmpsAuthError, ChargeAmpsClient, ChargeAmpsConnectionError, ChargeAmpsError
from .const import (
    CONF_API_KEY,
    CONF_EMAIL,
    CONF_ORGANISATION_ID,
    CONF_PASSWORD,
    CONF_RFID,
    CONF_RFID_FORMAT,
    CONF_RFID_LENGTH,
    CONF_SCAN_INTERVAL,
    DEFAULT_RFID_FORMAT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    RFID_FORMAT_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)


def _credentials_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_EMAIL, default=defaults.get(CONF_EMAIL, "")): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
            ),
            vol.Required(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_API_KEY): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Optional(CONF_ORGANISATION_ID, default=defaults.get(CONF_ORGANISATION_ID, "")): selector.TextSelector(),
        }
    )


async def _validate(hass: HomeAssistant, data: dict[str, Any]) -> tuple[str, str]:
    """Validate credentials and return ``(title, unique_id)``."""
    client = ChargeAmpsClient(
        data[CONF_EMAIL],
        data[CONF_PASSWORD],
        data[CONF_API_KEY],
        session=async_get_clientsession(hass),
        organisation_id=data.get(CONF_ORGANISATION_ID) or None,
    )
    await client.login()
    chargepoints = await client.get_chargepoints()
    if not chargepoints:
        raise ValueError("no_chargepoints")
    user = client.user
    unique_id = user.id if user and user.id else data[CONF_EMAIL].lower()
    title = user.name if user and user.name else data[CONF_EMAIL]
    return title, unique_id


class ChargeAmpsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the configuration flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = dict(user_input)
            if not data.get(CONF_ORGANISATION_ID):
                data.pop(CONF_ORGANISATION_ID, None)
            try:
                title, unique_id = await _validate(self.hass, data)
            except ChargeAmpsAuthError:
                errors["base"] = "invalid_auth"
            except ChargeAmpsConnectionError:
                errors["base"] = "cannot_connect"
            except ValueError as err:
                errors["base"] = str(err)
            except ChargeAmpsError as err:
                _LOGGER.debug("Unexpected Charge Amps error: %s", err)
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=title, data=data)
        return self.async_show_form(step_id="user", data_schema=_credentials_schema(user_input), errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {
                **entry.data,
                CONF_PASSWORD: user_input[CONF_PASSWORD],
                CONF_API_KEY: user_input[CONF_API_KEY],
            }
            try:
                title, _unique_id = await _validate(self.hass, data)
            except ChargeAmpsAuthError:
                errors["base"] = "invalid_auth"
            except ChargeAmpsConnectionError:
                errors["base"] = "cannot_connect"
            except ValueError as err:
                errors["base"] = str(err)
            except ChargeAmpsError:
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(entry, data=data, title=title)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                    vol.Required(CONF_API_KEY): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
            description_placeholders={"email": entry.data.get(CONF_EMAIL, "")},
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ChargeAmpsOptionsFlow()


class ChargeAmpsOptionsFlow(OptionsFlow):
    """Options for polling and remote start."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            data = dict(user_input)
            if data.get(CONF_RFID_LENGTH) == "auto":
                data[CONF_RFID_LENGTH] = None
            elif data.get(CONF_RFID_LENGTH) not in (None, ""):
                data[CONF_RFID_LENGTH] = int(data[CONF_RFID_LENGTH])
            return self.async_create_entry(title="", data=data)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=5,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                    vol.Optional(CONF_RFID, default=options.get(CONF_RFID, "")): selector.TextSelector(),
                    vol.Optional(
                        CONF_RFID_FORMAT,
                        default=options.get(CONF_RFID_FORMAT, DEFAULT_RFID_FORMAT),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(RFID_FORMAT_OPTIONS), mode=selector.SelectSelectorMode.DROPDOWN
                        )
                    ),
                    vol.Optional(
                        CONF_RFID_LENGTH,
                        default=str(options.get(CONF_RFID_LENGTH) or "auto"),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=["auto", "4", "7", "10"],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )
