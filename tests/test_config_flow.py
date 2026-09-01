"""Tests for OvumMira Config Flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.ovum_mira.config_flow import _test_connection
from custom_components.ovum_mira.const import Level

from .conftest import TEST_HOST, TEST_PORT, make_mock_modbus_result


@pytest.mark.asyncio
async def test_connection_success() -> None:
    with patch("custom_components.ovum_mira.config_flow.AsyncModbusTcpClient") as mock_cls:
        client = AsyncMock()
        client.connect = AsyncMock(return_value=True)
        client.write_registers = AsyncMock(return_value=make_mock_modbus_result([]))
        client.close = lambda: None
        mock_cls.return_value = client
        result = await _test_connection(TEST_HOST, TEST_PORT)
        assert result is None


@pytest.mark.asyncio
async def test_connection_refused() -> None:
    with patch("custom_components.ovum_mira.config_flow.AsyncModbusTcpClient") as mock_cls:
        client = AsyncMock()
        client.connect = AsyncMock(return_value=False)
        client.close = lambda: None
        mock_cls.return_value = client
        result = await _test_connection(TEST_HOST, TEST_PORT)
        assert result == "cannot_connect"


@pytest.mark.asyncio
async def test_login_failed() -> None:
    with patch("custom_components.ovum_mira.config_flow.AsyncModbusTcpClient") as mock_cls:
        client = AsyncMock()
        client.connect = AsyncMock(return_value=True)
        client.write_registers = AsyncMock(return_value=make_mock_modbus_result([], is_error=True))
        client.close = lambda: None
        mock_cls.return_value = client
        result = await _test_connection(TEST_HOST, TEST_PORT)
        assert result == "login_failed"


def test_level_enum_ordering() -> None:
    assert Level.L1 < Level.L2 < Level.L3
