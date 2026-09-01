"""Config Flow for Ovum MIRA integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from .const import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGIN_ADDRESS,
    LOGIN_PAYLOAD,
    SLAVE_HSM,
    Level,
)
from .coordinator import (
    CONF_COOLING,
    CONF_HOST,
    CONF_LEVEL,
    CONF_NUM_HK,
    CONF_NUM_WPM,
    CONF_SCAN_INTERVAL,
    CONF_WW_INTERNAL,
    CONF_PORT,
)

_LOGGER = logging.getLogger(__name__)


async def _test_connection(host: str, port: int) -> str | None:
    """Test Modbus connection + login. Returns error key or None on success."""
    client = AsyncModbusTcpClient(host, port=port)
    try:
        connected = await asyncio.wait_for(client.connect(), timeout=5.0)
        if not connected:
            return "cannot_connect"
        result = await asyncio.wait_for(
            client.write_registers(LOGIN_ADDRESS, LOGIN_PAYLOAD, slave=SLAVE_HSM),
            timeout=5.0,
        )
        if result.isError():
            return "login_failed"
        return None
    except (ModbusException, OSError, asyncio.TimeoutError):
        return "cannot_connect"
    finally:
        client.close()


class OvumMiraConfigFlow(ConfigFlow, domain=DOMAIN):
    """Multi-step config flow for Ovum MIRA."""

    VERSION = 1
    _data: dict[str, Any]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Connection."""
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await _test_connection(user_input[CONF_HOST], user_input[CONF_PORT])
            if error:
                errors["base"] = error
            else:
                self._data = {**user_input}
                return await self.async_step_license()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                    int, vol.Range(min=10, max=300)
                ),
            }),
            errors=errors,
        )

    async def async_step_license(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: License level."""
        if user_input is not None:
            self._data[CONF_LEVEL] = int(user_input[CONF_LEVEL])
            return await self.async_step_ww_type()

        return self.async_show_form(
            step_id="license",
            data_schema=vol.Schema({
                vol.Required(CONF_LEVEL, default=Level.L1): vol.In({
                    Level.L1: "Level 1 — Start Values (free)",
                    Level.L2: "Level 2 — Plus Values (paid)",
                    Level.L3: "Level 3 — BMS Values (paid)",
                }),
            }),
        )

    async def async_step_ww_type(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: WW type (internal Frischwasser or external tank)."""
        if user_input is not None:
            self._data[CONF_WW_INTERNAL] = user_input[CONF_WW_INTERNAL]
            return await self.async_step_hk_count()

        return self.async_show_form(
            step_id="ww_type",
            data_schema=vol.Schema({
                vol.Required(CONF_WW_INTERNAL, default=False): bool,
            }),
        )

    async def async_step_hk_count(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 4: Number of heating circuits (HK) and WPM modules."""
        if user_input is not None:
            self._data[CONF_NUM_HK] = user_input[CONF_NUM_HK]
            self._data[CONF_NUM_WPM] = user_input[CONF_NUM_WPM]
            return await self.async_step_cooling()

        level = self._data.get(CONF_LEVEL, Level.L1)
        max_hk = 4 if level >= Level.L2 else 2

        return self.async_show_form(
            step_id="hk_count",
            data_schema=vol.Schema({
                vol.Required(CONF_NUM_HK, default=2): vol.All(
                    int, vol.Range(min=1, max=max_hk)
                ),
                vol.Required(CONF_NUM_WPM, default=1): vol.All(
                    int, vol.Range(min=1, max=8)
                ),
            }),
        )

    async def async_step_cooling(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 5: Cooling configuration."""
        if user_input is not None:
            self._data[CONF_COOLING] = user_input[CONF_COOLING]
            await self.async_set_unique_id(
                f"{self._data[CONF_HOST]}:{self._data[CONF_PORT]}"
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Ovum MIRA ({self._data[CONF_HOST]})",
                data=self._data,
            )

        return self.async_show_form(
            step_id="cooling",
            data_schema=vol.Schema({
                vol.Required(CONF_COOLING, default=False): bool,
            }),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OvumMiraOptionsFlow()


class OvumMiraOptionsFlow(OptionsFlow):
    """Options flow: only scan_interval is user-changeable after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                    int, vol.Range(min=10, max=300)
                ),
            }),
        )
