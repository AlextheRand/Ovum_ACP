"""Tests for OvumMiraCoordinator: login, read, write, reconnect."""

from __future__ import annotations

import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ovum_acp.const import (
    DataType, Level, SLAVE_HSM, SLAVE_WPM_BASE,
    build_register_list, is_register_value_valid,
)
from custom_components.ovum_acp.coordinator import (
    OvumMiraCoordinator,
    _decode_value,
    _encode_float32,
    _encode_int16,
)

from .conftest import MOCK_CONFIG_DATA, TEST_LOGIN_CODE, make_mock_modbus_result


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


def test_actual_hk3_wire_response_is_unavailable() -> None:
    """Reproduce the read-only FC3 capture independently of HA state filters."""
    words = [65535, 32767, 32767, 32704, 0, 32704, 0, 65535]
    regs = build_register_list(Level.L2, 3, 1, False, True)
    for reg in regs:
        if reg.name.startswith("hk3_") and 56070 <= reg.address <= 56077:
            offset = reg.address - 56070
            value = _decode_value(words[offset:offset + reg.count], reg.data_type)
            assert not is_register_value_valid(reg, value), reg.name


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
    coord._connection_generation = 0
    coord._login_payload = [TEST_LOGIN_CODE >> 16, TEST_LOGIN_CODE & 0xFFFF]
    import asyncio
    coord._lock = asyncio.Lock()
    coord._failed_read_batches = set()
    from custom_components.ovum_acp.const import build_register_list
    coord.registers = build_register_list(
        coord._level, coord._num_hk, coord._num_wpm, coord._ww_internal, coord._cooling
    )
    return coord


@pytest.mark.asyncio
async def test_login_sends_fc16_to_hsm_and_wpm(coordinator, mock_modbus_client) -> None:
    await coordinator._login()
    calls = mock_modbus_client.write_registers.call_args_list
    slaves_called = {c.kwargs["device_id"] for c in calls}
    assert SLAVE_HSM in slaves_called
    assert SLAVE_WPM_BASE in slaves_called  # WPM1
    assert all(call.args[1] == [1, 57920] for call in calls)


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
async def test_write_int16_calls_fc06(coordinator, mock_modbus_client) -> None:
    await coordinator._login()  # set timestamp so no re-login
    mock_modbus_client.write_register.reset_mock()
    await coordinator.async_write_int16(SLAVE_HSM, 55001, 45)
    mock_modbus_client.write_register.assert_called_once()
    args = mock_modbus_client.write_register.call_args
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
    mock_modbus_client.write_register.side_effect = [
        error_result,   # first write fails
        success_result, # retry write succeeds
    ]
    # Should not raise
    await coordinator.async_write_int16(SLAVE_HSM, 55001, 45)


@pytest.mark.asyncio
async def test_named_int32_write_uses_fc16(coordinator, mock_modbus_client) -> None:
    await coordinator._login()
    mock_modbus_client.write_registers.reset_mock()
    coordinator.async_request_refresh = AsyncMock()
    await coordinator.async_write_register("ems_grid_power", -100000)
    mock_modbus_client.write_registers.assert_awaited_once_with(
        55072, [65534, 31072], device_id=110,
    )
    mock_modbus_client.write_register.assert_not_called()


@pytest.mark.asyncio
async def test_read_batches_do_not_cross_undocumented_gap(coordinator, mock_modbus_client):
    await coordinator._read_all()
    calls = mock_modbus_client.read_holding_registers.call_args_list
    assert any(call.args[0] == 55070 and call.kwargs["count"] == 8 for call in calls)
    for call in calls:
        if call.kwargs["device_id"] == SLAVE_HSM:
            assert not call.args[0] <= 55078 < call.args[0] + call.kwargs["count"]


@pytest.mark.asyncio
async def test_repeated_partial_read_errors_are_logged_once(
    coordinator, mock_modbus_client, caplog,
) -> None:
    error_result = make_mock_modbus_result([], is_error=True)
    mock_modbus_client.read_holding_registers.return_value = error_result
    mock_modbus_client.read_holding_registers.side_effect = None

    await coordinator._read_all()
    first_warnings = [record for record in caplog.records if "Read error" in record.message]
    assert first_warnings

    await coordinator._read_all()
    all_warnings = [record for record in caplog.records if "Read error" in record.message]
    assert len(all_warnings) == len(first_warnings)


@pytest.mark.asyncio
async def test_partial_read_recovery_rearms_error_logging(
    coordinator, mock_modbus_client, caplog,
) -> None:
    import logging

    caplog.set_level(logging.INFO)
    mock_modbus_client.read_holding_registers.side_effect = None
    mock_modbus_client.read_holding_registers.return_value = make_mock_modbus_result(
        [], is_error=True,
    )
    failed = await coordinator._read_all()
    assert "hk1_mode" not in failed
    first_count = len(coordinator._failed_read_batches)
    assert first_count > 0

    mock_modbus_client.read_holding_registers.side_effect = (
        lambda addr, count, device_id: make_mock_modbus_result([0] * count)
    )
    recovered = await coordinator._read_all()
    assert recovered["hk1_mode"] == 0
    assert not coordinator._failed_read_batches
    assert sum("Read recovered" in record.message for record in caplog.records) == first_count

    mock_modbus_client.read_holding_registers.side_effect = None
    await coordinator._read_all()
    assert sum("Read error" in record.message for record in caplog.records) == 2 * first_count


