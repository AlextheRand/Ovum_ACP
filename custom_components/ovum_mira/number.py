"""Number entities for Ovum MIRA — writable temperature and setpoint registers."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, DataType
from .coordinator import OvumMiraCoordinator
from .entity import OvumMiraEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OvumMiraCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[OvumMiraNumber] = []
    for reg in coordinator.registers:
        if not reg.writable:
            continue
        if reg.data_type not in (DataType.FLOAT32, DataType.INT16):
            continue
        # INT16 writable without named options → numeric entry (e.g. ww_soll, puffer_soll_pv)
        from .select import _get_options
        if reg.data_type == DataType.INT16 and _get_options(reg.name) is not None:
            continue  # Handled by select.py
        if not reg.unit:
            continue  # Skip non-unit writables (modes without options already filtered)
        entities.append(OvumMiraNumber(coordinator, reg))
    async_add_entities(entities)


class OvumMiraNumber(OvumMiraEntity, NumberEntity):
    """Number entity for a writable temperature or setpoint register."""

    def __init__(self, coordinator: OvumMiraCoordinator, reg: OvumMiraEntity) -> None:
        super().__init__(coordinator, reg)
        self._attr_mode = NumberMode.BOX
        if reg.unit == "°C":
            self._attr_device_class = NumberDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        else:
            self._attr_native_unit_of_measurement = reg.unit
        self._attr_native_min_value = reg.min_value if reg.min_value is not None else -50.0
        self._attr_native_max_value = reg.max_value if reg.max_value is not None else 100.0
        self._attr_native_step = 0.5 if reg.data_type == DataType.FLOAT32 else 1.0

    @property
    def native_value(self) -> float | None:
        raw = self._raw_value
        if raw is None:
            return None
        try:
            import math
            v = float(raw)
            return None if math.isnan(v) else v
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        if self._reg.data_type == DataType.FLOAT32:
            await self.coordinator.async_write_float32(
                self._reg.slave, self._reg.address, value
            )
        else:
            await self.coordinator.async_write_int16(
                self._reg.slave, self._reg.address, int(value)
            )
        await self.coordinator.async_request_refresh()
