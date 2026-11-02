"""Set up the integration in a real Home Assistant instance (needs
pytest-homeassistant-custom-component; skipped without it)."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.helpers import entity_registry as er  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.ovum_acp.const import Level  # noqa: E402
from custom_components.ovum_acp.coordinator import OvumMiraCoordinator  # noqa: E402

from .conftest import MOCK_CONFIG_DATA  # noqa: E402

# Values as on a MIRA with Cube storage (user screenshot, 2026-11-02)
CUBE_DATA = {
    "sys_ww": 1,
    "sys_puffer": 2,
    "hk1_type": 3,
    "wpm1_status": 3,
    "wpm1_anfsoll": 58,
    "puffer_temp_unten": 30.0,
    "puffer_temp_oben": float("nan"),
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> Iterator[None]:
    yield


async def setup_entry(hass: HomeAssistant, language: str) -> None:
    hass.config.language = language
    entry = MockConfigEntry(
        domain="ovum_acp",
        data={**MOCK_CONFIG_DATA, "level": Level.L1},
        entry_id="cube",
    )
    entry.add_to_hass(hass)
    with (
        patch.object(OvumMiraCoordinator, "_async_setup", AsyncMock()),
        patch.object(
            OvumMiraCoordinator, "_async_update_data", AsyncMock(return_value=CUBE_DATA)
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def test_german_names_established_ids_and_raw_codes(hass: HomeAssistant) -> None:
    await setup_entry(hass, "de")

    status = hass.states.get("sensor.ovum_mira_wpm1_status")
    assert status.state == "3"
    assert status.attributes["friendly_name"] == "Ovum MIRA WP 1 Status"
    assert status.attributes["device_class"] == "enum"
    assert "3" in status.attributes["options"]

    puffer = hass.states.get("sensor.ovum_mira_sys_puffer")
    assert puffer.state == "2"
    assert puffer.attributes["friendly_name"] == "Ovum MIRA Heizpuffer"

    assert hass.states.get("sensor.ovum_mira_hk1_type").attributes["friendly_name"] == (
        "Ovum MIRA Heizkreis 1 Typ"
    )
    demand = hass.states.get("sensor.ovum_mira_wpm1_anfsoll")
    assert demand.state == "58"
    assert demand.attributes["unit_of_measurement"] == "%"
    assert hass.states.get("sensor.ovum_mira_puffer_temp_oben").state == "unavailable"
    assert hass.states.get("number.ovum_mira_ww_soll").attributes["friendly_name"] == (
        "Ovum MIRA WW-Soll"
    )

    registry = er.async_get(hass)
    assert registry.async_get_entity_id("sensor", "ovum_acp", "ovum_acp_wpm1_status") == (
        "sensor.ovum_mira_wpm1_status"
    )


async def test_english_names_keep_the_same_ids(hass: HomeAssistant) -> None:
    await setup_entry(hass, "en")
    status = hass.states.get("sensor.ovum_mira_wpm1_status")
    assert status.attributes["friendly_name"] == "Ovum MIRA Heat pump 1 status"
    assert hass.states.get("sensor.ovum_mira_hk1_type").attributes["friendly_name"] == (
        "Ovum MIRA Heating circuit 1 type"
    )
