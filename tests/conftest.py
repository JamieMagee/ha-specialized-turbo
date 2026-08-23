"""Fixtures for Specialized Turbo integration tests."""

from __future__ import annotations

import asyncio
import base64
import sys
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from specialized_turbo import PRODUCTION_WRAPPING_KEY

# Windows requires SelectorEventLoop for compatibility with pytest-homeassistant
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in all tests."""
    return


@pytest.fixture(autouse=True)
def mock_bluetooth(
    mock_bleak_scanner_start: MagicMock,
    mock_bluetooth_adapters: None,
) -> None:
    """Mock out bluetooth from starting."""
    return


MOCK_ADDRESS = "DC:DD:BB:4A:D6:55"
MOCK_ADDRESS_FORMATTED = "dc:dd:bb:4a:d6:55"
MOCK_NAME = "SPECIALIZED"
MOCK_MANUFACTURER_DATA: dict[int, bytes] = {0x0059: b"TURBOHMItest1234"}
MOCK_ENCRYPTED_MANUFACTURER_DATA: dict[int, bytes] = {
    0x0059: bytes.fromhex("dac8c404423333330601")
}

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
    info.service_uuids = []
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
    info.service_uuids = []
    return info


def make_wrapped_key(
    key: bytes = bytes.fromhex("00112233445566778899aabbccddeeff"),
) -> str:
    """Build a valid wrapped key for config-flow tests."""
    wrapping_iv = bytes(range(16))
    cipher = Cipher(
        algorithms.AES(PRODUCTION_WRAPPING_KEY),
        modes.CTR(wrapping_iv),
    )
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(key.hex().encode()) + encryptor.finalize()
    return base64.b64encode(wrapping_iv + encrypted).decode()
