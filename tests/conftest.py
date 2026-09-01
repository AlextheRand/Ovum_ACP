"""Test fixtures for Ovum MIRA integration tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ovum_mira.const import DOMAIN, Level
from custom_components.ovum_mira.coordinator import (
    CONF_COOLING,
    CONF_HOST,
    CONF_LEVEL,
    CONF_NUM_HK,
    CONF_NUM_WPM,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_WW_INTERNAL,
)

TEST_HOST = "192.168.178.82"
TEST_PORT = 502

MOCK_CONFIG_DATA: dict[str, Any] = {
    CONF_HOST: TEST_HOST,
    CONF_PORT: TEST_PORT,
    CONF_SCAN_INTERVAL: 30,
    CONF_LEVEL: Level.L2,
    CONF_NUM_HK: 2,
    CONF_NUM_WPM: 1,
    CONF_WW_INTERNAL: False,
    CONF_COOLING: False,
}


def make_mock_modbus_result(registers: list[int], is_error: bool = False) -> MagicMock:
    result = MagicMock()
    result.isError.return_value = is_error
    result.registers = registers
    return result


@pytest.fixture
def mock_modbus_client():
    """Patch AsyncModbusTcpClient with a mock that always connects and logins successfully."""
    with patch(
        "custom_components.ovum_mira.coordinator.AsyncModbusTcpClient"
    ) as mock_cls:
        client = AsyncMock()
        client.connected = True
        client.connect = AsyncMock(return_value=True)
        client.close = MagicMock()
        # Default: write_registers always succeeds
        client.write_registers = AsyncMock(
            return_value=make_mock_modbus_result([])
        )
        # Default: read_holding_registers returns zeros
        client.read_holding_registers = AsyncMock(
            side_effect=lambda addr, count, slave: make_mock_modbus_result([0] * count)
        )
        client.read_input_registers = AsyncMock(
            side_effect=lambda addr, count, slave: make_mock_modbus_result([0] * count)
        )
        mock_cls.return_value = client
        yield client
