"""Config Flow for Ovum MIRA integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from .const import (
    DEFAULT_HOST,
    DEFAULT_LOGIN_CODE,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HK_TYPE_LABELS,
    LOGIN_ADDRESS,
    SLAVE_HSM,
    Level,
)
from .coordinator import (
    CONF_COOLING,
    CONF_HK_TYPES,
    CONF_HOST,
    CONF_LEVEL,
    CONF_LOGIN_CODE,
    CONF_NUM_HK,
    CONF_NUM_WPM,
    CONF_SCAN_INTERVAL,
    CONF_WW_INTERNAL,
    CONF_PORT,
)

_LOGGER = logging.getLogger(__name__)


async def _test_connection(host: str, port: int, login_code: int) -> str | None:
    """Test Modbus connection + login. Returns error key or None on success."""
    login_payload = [(login_code >> 16) & 0xFFFF, login_code & 0xFFFF]
    client = AsyncModbusTcpClient(host, port=port)
    try:
        connected = await asyncio.wait_for(client.connect(), timeout=5.0)
        if not connected:
            return "cannot_connect"
        result = await asyncio.wait_for(
            client.write_registers(LOGIN_ADDRESS, login_payload, device_id=SLAVE_HSM),
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
            error = await _test_connection(
                user_input[CONF_HOST], user_input[CONF_PORT], user_input[CONF_LOGIN_CODE]
            )
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
                vol.Required(CONF_LOGIN_CODE, default=DEFAULT_LOGIN_CODE): vol.All(
                    int, vol.Range(min=1, max=2147483647)
                ),
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
            return await self.async_step_hk_types()

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

    async def async_step_hk_types(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 4b: Function type per heating circuit."""
        num_hk: int = self._data[CONF_NUM_HK]

        if user_input is not None:
            self._data[CONF_HK_TYPES] = {
                f"hk{n}": int(user_input[f"hk{n}_type"]) for n in range(1, num_hk + 1)
            }
            return await self.async_step_cooling()

        schema_dict: dict[Any, Any] = {}
        for n in range(1, num_hk + 1):
            schema_dict[vol.Required(f"hk{n}_type", default=1)] = vol.In(HK_TYPE_LABELS)

        return self.async_show_form(
            step_id="hk_types",
            data_schema=vol.Schema(schema_dict),
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

    # ── Reconfigure flow (HA 2025+: ⋮ → "Neu konfigurieren") ──────────
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure Step 1: Connection."""
        errors: dict[str, str] = {}
        entry = self.config_entry

        def _cur(key: str, default: Any) -> Any:
            return entry.options.get(key, entry.data.get(key, default))

        if user_input is not None:
            self._data = {**user_input}
            return await self.async_step_reconfigure_license()

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=_cur(CONF_HOST, DEFAULT_HOST)): str,
                vol.Required(CONF_PORT, default=_cur(CONF_PORT, DEFAULT_PORT)): int,
                vol.Required(CONF_LOGIN_CODE, default=_cur(CONF_LOGIN_CODE, DEFAULT_LOGIN_CODE)): vol.All(
                    int, vol.Range(min=1, max=2147483647)
                ),
                vol.Required(CONF_SCAN_INTERVAL, default=_cur(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): vol.All(
                    int, vol.Range(min=10, max=300)
                ),
            }),
            errors=errors,
        )

    async def async_step_reconfigure_license(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure Step 2: Level."""
        entry = self.config_entry

        def _cur(key: str, default: Any) -> Any:
            return entry.options.get(key, entry.data.get(key, default))

        if user_input is not None:
            self._data[CONF_LEVEL] = int(user_input[CONF_LEVEL])
            return await self.async_step_reconfigure_ww_type()

        return self.async_show_form(
            step_id="reconfigure_license",
            data_schema=vol.Schema({
                vol.Required(CONF_LEVEL, default=_cur(CONF_LEVEL, Level.L1)): vol.In({
                    Level.L1: "Level 1 — Start Values (free)",
                    Level.L2: "Level 2 — Plus Values (paid)",
                    Level.L3: "Level 3 — BMS Values (paid)",
                }),
            }),
        )

    async def async_step_reconfigure_ww_type(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure Step 3: WW type."""
        entry = self.config_entry

        def _cur(key: str, default: Any) -> Any:
            return entry.options.get(key, entry.data.get(key, default))

        if user_input is not None:
            self._data[CONF_WW_INTERNAL] = user_input[CONF_WW_INTERNAL]
            return await self.async_step_reconfigure_hk_count()

        return self.async_show_form(
            step_id="reconfigure_ww_type",
            data_schema=vol.Schema({
                vol.Required(CONF_WW_INTERNAL, default=_cur(CONF_WW_INTERNAL, False)): bool,
            }),
        )

    async def async_step_reconfigure_hk_count(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure Step 4: HK count + WPM count."""
        entry = self.config_entry

        def _cur(key: str, default: Any) -> Any:
            return entry.options.get(key, entry.data.get(key, default))

        if user_input is not None:
            self._data[CONF_NUM_HK] = user_input[CONF_NUM_HK]
            self._data[CONF_NUM_WPM] = user_input[CONF_NUM_WPM]
            return await self.async_step_reconfigure_hk_types()

        level = self._data.get(CONF_LEVEL, _cur(CONF_LEVEL, Level.L1))
        max_hk = 4 if level >= Level.L2 else 2

        return self.async_show_form(
            step_id="reconfigure_hk_count",
            data_schema=vol.Schema({
                vol.Required(CONF_NUM_HK, default=_cur(CONF_NUM_HK, 2)): vol.All(
                    int, vol.Range(min=1, max=max_hk)
                ),
                vol.Required(CONF_NUM_WPM, default=_cur(CONF_NUM_WPM, 1)): vol.All(
                    int, vol.Range(min=1, max=8)
                ),
            }),
        )

    async def async_step_reconfigure_hk_types(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure Step 5: HK types."""
        entry = self.config_entry
        num_hk: int = self._data[CONF_NUM_HK]
        cur_types: dict[str, int] = entry.options.get(
            CONF_HK_TYPES, entry.data.get(CONF_HK_TYPES, {})
        )

        if user_input is not None:
            self._data[CONF_HK_TYPES] = {
                f"hk{n}": int(user_input[f"hk{n}_type"]) for n in range(1, num_hk + 1)
            }
            return await self.async_step_reconfigure_cooling()

        schema_dict: dict[Any, Any] = {}
        for n in range(1, num_hk + 1):
            schema_dict[vol.Required(f"hk{n}_type", default=cur_types.get(f"hk{n}", 1))] = vol.In(HK_TYPE_LABELS)

        return self.async_show_form(
            step_id="reconfigure_hk_types",
            data_schema=vol.Schema(schema_dict),
        )

    async def async_step_reconfigure_cooling(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure Step 6: Cooling — update entry data and reload."""
        entry = self.config_entry

        def _cur(key: str, default: Any) -> Any:
            return entry.options.get(key, entry.data.get(key, default))

        if user_input is not None:
            self._data[CONF_COOLING] = user_input[CONF_COOLING]
            return self.async_update_reload_and_abort(
                entry,
                data={**entry.data, **self._data},
                reason="reconfigure_successful",
            )

        return self.async_show_form(
            step_id="reconfigure_cooling",
            data_schema=vol.Schema({
                vol.Required(CONF_COOLING, default=_cur(CONF_COOLING, False)): bool,
            }),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OvumMiraOptionsFlow()


class OvumMiraOptionsFlow(OptionsFlow):
    """Options flow: all parameters changeable; triggers reload on save."""

    _data: dict[str, Any]

    def _cur(self, key: str, default: Any) -> Any:
        return self.config_entry.options.get(
            key, self.config_entry.data.get(key, default)
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Connection + scan interval (no live test — coordinator already connected)."""
        if user_input is not None:
            self._data = {**user_input}
            return await self.async_step_license()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=self._cur(CONF_HOST, DEFAULT_HOST)): str,
                vol.Required(CONF_PORT, default=self._cur(CONF_PORT, DEFAULT_PORT)): int,
                vol.Required(CONF_LOGIN_CODE, default=self._cur(CONF_LOGIN_CODE, DEFAULT_LOGIN_CODE)): vol.All(
                    int, vol.Range(min=1, max=2147483647)
                ),
                vol.Required(CONF_SCAN_INTERVAL, default=self._cur(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): vol.All(
                    int, vol.Range(min=10, max=300)
                ),
            }),
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
                vol.Required(CONF_LEVEL, default=self._cur(CONF_LEVEL, Level.L1)): vol.In({
                    Level.L1: "Level 1 — Start Values (free)",
                    Level.L2: "Level 2 — Plus Values (paid)",
                    Level.L3: "Level 3 — BMS Values (paid)",
                }),
            }),
        )

    async def async_step_ww_type(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: WW type."""
        if user_input is not None:
            self._data[CONF_WW_INTERNAL] = user_input[CONF_WW_INTERNAL]
            return await self.async_step_hk_count()

        return self.async_show_form(
            step_id="ww_type",
            data_schema=vol.Schema({
                vol.Required(CONF_WW_INTERNAL, default=self._cur(CONF_WW_INTERNAL, False)): bool,
            }),
        )

    async def async_step_hk_count(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 4: HK count + WPM count."""
        if user_input is not None:
            self._data[CONF_NUM_HK] = user_input[CONF_NUM_HK]
            self._data[CONF_NUM_WPM] = user_input[CONF_NUM_WPM]
            return await self.async_step_hk_types()

        level = self._data.get(CONF_LEVEL, self._cur(CONF_LEVEL, Level.L1))
        max_hk = 4 if level >= Level.L2 else 2

        return self.async_show_form(
            step_id="hk_count",
            data_schema=vol.Schema({
                vol.Required(CONF_NUM_HK, default=self._cur(CONF_NUM_HK, 2)): vol.All(
                    int, vol.Range(min=1, max=max_hk)
                ),
                vol.Required(CONF_NUM_WPM, default=self._cur(CONF_NUM_WPM, 1)): vol.All(
                    int, vol.Range(min=1, max=8)
                ),
            }),
        )

    async def async_step_hk_types(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 5: HK type per circuit."""
        num_hk: int = self._data[CONF_NUM_HK]
        cur_types: dict[str, int] = self._cur(CONF_HK_TYPES, {})

        if user_input is not None:
            self._data[CONF_HK_TYPES] = {
                f"hk{n}": int(user_input[f"hk{n}_type"]) for n in range(1, num_hk + 1)
            }
            return await self.async_step_cooling()

        schema_dict: dict[Any, Any] = {}
        for n in range(1, num_hk + 1):
            default_type = cur_types.get(f"hk{n}", 1)
            schema_dict[vol.Required(f"hk{n}_type", default=default_type)] = vol.In(HK_TYPE_LABELS)

        return self.async_show_form(
            step_id="hk_types",
            data_schema=vol.Schema(schema_dict),
        )

    async def async_step_cooling(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 6: Cooling — save and trigger reload."""
        if user_input is not None:
            self._data[CONF_COOLING] = user_input[CONF_COOLING]
            return self.async_create_entry(data=self._data)

        return self.async_show_form(
            step_id="cooling",
            data_schema=vol.Schema({
                vol.Required(CONF_COOLING, default=self._cur(CONF_COOLING, False)): bool,
            }),
        )
