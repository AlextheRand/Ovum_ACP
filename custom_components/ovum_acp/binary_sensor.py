"""Binary sensor entities for Ovum MIRA — boolean and derived status registers."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DataType
from .coordinator import OvumMiraCoordinator
from .entity import OvumMiraEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OvumMiraCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = []

    for reg in coordinator.registers:
        if reg.data_type == DataType.BOOL:
            entities.append(OvumMiraBinarySensor(coordinator, reg))

    # Derived: WP system fault (from HSM_ERRORBITS)
    if any(r.name == "hsm_errorbits" for r in coordinator.registers):
        entities.append(OvumMiraFaultSensor(coordinator))

    # Derived: WPM compressor running (from wpm_status)
    for wpm_idx in range(1, coordinator._num_wpm + 1):
        if any(r.name == f"wpm{wpm_idx}_wpm_status" for r in coordinator.registers):
            entities.append(OvumMiraWpmRunningSensor(coordinator, wpm_idx))

    async_add_entities(entities)


class OvumMiraBinarySensor(OvumMiraEntity, BinarySensorEntity):
    """Binary sensor for a BOOL register."""

    @property
    def is_on(self) -> bool | None:
        raw = self._raw_value
        if raw is None:
            return None
        return bool(raw)


class OvumMiraFaultSensor(CoordinatorEntity[OvumMiraCoordinator], BinarySensorEntity):
    """True when any HSM or WPM module has an active level 3/4 fault."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: OvumMiraCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_has_fault"
        self._attr_translation_key = "has_fault"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self.coordinator._host)})

    @property
    def is_on(self) -> bool | None:
        bits = self.coordinator.data.get("hsm_errorbits")
        if bits is None:
            return None
        return int(bits) != 0


class OvumMiraWpmRunningSensor(CoordinatorEntity[OvumMiraCoordinator], BinarySensorEntity):
    """True when WPM compressor is actively running (status 6-11)."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: OvumMiraCoordinator, wpm_idx: int) -> None:
        super().__init__(coordinator)
        self._wpm_idx = wpm_idx
        self._attr_unique_id = f"{DOMAIN}_wpm{wpm_idx}_running"
        self._attr_translation_key = "wpm_running"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self.coordinator._host)})

    @property
    def is_on(self) -> bool | None:
        status = self.coordinator.data.get(f"wpm{self._wpm_idx}_wpm_status")
        if status is None:
            return None
        # 6=Start, 7=WW, 8=HZ, 9=Kühlen, 10=Abtauen, 11=Manuell Enteisen
        return int(status) in {6, 7, 8, 9, 10, 11}
