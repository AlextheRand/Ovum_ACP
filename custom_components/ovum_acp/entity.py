"""Base entity for Ovum MIRA integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ENTITY_ID_PREFIX,
    MANUFACTURER,
    MODEL,
    RegisterDef,
    entity_translation,
    is_register_value_valid,
)
from .coordinator import OvumMiraCoordinator


class OvumMiraEntity(CoordinatorEntity[OvumMiraCoordinator]):
    """Base class for all Ovum MIRA entities."""

    _attr_has_entity_name = True
    # Entity platform domain, set by each platform subclass
    _entity_domain: str

    def __init__(self, coordinator: OvumMiraCoordinator, reg: RegisterDef) -> None:
        super().__init__(coordinator)
        self._reg = reg
        self._attr_unique_id = f"{DOMAIN}_{reg.name}"
        self._attr_translation_key, self._attr_translation_placeholders = (
            entity_translation(reg.name)
        )
        # New installs keep the established IDs instead of IDs derived from the
        # translated name; registered entities keep their existing ID anyway.
        self.entity_id = f"{self._entity_domain}.{ENTITY_ID_PREFIX}_{reg.name}"

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
        return is_register_value_valid(
            self._reg,
            self.coordinator.data.get(self._reg.name),
        )

    @property
    def _raw_value(self) -> int | float | bool | str | None:
        return self.coordinator.data.get(self._reg.name)
