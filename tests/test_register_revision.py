"""Regressions against user-supplied Start/Plus tables dated 2026-06-01."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ovum_acp.const import DataType, Level, build_register_list, is_register_value_valid
from custom_components.ovum_acp.coordinator import _decode_value, _encode_int32
from custom_components.ovum_acp.number import OvumMiraNumber, async_setup_entry
from custom_components.ovum_acp.select import _get_options


def registers(level=Level.L2):
    return {reg.name: reg for reg in build_register_list(level, 4, 1, False, True)}


@pytest.mark.parametrize("name,address", [
    ("ems_grid_power", 55072), ("ems_wr_power", 55074), ("ems_target_power", 55076),
])
def test_ems_signed_32bit_register_layout(name, address):
    reg = registers()[name]
    assert (reg.address, reg.count, reg.data_type, reg.writable) == (address, 2, DataType.INT32, True)


@pytest.mark.parametrize("value", [-2147483647, -100000, -1, 0, 32767, 100000, 2147483646])
def test_signed_power_roundtrip_and_readback(value):
    assert _decode_value(_encode_int32(value), DataType.INT32) == value
    assert is_register_value_valid(registers()["ems_grid_power"], value)


@pytest.mark.parametrize("hk", [1, 2, 3, 4])
def test_hk_ranges_and_platform_routing(hk):
    regs = registers()
    expected = {"pv_plus": (0, 25), "pv_minus": (-25, 0),
                "raumsoll_hz": (0, 50), "raumsoll_kue": (0, 50),
                "tvl_urlaub_hz": (0, 50), "tvl_urlaub_kue": (0, 50),
                "at_heizgrenze": (0, 100)}
    for suffix, limits in expected.items():
        reg = regs[f"hk{hk}_{suffix}"]
        assert reg.writable
        assert (reg.min_value, reg.max_value) == limits
        assert _get_options(reg.name) is None
    assert _get_options(f"hk{hk}_urlaub") == ["AUS", "EIN"]


def test_start_level_includes_hk1_room_temperature():
    regs = registers(Level.L1)
    assert regs["hk1_actualroomtemp"].address == 56152
    assert "hk2_actualroomtemp" not in regs
    assert "hk3_mode" not in regs
    assert regs["wpm1_anfsoll"].address == 56020
    assert regs["sys_ww"].address == 55003
    assert regs["sys_puffer"].address == 55020


def test_text_register_decode():
    value = _decode_value([0x4D49, 0x5241] + [0] * 8, DataType.TEXT)
    assert value == "MIRA"
    assert is_register_value_valid(registers()["sys_type"], value)
    assert not is_register_value_valid(registers()["sys_type"], "")
    assert _decode_value([65535] * 10, DataType.TEXT) is None


@pytest.mark.parametrize("word", [2, 32767, 65535])
def test_invalid_boolean_does_not_become_on(word):
    assert _decode_value([word], DataType.BOOL) is None


@pytest.mark.asyncio
async def test_number_platform_exposes_int32():
    coordinator = MagicMock()
    coordinator.registers = list(registers().values())
    hass = MagicMock()
    hass.data = {"ovum_acp": {"test": coordinator}}
    entry = MagicMock(entry_id="test")
    add = MagicMock()
    await async_setup_entry(hass, entry, add)
    entities = {entity._reg.name: entity for entity in add.call_args.args[0]}
    assert "ems_grid_power" in entities
    assert "hk3_pv_plus" in entities
    assert "hk3_tvl_urlaub_hz" in entities


@pytest.mark.asyncio
async def test_number_writes_32bit_without_truncation():
    coordinator = MagicMock()
    coordinator.async_write_int32 = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    entity = OvumMiraNumber(coordinator, registers()["ems_grid_power"])
    await entity.async_set_native_value(-100000)
    coordinator.async_write_int32.assert_awaited_once_with(110, 55072, -100000)
    coordinator.async_write_int16.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [float("nan"), float("inf"), 2147483648, 1.5])
async def test_invalid_power_write_does_not_reach_hardware(value):
    coordinator = MagicMock()
    coordinator.async_write_int32 = AsyncMock()
    entity = OvumMiraNumber(coordinator, registers()["ems_grid_power"])
    with pytest.raises(ValueError):
        await entity.async_set_native_value(value)
    coordinator.async_write_int32.assert_not_called()


@pytest.mark.asyncio
async def test_frost_readback_does_not_relax_manual_write_limit():
    coordinator = MagicMock()
    coordinator.data = {"hk1_desiredtemp": 5.0}
    coordinator.last_update_success = True
    coordinator.async_write_float32 = AsyncMock()
    entity = OvumMiraNumber(coordinator, registers()["hk1_desiredtemp"])
    assert entity.available
    assert entity.native_value == 5.0
    with pytest.raises(ValueError):
        await entity.async_set_native_value(5.0)
    coordinator.async_write_float32.assert_not_called()
