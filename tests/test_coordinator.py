"""Tests for OvumMiraCoordinator: login, read, write, reconnect."""

from __future__ import annotations

import struct
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from custom_components.ovum_mira.const import DataType, FC, Level, SLAVE_HSM, SLAVE_WPM_BASE
from custom_components.ovum_mira.coordinator import (
    OvumMiraCoordinator,
    _decode_value,
    _encode_float32,
    _encode_int16,
)

from .conftest import MOCK_CONFIG_DATA, make_mock_modbus_result


# ---------------------------------------------------------------------------
# Unit tests: encode/decode
# ---------------------------------------------------------------------------

def test_encode_decode_int16_positive() -> None:
    encoded = _encode_int16(42)
    decoded = _decode_value(encoded, DataType.INT16)
    assert decoded == 42


def test_encode_decode_int16_negative() -> None:
    encoded = _encode_int16(-300)
    decoded = _decode_value(encoded, DataType.INT16)
    assert decoded == -300


def test_encode_decode_float32_roundtrip() -> None:
    for val in [0.0, 45.5, -12.3, 100.0]:
        encoded = _encode_float32(val)
        decoded = _decode_value(encoded, DataType.FLOAT32)
        assert abs(decoded - val) < 0.01, f"roundtrip failed for {val}: got {decoded}"


def test_decode_float32_sentinel_returns_nan() -> None:
    import math
    # FLT_MAX encoded
    raw = struct.pack(">f", 3.4028235e38)
    regs = list(struct.unpack(">HH", raw))
    result = _decode_value(regs, DataType.FLOAT32)
    assert math.isnan(result)


def test_decode_bool() -> None:
    assert _decode_value([1], DataType.BOOL) is True
    assert _decode_value([0], DataType.BOOL) is False


# ---------------------------------------------------------------------------
# Integration tests: coordinator lifecycle
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_entry(mock_modbus_client):
    entry = MagicMock()
    entry.data = MOCK_CONFIG_DATA
    entry.options = {}
    return entry


@pytest.fixture
def coordinator(mock_entry, mock_modbus_client):
    hass = MagicMock()
    hass.loop = None
    coord = OvumMiraCoordinator.__new__(OvumMiraCoordinator)
    # Bypass __init__ DataUpdateCoordinator machinery for unit tests
    coord._host = MOCK_CONFIG_DATA["host"]
    coord._port = MOCK_CONFIG_DATA["port"]
    coord._level = Level(MOCK_CONFIG_DATA["level"])
    coord._num_hk = MOCK_CONFIG_DATA["num_hk"]
    coord._num_wpm = MOCK_CONFIG_DATA["num_wpm"]
    coord._ww_internal = MOCK_CONFIG_DATA["ww_internal"]
    coord._cooling = MOCK_CONFIG_DATA["cooling"]
    coord._client = mock_modbus_client
    coord._last_login = None
    import asyncio
    coord._lock = asyncio.Lock()
    from custom_components.ovum_mira.const import build_register_list
    coord.registers = build_register_list(
        coord._level, coord._num_hk, coord._num_wpm, coord._ww_internal, coord._cooling
    )
    return coord


@pytest.mark.asyncio
async def test_login_sends_fc16_to_hsm_and_wpm(coordinator, mock_modbus_client) -> None:
    await coordinator._login()
    calls = mock_modbus_client.write_registers.call_args_list
    slaves_called = {c.kwargs.get("slave") or c.args[2] for c in calls}
    assert SLAVE_HSM in slaves_called
    assert SLAVE_WPM_BASE in slaves_called  # WPM1


@pytest.mark.asyncio
async def test_login_sets_timestamp(coordinator, mock_modbus_client) -> None:
    assert coordinator._last_login is None
    await coordinator._login()
    assert coordinator._last_login is not None


@pytest.mark.asyncio
async def test_needs_relogin_after_25_min(coordinator) -> None:
    from datetime import datetime, timedelta
    coordinator._last_login = datetime.now() - timedelta(minutes=26)
    assert coordinator._needs_relogin() is True


@pytest.mark.asyncio
async def test_needs_relogin_false_within_interval(coordinator) -> None:
    from datetime import datetime
    coordinator._last_login = datetime.now()
    assert coordinator._needs_relogin() is False


@pytest.mark.asyncio
async def test_write_int16_calls_fc16(coordinator, mock_modbus_client) -> None:
    await coordinator._login()  # set timestamp so no re-login
    mock_modbus_client.write_registers.reset_mock()
    await coordinator.async_write_int16(SLAVE_HSM, 55001, 45)
    mock_modbus_client.write_registers.assert_called_once()
    args = mock_modbus_client.write_registers.call_args
    assert args.args[0] == 55001 or args.kwargs.get("address") == 55001


@pytest.mark.asyncio
async def test_write_float32_bitexact(coordinator, mock_modbus_client) -> None:
    await coordinator._login()
    mock_modbus_client.write_registers.reset_mock()
    await coordinator.async_write_float32(SLAVE_HSM, 56058, 22.5)
    args = mock_modbus_client.write_registers.call_args
    written: list[int] = args.args[1] if len(args.args) > 1 else args.kwargs["values"]
    # Decode written back
    raw = struct.pack(">HH", written[0], written[1])
    decoded = struct.unpack(">f", raw)[0]
    assert abs(decoded - 22.5) < 0.01


@pytest.mark.asyncio
async def test_write_retries_on_error(coordinator, mock_modbus_client) -> None:
    """Write error → re-login + retry."""
    await coordinator._login()
    error_result = make_mock_modbus_result([], is_error=True)
    success_result = make_mock_modbus_result([])
    mock_modbus_client.write_registers.side_effect = [
        error_result,   # first write fails
        success_result, # re-login write (FC16 login) succeeds
        success_result, # retry write succeeds
    ]
    # Should not raise
    await coordinator.async_write_int16(SLAVE_HSM, 55001, 45)


@pytest.mark.asyncio
async def test_reconnect_on_disconnected_client(coordinator, mock_modbus_client) -> None:
    """If client disconnects, _ensure_connected reconnects."""
    mock_modbus_client.connected = False
    with patch(
        "custom_components.ovum_mira.coordinator.AsyncModbusTcpClient"
    ) as mock_cls:
        new_client = AsyncMock()
        new_client.connected = True
        new_client.connect = AsyncMock(return_value=True)
        new_client.write_registers = AsyncMock(return_value=make_mock_modbus_result([]))
        mock_cls.return_value = new_client
        await coordinator._ensure_connected()
        assert coordinator._last_login is None  # reset on reconnect