@pytest.mark.asyncio
async def test_reconnect_on_disconnected_client(coordinator, mock_modbus_client) -> None:
    """If client disconnects, _ensure_connected reconnects."""
    mock_modbus_client.connected = False
    with patch(
        "custom_components.ovum_acp.coordinator.AsyncModbusTcpClient"
    ) as mock_cls:
        new_client = AsyncMock()
        new_client.connected = True
        new_client.connect = AsyncMock(return_value=True)
        new_client.write_registers = AsyncMock(return_value=make_mock_modbus_result([]))
        mock_cls.return_value = new_client
        await coordinator._ensure_connected()
        assert coordinator._last_login is None  # reset on reconnect
        mock_cls.assert_called_once_with(
            coordinator._host, port=coordinator._port,
            trace_connect=coordinator._connection_changed,
        )
        mock_modbus_client.close.assert_called_once()


async def test_each_poll_refreshes_plus_access(
    coordinator: OvumMiraCoordinator, mock_modbus_client: AsyncMock,
) -> None:
    """Display-side activation becomes readable without reloading the integration."""
    from datetime import datetime

    coordinator._last_login = datetime.now()
    authenticated = False

    async def login(
        address: int, values: list[int], *, device_id: int,
    ) -> MagicMock:
        nonlocal authenticated
        authenticated = True
        return make_mock_modbus_result([])

    def read(addr: int, count: int, device_id: int) -> MagicMock:
        words = [0] * count
        if device_id == SLAVE_HSM and addr <= 55022 < addr + count:
            words[55022 - addr] = 1 if authenticated else 32767
        return make_mock_modbus_result(words)

    mock_modbus_client.write_registers.side_effect = login
    mock_modbus_client.read_holding_registers.side_effect = read
    for _ in range(2):
        authenticated = False
        data = await coordinator._async_update_data()
        assert data["hpuf_status"] == 1
    assert mock_modbus_client.write_registers.await_count == 4
    assert all(c.args[0] == 101 for c in mock_modbus_client.write_registers.call_args_list)
    mock_modbus_client.write_register.assert_not_called()


async def test_auto_reconnect_invalidates_login_before_write(
    coordinator: OvumMiraCoordinator, mock_modbus_client: AsyncMock,
) -> None:
    await coordinator._login()
    mock_modbus_client.write_registers.reset_mock()
    coordinator._connection_changed(False)
    coordinator._connection_changed(True)
    assert coordinator._needs_relogin()
    await coordinator.async_write_int16(SLAVE_HSM, 55001, 45)
    assert mock_modbus_client.write_registers.await_count == 2


async def test_reconnect_during_read_discards_unauthenticated_data(
    coordinator: OvumMiraCoordinator,
) -> None:
    calls = 0

    async def read() -> dict[str, int]:
        nonlocal calls
        calls += 1
        if calls == 1:
            coordinator._connection_changed(False)
            coordinator._connection_changed(True)
            return {"hpuf_status": 32767}
        return {"hpuf_status": 1}

    coordinator._read_all = AsyncMock(side_effect=read)
    assert await coordinator._async_update_data() == {"hpuf_status": 1}
    assert calls == 2


async def test_repeated_reconnect_is_bounded(
    coordinator: OvumMiraCoordinator,
) -> None:
    from homeassistant.helpers.update_coordinator import UpdateFailed

    async def read() -> dict[str, int]:
        coordinator._connection_changed(False)
        coordinator._connection_changed(True)
        return {"hpuf_status": 32767}

    coordinator._read_all = AsyncMock(side_effect=read)
    with pytest.raises(UpdateFailed, match="repeatedly changed"):
        await coordinator._async_update_data()
    assert coordinator._read_all.await_count == 2


async def test_reconnect_during_login_cannot_authenticate_new_session(
    coordinator: OvumMiraCoordinator, mock_modbus_client: AsyncMock,
) -> None:
    from homeassistant.helpers.update_coordinator import UpdateFailed

    async def login(
        address: int, values: list[int], *, device_id: int,
    ) -> MagicMock:
        coordinator._connection_changed(False)
        coordinator._connection_changed(True)
        return make_mock_modbus_result([])

    mock_modbus_client.write_registers.side_effect = login
    with pytest.raises(UpdateFailed, match="during login"):
        await coordinator._login()
    assert coordinator._last_login is None


async def test_failed_login_prevents_reading(
    coordinator: OvumMiraCoordinator, mock_modbus_client: AsyncMock,
) -> None:
    from homeassistant.helpers.update_coordinator import UpdateFailed

    mock_modbus_client.write_registers.return_value = make_mock_modbus_result([], is_error=True)
    with pytest.raises(UpdateFailed, match="Login FC16 failed"):
        await coordinator._async_update_data()
    mock_modbus_client.read_holding_registers.assert_not_called()
    assert coordinator._last_login is None


async def test_authenticated_missing_sensor_does_not_trigger_retry(
    coordinator: OvumMiraCoordinator,
) -> None:
    coordinator._read_all = AsyncMock(return_value={"hk3_actualvalue": float("nan")})
    data = await coordinator._async_update_data()
    import math
    assert math.isnan(data["hk3_actualvalue"])
    coordinator._read_all.assert_awaited_once()
