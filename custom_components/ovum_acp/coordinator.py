"""DataUpdateCoordinator for Ovum MIRA: Login, Batch-Read, Write."""

from __future__ import annotations

import asyncio
import logging
import struct
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

try:
    from pymodbus.client import AsyncModbusTcpClient
    from pymodbus.exceptions import ModbusException
except ImportError as exc:
    raise ImportError(
        "pymodbus is required for ovum_mira. "
        "It is bundled with HA's built-in modbus integration. "
        f"Original error: {exc}"
    ) from exc

from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FC,
    DataType,
    Level,
    LOGIN_ADDRESS,
    LOGIN_INTERVAL_SECONDS,
    SLAVE_HSM,
    SLAVE_WPM_BASE,
    RegisterDef,
    build_register_list,
)

_LOGGER = logging.getLogger(__name__)

CONF_HOST = "host"
CONF_PORT = "port"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_LEVEL = "level"
CONF_NUM_HK = "num_hk"
CONF_NUM_WPM = "num_wpm"
CONF_WW_INTERNAL = "ww_internal"
CONF_COOLING = "cooling"
CONF_LOGIN_CODE = "login_code"
CONF_HK_TYPES = "hk_types"


def _decode_value(registers: list[int], data_type: DataType) -> float | int | bool:
    if data_type == DataType.FLOAT32:
        raw = struct.pack(">HH", registers[0], registers[1])
        value = struct.unpack(">f", raw)[0]
        # Sentinel: FLT_MAX or similar → treat as unavailable
        if abs(value) > 1e30:
            return float("nan")
        return round(value, 2)
    if data_type == DataType.INT32:
        raw = struct.pack(">HH", registers[0], registers[1])
        return struct.unpack(">i", raw)[0]
    if data_type == DataType.INT16:
        raw = struct.pack(">H", registers[0])
        return struct.unpack(">h", raw)[0]
    if data_type == DataType.UINT16:
        return registers[0]
    if data_type == DataType.BOOL:
        return bool(registers[0])
    raise ValueError(f"Unknown DataType: {data_type}")


def _encode_int16(value: int) -> list[int]:
    raw = struct.pack(">h", value)
    return list(struct.unpack(">H", raw))


def _encode_float32(value: float) -> list[int]:
    raw = struct.pack(">f", value)
    return list(struct.unpack(">HH", raw))


class OvumMiraCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manages Modbus TCP connection, login, reads and writes to the MIRA."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        def _get(key: str, default: Any) -> Any:
            return entry.options.get(key, entry.data.get(key, default))

        self._host: str = _get(CONF_HOST, "")
        self._port: int = _get(CONF_PORT, 502)
        self._level = Level(_get(CONF_LEVEL, Level.L1))
        self._num_hk: int = _get(CONF_NUM_HK, 1)
        self._num_wpm: int = _get(CONF_NUM_WPM, 1)
        self._ww_internal: bool = _get(CONF_WW_INTERNAL, False)
        self._cooling: bool = _get(CONF_COOLING, False)

        login_code: int = _get(CONF_LOGIN_CODE, 1)
        self._login_payload: list[int] = [
            (login_code >> 16) & 0xFFFF,
            login_code & 0xFFFF,
        ]

        scan_interval = _get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

        self._client: AsyncModbusTcpClient | None = None
        self._last_login: datetime | None = None
        self._lock = asyncio.Lock()

        self.registers: list[RegisterDef] = build_register_list(
            self._level, self._num_hk, self._num_wpm, self._ww_internal, self._cooling
        )
        _LOGGER.debug("Coordinator: %d registers active", len(self.registers))

    # ------------------------------------------------------------------
    # Connection + Login
    # ------------------------------------------------------------------

    async def _ensure_connected(self) -> None:
        if self._client is None or not self._client.connected:
            self._client = AsyncModbusTcpClient(self._host, port=self._port)
            connected = await self._client.connect()
            if not connected:
                raise UpdateFailed(f"Cannot connect to MIRA at {self._host}:{self._port}")
            self._last_login = None  # Force re-login after reconnect

    async def _login(self) -> None:
        """Send FC16 login to all required slaves."""
        if self._client is None:
            return
        slaves_to_login = [SLAVE_HSM] + [
            SLAVE_WPM_BASE + i for i in range(self._num_wpm)
        ]
        for slave in slaves_to_login:
            result = await self._client.write_registers(
                LOGIN_ADDRESS, self._login_payload, device_id=slave
            )
            if result.isError():
                raise UpdateFailed(f"Login FC16 failed on slave {slave}: {result}")
        await asyncio.sleep(0.5)
        self._last_login = datetime.now()
        _LOGGER.debug("MIRA login successful (%d slaves)", len(slaves_to_login))

    def _needs_relogin(self) -> bool:
        if self._last_login is None:
            return True
        return (datetime.now() - self._last_login).total_seconds() > LOGIN_INTERVAL_SECONDS

    # ------------------------------------------------------------------
    # Batch-Read
    # ------------------------------------------------------------------

    async def _read_all(self) -> dict[str, Any]:
        """Group registers by (slave, fc, contiguous address range) and batch-read."""
        if self._client is None:
            raise UpdateFailed("No client")

        # Group: (slave, fc) → sorted list of RegisterDef
        groups: dict[tuple[int, FC], list[RegisterDef]] = {}
        for reg in self.registers:
            key = (reg.slave, reg.fc)
            groups.setdefault(key, []).append(reg)
        for key in groups:
            groups[key].sort(key=lambda r: r.address)

        data: dict[str, Any] = {}

        for (slave, fc), regs in groups.items():
            # Build contiguous batches (gap ≤ 4 registers → merge)
            batches: list[tuple[int, int]] = []  # (start_addr, end_addr_exclusive)
            batch_start = regs[0].address
            batch_end = regs[0].address + regs[0].count

            for reg in regs[1:]:
                if reg.address <= batch_end + 4:
                    batch_end = max(batch_end, reg.address + reg.count)
                else:
                    batches.append((batch_start, batch_end))
                    batch_start = reg.address
                    batch_end = reg.address + reg.count
            batches.append((batch_start, batch_end))

            # Execute batch reads
            raw_regs: dict[int, int] = {}
            for start, end in batches:
                count = end - start
                try:
                    if fc == FC.FC4:
                        result = await self._client.read_input_registers(
                            start, count=count, device_id=slave
                        )
                    else:
                        result = await self._client.read_holding_registers(
                            start, count=count, device_id=slave
                        )
                    if result.isError():
                        _LOGGER.warning(
                            "Read error slave=%d fc=%d addr=%d count=%d: %s",
                            slave, fc, start, count, result,
                        )
                        continue
                    for i, val in enumerate(result.registers):
                        raw_regs[start + i] = val
                except (ModbusException, asyncio.TimeoutError) as exc:
                    _LOGGER.warning("Read exception slave=%d addr=%d: %s", slave, start, exc)

            # Decode
            for reg in regs:
                try:
                    reg_values = [
                        raw_regs[reg.address + i] for i in range(reg.count)
                    ]
                    data[reg.name] = _decode_value(reg_values, reg.data_type)
                except KeyError:
                    _LOGGER.debug("Register %s not in raw read result (addr=%d)", reg.name, reg.address)
                except (struct.error, ValueError) as exc:
                    _LOGGER.warning("Decode error %s: %s", reg.name, exc)

        return data

    # ------------------------------------------------------------------
    # DataUpdateCoordinator interface
    # ------------------------------------------------------------------

    async def _async_setup(self) -> None:
        async with self._lock:
            await self._ensure_connected()
            await self._login()

    async def _async_update_data(self) -> dict[str, Any]:
        async with self._lock:
            try:
                await self._ensure_connected()
                if self._needs_relogin():
                    await self._login()
                return await self._read_all()
            except UpdateFailed:
                raise
            except Exception as exc:
                raise UpdateFailed(f"Unexpected error reading MIRA: {exc}") from exc

    async def async_shutdown(self) -> None:
        if self._client and self._client.connected:
            self._client.close()
        self._client = None

    # ------------------------------------------------------------------
    # Write helpers (called by writable entities)
    # ------------------------------------------------------------------

    async def _write_single_with_retry(self, slave: int, address: int, value: int) -> None:
        """FC06 write single register with one re-login retry.

        Use for single-word values (INT16, UINT16, BOOL, P_WAHL, P_INT) per MIRA documentation.
        """
        if self._client is None:
            raise RuntimeError("No Modbus client")
        try:
            result = await self._client.write_register(address, value, device_id=slave)
            if result.isError():
                _LOGGER.warning("Write FC06 error addr=%d: %s — retrying after re-login", address, result)
                await self._login()
                result = await self._client.write_register(address, value, device_id=slave)
                if result.isError():
                    raise RuntimeError(f"Write FC06 failed after retry: {result}")
        except (ModbusException, asyncio.TimeoutError) as exc:
            _LOGGER.warning("Write FC06 exception addr=%d: %s — retrying", address, exc)
            await self._ensure_connected()
            await self._login()
            result = await self._client.write_register(address, value, device_id=slave)
            if result.isError():
                raise RuntimeError(f"Write FC06 failed after reconnect: {result}") from exc

    async def _write_with_retry(
        self, slave: int, address: int, values: list[int]
    ) -> None:
        """FC16 write multiple registers with one re-login retry.

        Use for multi-word values (FLOAT32, INT32) per MIRA documentation.
        """
        if self._client is None:
            raise RuntimeError("No Modbus client")
        try:
            result = await self._client.write_registers(address, values, device_id=slave)
            if result.isError():
                _LOGGER.warning("Write FC16 error addr=%d: %s — retrying after re-login", address, result)
                await self._login()
                result = await self._client.write_registers(address, values, device_id=slave)
                if result.isError():
                    raise RuntimeError(f"Write FC16 failed after retry: {result}")
        except (ModbusException, asyncio.TimeoutError) as exc:
            _LOGGER.warning("Write FC16 exception addr=%d: %s — retrying", address, exc)
            await self._ensure_connected()
            await self._login()
            result = await self._client.write_registers(address, values, device_id=slave)
            if result.isError():
                raise RuntimeError(f"Write FC16 failed after reconnect: {result}") from exc

    async def async_write_int16(self, slave: int, address: int, value: int) -> None:
        async with self._lock:
            await self._ensure_connected()
            if self._needs_relogin():
                await self._login()
            await self._write_single_with_retry(slave, address, _encode_int16(value)[0])

    async def async_write_float32(self, slave: int, address: int, value: float) -> None:
        async with self._lock:
            await self._ensure_connected()
            if self._needs_relogin():
                await self._login()
            await self._write_with_retry(slave, address, _encode_float32(value))

    async def async_write_register(self, reg_name: str, value: int | float) -> None:
        """Write by register name (looks up address/type from register list)."""
        for reg in self.registers:
            if reg.name == reg_name:
                if not reg.writable:
                    raise ValueError(f"Register {reg_name} is not writable")
                if reg.data_type == DataType.FLOAT32:
                    await self.async_write_float32(reg.slave, reg.address, float(value))
                else:
                    await self.async_write_int16(reg.slave, reg.address, int(value))
                await self.async_request_refresh()
                return
        raise KeyError(f"Register {reg_name} not found in active register list")
