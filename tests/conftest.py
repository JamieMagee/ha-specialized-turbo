"""Fixtures for Specialized Turbo integration tests."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import MagicMock

import pytest

# Windows requires SelectorEventLoop for compatibility with pytest-homeassistant
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:  # noqa: PT004
    """Enable custom integrations in all tests."""
    return


@pytest.fixture(autouse=True)
def mock_bluetooth(  # noqa: PT004
    mock_bleak_scanner_start: MagicMock,
    mock_bluetooth_adapters: None,
) -> None:
    """Mock out bluetooth from starting."""
    return


MOCK_ADDRESS = "DC:DD:BB:4A:D6:55"
MOCK_ADDRESS_FORMATTED = "dc:dd:bb:4a:d6:55"
MOCK_NAME = "SPECIALIZED"
MOCK_MANUFACTURER_DATA: dict[int, bytes] = {0x0059: b"TURBOHMItest1234"}

# TCU1 (2018 Levo) test data
MOCK_GEN1_ADDRESS = "C6:1A:10:12:5E:48"
MOCK_GEN1_ADDRESS_FORMATTED = "c6:1a:10:12:5e:48"
MOCK_GEN1_NAME = "SPECIALIZED"
MOCK_GEN1_MANUFACTURER_DATA: dict[int, bytes] = {
    0x020D: bytes.fromhex("028657" + "ff" * 24),
}


def make_service_info(
    name: str = MOCK_NAME,
    address: str = MOCK_ADDRESS,
    manufacturer_data: dict[int, bytes] | None = None,
) -> MagicMock:
    """Create a mock BluetoothServiceInfoBleak."""
    info = MagicMock()
    info.name = name
    info.address = address
    info.manufacturer_data = (
        manufacturer_data if manufacturer_data is not None else MOCK_MANUFACTURER_DATA
    )
    return info


def make_tcu1_service_info(
    name: str = MOCK_GEN1_NAME,
    address: str = MOCK_GEN1_ADDRESS,
    manufacturer_data: dict[int, bytes] | None = None,
) -> MagicMock:
    """Create a mock BluetoothServiceInfoBleak for a TCU1 bike."""
    info = MagicMock()
    info.name = name
    info.address = address
    info.manufacturer_data = (
        manufacturer_data
        if manufacturer_data is not None
        else MOCK_GEN1_MANUFACTURER_DATA
    )
    return info
