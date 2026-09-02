"""Base entity for Ovum MIRA integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL, RegisterDef
from .coordinator import OvumMiraCoordinator


class OvumMiraEntity(CoordinatorEntity[OvumMiraCoordinator]):
    """Base class for all Ovum MIRA entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OvumMiraCoordinator, reg: RegisterDef) -> None:
        super().__init__(coordinator)
        self._reg = reg
        self._attr_unique_id = f"{DOMAIN}_{reg.name}"
        self._attr_name = reg.name

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator._host)},
            name="Ovum MIRA",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        raw = self.coordinator.data.get(self._reg.name)
        if raw is None:
            return False
        try:
            import math
            return not math.isnan(float(raw))
        except (TypeError, ValueError):
            return True

    @property
    def _raw_value(self) -> int | float | bool | None:
        return self.coordinator.data.get(self._reg.name)
