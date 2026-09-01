"""Tests for register map completeness and correctness."""

from __future__ import annotations

import pytest

from custom_components.ovum_mira.const import (
    FC,
    DataType,
    Level,
    RegisterDef,
    build_register_list,
)


def test_build_l1_minimal() -> None:
    regs = build_register_list(Level.L1, num_hk=2, num_wpm=1, has_ww_internal=False, has_cooling=False)
    names = {r.name for r in regs}
    assert "ww_soll" in names
    assert "ww_temp_oben" in names
    assert "aussentemperatur" in names
    assert "hk1_desiredtemp" in names
    assert "hk2_desiredtemp" in names
    # L2 not included
    assert "ww_anfstatus" not in names
    assert "hk1_at_heizgrenze" not in names


def test_build_l2_adds_extended_hk() -> None:
    regs = build_register_list(Level.L2, num_hk=2, num_wpm=1, has_ww_internal=False, has_cooling=False)
    names = {r.name for r in regs}
    assert "hk1_at_heizgrenze" in names
    assert "hk2_at_heizgrenze" in names
    assert "ww_anfstatus" in names
    # HK3 not included (num_hk=2)
    assert "hk3_desiredtemp" not in names


def test_build_l2_hk3_requires_l2() -> None:
    regs = build_register_list(Level.L2, num_hk=4, num_wpm=1, has_ww_internal=False, has_cooling=False)
    names = {r.name for r in regs}
    assert "hk3_desiredtemp" in names
    assert "hk4_desiredtemp" in names


def test_fws_excluded_without_internal_ww() -> None:
    regs = build_register_list(Level.L2, num_hk=2, num_wpm=1, has_ww_internal=False, has_cooling=False)
    names = {r.name for r in regs}
    assert "fws_soll" not in names
    assert "ww_fwsstsstatus" not in names


def test_fws_included_with_internal_ww() -> None:
    regs = build_register_list(Level.L2, num_hk=2, num_wpm=1, has_ww_internal=True, has_cooling=False)
    names = {r.name for r in regs}
    assert "fws_soll" in names
    assert "ww_fwsstsstatus" in names


def test_cooling_excluded_without_cooling() -> None:
    regs = build_register_list(Level.L2, num_hk=2, num_wpm=1, has_ww_internal=False, has_cooling=False)
    names = {r.name for r in regs}
    assert "kpuf_puut" not in names
    assert "sys_kue_puffer" not in names


def test_cooling_included_with_cooling() -> None:
    regs = build_register_list(Level.L2, num_hk=2, num_wpm=1, has_ww_internal=False, has_cooling=True)
    names = {r.name for r in regs}
    assert "kpuf_puut" in names
    assert "sys_kue_puffer" in names


def test_l3_adds_wpm_diagnostics() -> None:
    regs = build_register_list(Level.L3, num_hk=2, num_wpm=1, has_ww_internal=False, has_cooling=False)
    names = {r.name for r in regs}
    assert "wpm1_cop" in names
    assert "wpm1_rps" in names
    assert "wpm1_wpm_status" in names
    assert "hsm_errorbits" in names
    assert "hsm_error_quit" in names


def test_l3_registers_use_fc4_for_diagnostics() -> None:
    regs = build_register_list(Level.L3, num_hk=2, num_wpm=1, has_ww_internal=False, has_cooling=False)
    cop = next(r for r in regs if r.name == "wpm1_cop")
    assert cop.fc == FC.FC4
    assert cop.address == 30088


def test_register_count_matches_datatype() -> None:
    """All FLOAT32 and INT32 registers must have count==2."""
    regs = build_register_list(Level.L3, num_hk=4, num_wpm=2, has_ww_internal=True, has_cooling=True)
    for reg in regs:
        if reg.data_type in (DataType.FLOAT32, DataType.INT32):
            assert reg.count == 2, f"{reg.name} count should be 2"
        else:
            assert reg.count == 1, f"{reg.name} count should be 1"


def test_hk1_desiredtemp_is_writable() -> None:
    regs = build_register_list(Level.L1, num_hk=2, num_wpm=1, has_ww_internal=False, has_cooling=False)
    hk1 = next(r for r in regs if r.name == "hk1_desiredtemp")
    assert hk1.writable is True


def test_hk3_desiredtemp_is_readonly() -> None:
    regs = build_register_list(Level.L2, num_hk=4, num_wpm=1, has_ww_internal=False, has_cooling=False)
    hk3 = next(r for r in regs if r.name == "hk3_desiredtemp")
    assert hk3.writable is False


def test_hk_l2_base_addresses() -> None:
    """HK extended block base = 56150 + (n-1)*25."""
    regs = build_register_list(Level.L2, num_hk=4, num_wpm=1, has_ww_internal=False, has_cooling=False)
    for n in range(1, 5):
        at_heizgrenze = next(r for r in regs if r.name == f"hk{n}_at_heizgrenze")
        expected_base = 56150 + (n - 1) * 25
        assert at_heizgrenze.address == expected_base + 10, (
            f"hk{n}_at_heizgrenze expected addr {expected_base + 10}, got {at_heizgrenze.address}"
        )


def test_wpm_l1_base_addresses() -> None:
    regs = build_register_list(Level.L1, num_hk=2, num_wpm=2, has_ww_internal=False, has_cooling=False)
    wpm1 = next(r for r in regs if r.name == "wpm1_aufnahmeleistung")
    wpm2 = next(r for r in regs if r.name == "wpm2_aufnahmeleistung")
    assert wpm1.address == 56021
    assert wpm1.slave == 111
    assert wpm2.address == 56021
    assert wpm2.slave == 112
