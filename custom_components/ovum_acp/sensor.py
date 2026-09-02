"""Sensor entities for Ovum MIRA — all read-only register values."""

from __future__ import annotations

import math
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfPower, UnitOfEnergy, UnitOfVolumeFlowRate, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    DataType,
    RegisterDef,
    WPM_STATUS_NAMES,
    WW_ANFSTATUS_NAMES,
)
from .coordinator import OvumMiraCoordinator
from .entity import OvumMiraEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OvumMiraCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[OvumMiraSensor] = []
    for reg in coordinator.registers:
        if not reg.writable or reg.data_type == DataType.INT16:
            # Expose writable int16 as both sensor (read-back) and select/number
            # For now: all non-writable regs get a sensor
            # Writable float32 and int16 get separate select/number entities, no sensor
            if reg.writable:
                continue
            entities.append(OvumMiraSensor(coordinator, reg))
    async_add_entities(entities)


_UNIT_DEVICE_CLASS: dict[str, tuple[str | None, SensorDeviceClass | None]] = {
    "°C": (UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
    "kW": (UnitOfPower.KILO_WATT, SensorDeviceClass.POWER),
    "W": (UnitOfPower.WATT, SensorDeviceClass.POWER),
    "kWh": (UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY),
    "l/min": (UnitOfVolumeFlowRate.LITERS_PER_MINUTE, None),
    "%": (None, None),
    "rps": (None, None),
    "h": (UnitOfTime.HOURS, SensorDeviceClass.DURATION),
    "min": (UnitOfTime.MINUTES, SensorDeviceClass.DURATION),
    "": (None, None),
}


class OvumMiraSensor(OvumMiraEntity, SensorEntity):
    """Sensor entity for a read-only (or read-back) Modbus register."""

    def __init__(self, coordinator: OvumMiraCoordinator, reg: RegisterDef) -> None:
        super().__init__(coordinator, reg)
        native_unit, device_class = _UNIT_DEVICE_CLASS.get(reg.unit, (reg.unit or None, None))
        self._attr_native_unit_of_measurement = native_unit
        self._attr_device_class = device_class
        if reg.data_type in (DataType.FLOAT32,):
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif reg.data_type in (DataType.INT32,) and reg.unit in ("h", "min", ""):
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self) -> float | int | str | None:
        raw = self._raw_value
        if raw is None:
            return None
        if isinstance(raw, float) and math.isnan(raw):
            return None

        if self._reg.scale != 1.0 and isinstance(raw, (int, float)):
            raw = raw * self._reg.scale

        # Named states for status codes
        if self._reg.name.endswith("wpm_status"):
            return WPM_STATUS_NAMES.get(int(raw), str(raw))
        if self._reg.name in ("ww_anfstatus", "ww_anfstatus_bms"):
            return WW_ANFSTATUS_NAMES.get(int(raw), str(raw))
        if self._reg.name.endswith("_mode") and "lk_" in self._reg.name:
            return {0: "AUS", 1: "WW", 2: "HZ", 3: "KÜ"}.get(int(raw), str(raw))

        if isinstance(raw, bool):
            return "on" if raw else "off"
        return raw

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"register_address": self._reg.address, "slave": self._reg.slave}
        if self._reg.description:
            attrs["description"] = self._reg.description
        return attrs
