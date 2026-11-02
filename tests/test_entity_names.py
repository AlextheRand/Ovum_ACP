"""Entity names, entity IDs and translated code states."""

import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_components.ovum_acp import binary_sensor, number, select, sensor
from custom_components.ovum_acp.const import (
    SENSOR_ENUM_CODES,
    Level,
    build_register_list,
    entity_translation,
)
from custom_components.ovum_acp.sensor import OvumMiraSensor

COMPONENT = Path(__file__).parent.parent / "custom_components" / "ovum_acp"
TRANSLATIONS = {
    path.name: json.loads(path.read_text(encoding="utf-8"))["entity"]
    for path in (
        COMPONENT / "strings.json",
        COMPONENT / "translations" / "en.json",
        COMPONENT / "translations" / "de.json",
    )
}
PLATFORMS = {
    "binary_sensor": binary_sensor,
    "number": number,
    "select": select,
    "sensor": sensor,
}


def full_coordinator() -> MagicMock:
    coordinator = MagicMock()
    coordinator.registers = build_register_list(Level.L3, 4, 2, True, True)
    coordinator.data = {}
    coordinator._num_wpm = 2
    return coordinator


def registers() -> dict:
    return {reg.name: reg for reg in full_coordinator().registers}


async def platform_entities(platform: str) -> list:
    hass = MagicMock()
    hass.data = {"ovum_acp": {"test": full_coordinator()}}
    add = MagicMock()
    await PLATFORMS[platform].async_setup_entry(hass, MagicMock(entry_id="test"), add)
    return add.call_args.args[0]


@pytest.mark.parametrize(
    "name,expected",
    [
        ("hk2_type", ("hk_type", {"hk": "2"})),
        ("wpm1_status", ("wpm_status", {"wpm": "1"})),
        ("wpm1_wpm_status", ("wpm_wpm_status", {"wpm": "1"})),
        ("hpuf_solltemp", ("hpuf_solltemp", {})),
        ("hsm_lk_a_mode", ("hsm_lk_a_mode", {})),
    ],
)
def test_entity_translation(name: str, expected: tuple[str, dict[str, str]]) -> None:
    assert entity_translation(name) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", sorted(PLATFORMS))
async def test_every_entity_has_a_translated_name(platform: str) -> None:
    entities = await platform_entities(platform)
    assert entities
    for entity in entities:
        key = entity.translation_key
        placeholders = entity.translation_placeholders or {}
        for file_name, translations in TRANSLATIONS.items():
            name = translations[platform][key]["name"]
            formatted = name.format(**placeholders)
            assert not re.search(r"[{}]", formatted), (file_name, key)


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", sorted(PLATFORMS))
async def test_new_installs_keep_established_entity_ids(platform: str) -> None:
    entities = await platform_entities(platform)
    ids = [entity.entity_id for entity in entities]
    assert len(ids) == len(set(ids))
    for entity in entities:
        reg = getattr(entity, "_reg", None)
        if reg is not None:
            assert entity.entity_id == f"{platform}.ovum_mira_{reg.name}"
    if platform == "binary_sensor":
        assert "binary_sensor.ovum_mira_has_fault" in ids
        assert "binary_sensor.ovum_mira_wpm2_running" in ids


def test_translation_files_cover_the_same_keys() -> None:
    shapes = {
        file_name: {
            platform: {key: sorted(entry.get("state", {})) for key, entry in entries.items()}
            for platform, entries in translations.items()
        }
        for file_name, translations in TRANSLATIONS.items()
    }
    assert shapes["strings.json"] == shapes["en.json"] == shapes["de.json"]


@pytest.mark.parametrize("key", sorted(SENSOR_ENUM_CODES))
def test_translated_states_are_valid_options(key: str) -> None:
    options = {str(code) for code in SENSOR_ENUM_CODES[key]}
    for translations in TRANSLATIONS.values():
        assert set(translations["sensor"][key]["state"]) <= options


def test_wpm_status_keeps_the_raw_code_as_state() -> None:
    coordinator = full_coordinator()
    entity = OvumMiraSensor(coordinator, registers()["wpm1_status"])
    assert entity.device_class == "enum"
    assert entity.native_unit_of_measurement is None
    coordinator.data = {"wpm1_status": 3}
    assert entity.native_value == "3"
    assert entity.native_value in entity.options
    coordinator.data = {"wpm1_status": 2}
    assert entity.native_value == "2"


def test_undocumented_code_becomes_unknown() -> None:
    coordinator = full_coordinator()
    entity = OvumMiraSensor(coordinator, registers()["sys_puffer"])
    coordinator.data = {"sys_puffer": 7}
    assert entity.native_value is None
    coordinator.data = {"sys_puffer": 2}
    assert entity.native_value == "2"


def test_cube_and_heating_circuit_codes_are_enums() -> None:
    regs = registers()
    for name in ("sys_ww", "sys_puffer", "hk1_type", "hk4_type"):
        assert OvumMiraSensor(full_coordinator(), regs[name]).device_class == "enum"


def test_percent_unit_is_kept() -> None:
    entity = OvumMiraSensor(full_coordinator(), registers()["wpm1_anfsoll"])
    assert entity.native_unit_of_measurement == "%"
