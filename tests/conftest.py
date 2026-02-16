"""Fixtures for Specialized Turbo integration tests."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import MagicMock

# Windows requires SelectorEventLoop for compatibility with pytest-homeassistant
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

MOCK_ADDRESS = "DC:DD:BB:4A:D6:55"
MOCK_ADDRESS_FORMATTED = "dc:dd:bb:4a:d6:55"
MOCK_NAME = "SPECIALIZED"
MOCK_MANUFACTURER_DATA: dict[int, bytes] = {0x0059: b"TURBOHMItest1234"}


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
