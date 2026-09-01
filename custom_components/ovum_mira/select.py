"""Select entities for Ovum MIRA — writable INT16 mode registers."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    DataType,
    EMS_PV_STATUS_OPTIONS,
    HK_FIX_MODE_OPTIONS,
    HK_MODE_OPTIONS,
)
from .coordinator import OvumMiraCoordinator
from .entity import OvumMiraEntity

_LOGGER = logging.getLogger(__name__)


# Map register name patterns → option lists
_SELECT_OPTIONS: dict[str, list[str]] = {
    "hk_mode": HK_MODE_OPTIONS,
    "hk_fix_mode": HK_FIX_MODE_OPTIONS,
    "ems_pvstatus": EMS_PV_STATUS_OPTIONS,
    "ww_switch_on": ["AUS", "EIN"],
    "ww_urlaub": ["AUS", "EIN"],
    "hk_urlaub": ["AUS", "EIN"],
}


def _get_options(reg_name: str) -> list[str] | None:
    for pattern, opts in _SELECT_OPTIONS.items():
        if pattern in reg_name:
            return opts
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OvumMiraCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[OvumMiraSelect] = []
    for reg in coordinator.registers:
        if not reg.writable or reg.data_type != DataType.INT16:
            continue
        options = _get_options(reg.name)
        if options is None:
            continue  # Not a select — handled as number or binary_sensor
        entities.append(OvumMiraSelect(coordinator, reg, options))
    async_add_entities(entities)


class OvumMiraSelect(OvumMiraEntity, SelectEntity):
    """Select entity for a writable INT16 register with named options."""

    def __init__(
        self, coordinator: OvumMiraCoordinator, reg: Any, options: list[str]
    ) -> None:
        super().__init__(coordinator, reg)
        self._attr_options = options

    @property
    def current_option(self) -> str | None:
        raw = self._raw_value
        if raw is None:
            return None
        idx = int(raw)
        if 0 <= idx < len(self._attr_options):
            return self._attr_options[idx]
        return str(idx)

    async def async_select_option(self, option: str) -> None:
        if option not in self._attr_options:
            raise ValueError(f"Invalid option {option!r} for {self._reg.name}")
        value = self._attr_options.index(option)
        await self.coordinator.async_write_int16(self._reg.slave, self._reg.address, value)
        await self.coordinator.async_request_refresh()
