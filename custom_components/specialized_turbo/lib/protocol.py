"""
Specialized Turbo BLE Protocol Definition (Gen 2 — "TURBOHMI2017")

This module defines the BLE service/characteristic UUIDs, message format,
sender/channel enums, and parsing logic for the Specialized Turbo e-bike
Bluetooth Low Energy protocol.

Protocol reverse-engineered from the Sepp62/LevoEsp32Ble project (MIT).
UUID base encodes "TURBOHMI2017" in reverse ASCII in its lower bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import NamedTuple

# ---------------------------------------------------------------------------
# UUID definitions
# ---------------------------------------------------------------------------

# Base UUID: 000000xx-3731-3032-494d-484f42525554
# Last 12 bytes = "7102IMHOBRUT" = reverse of "TURBOHMI2017"
UUID_BASE = "0000{:04x}-3731-3032-494d-484f42525554"


def _uuid(short: int) -> str:
    """Expand a 16-bit short UUID into the full Specialized 128-bit UUID string."""
    return UUID_BASE.format(short)


# Service UUIDs
SERVICE_DATA_NOTIFY = _uuid(0x0003)  # Notification data service
SERVICE_DATA_REQUEST = _uuid(0x0001)  # Request-read service
SERVICE_DATA_WRITE = _uuid(0x0002)  # Write command service

# Characteristic UUIDs
CHAR_NOTIFY = _uuid(0x0013)  # READ, NOTIFY — bike pushes telemetry here
CHAR_REQUEST_WRITE = _uuid(0x0021)  # WRITE — send a 2-byte request here
CHAR_REQUEST_READ = _uuid(0x0011)  # READ — read the response after writing to 0x0021
CHAR_WRITE = _uuid(0x0012)  # WRITE — send commands (assist level, settings)

# Nordic Semiconductor BLE company ID (used in manufacturer advertising data)
NORDIC_COMPANY_ID = 0x0059

# Magic advertising string embedded in manufacturer data bytes [2:10]
ADVERTISING_MAGIC = b"TURBOHMI"

# ---------------------------------------------------------------------------
# Protocol enums
# ---------------------------------------------------------------------------


class Sender(IntEnum):
    """Identifies the subsystem that produced a message."""

    BATTERY = 0x00
    MOTOR = 0x01  # Motor / rider data
    BIKE_SETTINGS = 0x02
    UNKNOWN_03 = 0x03
    BATTERY_2 = 0x04  # Secondary / range-extender battery (same channels as BATTERY)


class BatteryChannel(IntEnum):
    """Channels for Sender.BATTERY (0x00) and Sender.BATTERY_2 (0x04)."""

    SIZE_WH = 0x00
    REMAIN_WH = 0x01
    HEALTH = 0x02
    TEMP = 0x03
    CHARGE_CYCLES = 0x04
    VOLTAGE = 0x05
    CURRENT = 0x06
    CHARGE_PERCENT = 0x0C


class MotorChannel(IntEnum):
    """Channels for Sender.MOTOR (0x01)."""

    RIDER_POWER = 0x00
    CADENCE = 0x01
    SPEED = 0x02
    ODOMETER = 0x04
    ASSIST_LEVEL = 0x05
    MOTOR_TEMP = 0x07
    MOTOR_POWER = 0x0C
    PEAK_ASSIST = 0x10
    SHUTTLE = 0x15


class BikeSettingsChannel(IntEnum):
    """Channels for Sender.BIKE_SETTINGS (0x02)."""

    WHEEL_CIRCUMFERENCE = 0x00
    ASSIST_LEV1 = 0x03
    ASSIST_LEV2 = 0x04
    ASSIST_LEV3 = 0x05
    FAKE_CHANNEL = 0x06
    ACCELERATION = 0x07


class AssistLevel(IntEnum):
    """Assist mode enum — written or read via MotorChannel.ASSIST_LEVEL."""

    OFF = 0
    ECO = 1
    TRAIL = 2
    TURBO = 3


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def _int_from_bytes(data: bytes, offset: int, size: int) -> int:
    """Extract a little-endian unsigned integer of *size* bytes starting at *offset*."""
    return int.from_bytes(
        data[offset : offset + size], byteorder="little", signed=False
    )


# Lookup: (sender, channel) → (data_size_bytes, human_name, unit, conversion_fn)
# conversion_fn takes the raw integer and returns a float/int in human units.

_FIELD_DEFS: dict[tuple[int, int], FieldDefinition] = {}


@dataclass(frozen=True, slots=True)
class FieldDefinition:
    """Metadata for a single protocol field."""

    sender: int
    channel: int
    name: str
    unit: str
    data_size: int  # bytes of payload (after sender+channel)
    convert: object  # callable(int) -> float | int

    @property
    def key(self) -> tuple[int, int]:
        return (self.sender, self.channel)


def _reg(
    sender: int, channel: int, name: str, unit: str, size: int, convert=None
) -> FieldDefinition:
    if convert is None:
        convert = lambda v: v  # noqa: E731  identity
    fd = FieldDefinition(
        sender=sender,
        channel=channel,
        name=name,
        unit=unit,
        data_size=size,
        convert=convert,
    )
    _FIELD_DEFS[fd.key] = fd
    return fd


# --- Battery fields (sender 0x00 / 0x04) ---
_reg(0x00, 0x00, "battery_capacity_wh", "Wh", 2, lambda v: round(v * 1.1111))
_reg(0x00, 0x01, "battery_remaining_wh", "Wh", 2, lambda v: round(v * 1.1111))
_reg(0x00, 0x02, "battery_health", "%", 1)
_reg(0x00, 0x03, "battery_temp", "°C", 1)
_reg(0x00, 0x04, "battery_charge_cycles", "cycles", 2)
_reg(0x00, 0x05, "battery_voltage", "V", 1, lambda v: v / 5.0 + 20.0)
_reg(0x00, 0x06, "battery_current", "A", 1, lambda v: v / 5.0)
_reg(0x00, 0x0C, "battery_charge_percent", "%", 1)

# --- Motor / rider fields (sender 0x01) ---
_reg(0x01, 0x00, "rider_power", "W", 2)
_reg(0x01, 0x01, "cadence", "RPM", 2, lambda v: v / 10.0)
_reg(0x01, 0x02, "speed", "km/h", 2, lambda v: v / 10.0)
_reg(0x01, 0x04, "odometer", "km", 4, lambda v: v / 1000.0)
_reg(
    0x01,
    0x05,
    "assist_level",
    "",
    2,
    lambda v: AssistLevel(v) if v in AssistLevel._value2member_map_ else v,
)
_reg(0x01, 0x07, "motor_temp", "°C", 1)
_reg(0x01, 0x0C, "motor_power", "W", 2)
_reg(0x01, 0x10, "peak_assist", "", 3)  # 3 bytes: ECO%, TRAIL%, TURBO%
_reg(0x01, 0x15, "shuttle", "", 1)

# --- Bike settings fields (sender 0x02) ---
_reg(0x02, 0x00, "wheel_circumference", "mm", 2)
_reg(0x02, 0x03, "assist_lev1_pct", "%", 1)
_reg(0x02, 0x04, "assist_lev2_pct", "%", 1)
_reg(0x02, 0x05, "assist_lev3_pct", "%", 1)
_reg(0x02, 0x06, "fake_channel", "", 1)
_reg(0x02, 0x07, "acceleration", "%", 2, lambda v: (v - 3000) / 60.0)

# Duplicate battery fields for secondary battery (sender 0x04) — same channels
for _ch in list(BatteryChannel):
    _orig = _FIELD_DEFS.get((0x00, _ch))
    if _orig:
        _reg(
            0x04,
            _ch,
            _orig.name.replace("battery_", "battery2_"),
            _orig.unit,
            _orig.data_size,
            _orig.convert,
        )


def get_field_def(sender: int, channel: int) -> FieldDefinition | None:
    """Return the field definition for a (sender, channel) pair, or None."""
    return _FIELD_DEFS.get((sender, channel))


def all_field_defs() -> dict[tuple[int, int], FieldDefinition]:
    """Return a copy of all registered field definitions."""
    return dict(_FIELD_DEFS)


# ---------------------------------------------------------------------------
# Message parsing
# ---------------------------------------------------------------------------


class ParsedMessage(NamedTuple):
    """Result of parsing a single BLE notification or read-response."""

    sender: int
    channel: int
    raw_value: int
    converted_value: float | int | AssistLevel
    field_name: str | None  # None if field is unknown
    unit: str


def parse_message(data: bytes | bytearray) -> ParsedMessage:
    """
    Parse a raw BLE notification/read payload into a structured result.

    The message format is::

        [sender: 1B] [channel: 1B] [data: 1-4B little-endian]

    Parameters
    ----------
    data : bytes
        Raw bytes received from the CHAR_NOTIFY or CHAR_REQUEST_READ characteristic.

    Returns
    -------
    ParsedMessage
        Decoded message with raw and converted values.

    Raises
    ------
    ValueError
        If data is too short (< 3 bytes).
    """
    if len(data) < 3:
        raise ValueError(f"Message too short ({len(data)} bytes), need at least 3")

    sender = data[0]
    channel = data[1]
    payload = data[2:]

    field_def = get_field_def(sender, channel)

    if field_def is not None:
        raw = _int_from_bytes(data, 2, field_def.data_size)
        converted = field_def.convert(raw)
        return ParsedMessage(
            sender=sender,
            channel=channel,
            raw_value=raw,
            converted_value=converted,
            field_name=field_def.name,
            unit=field_def.unit,
        )
    else:
        # Unknown field — extract as many bytes as available
        raw = _int_from_bytes(data, 2, len(payload))
        return ParsedMessage(
            sender=sender,
            channel=channel,
            raw_value=raw,
            converted_value=raw,
            field_name=None,
            unit="",
        )


def is_specialized_advertisement(manufacturer_data: dict[int, bytes]) -> bool:
    """
    Check whether BLE advertisement manufacturer data belongs to a Specialized Turbo bike.

    Parameters
    ----------
    manufacturer_data : dict[int, bytes]
        Mapping of company ID → manufacturer-specific data bytes,
        as returned by ``bleak.backends.scanner.AdvertisementData.manufacturer_data``.

    Returns
    -------
    bool
        True if the data contains the TURBOHMI magic bytes under the Nordic company ID.
    """
    payload = manufacturer_data.get(NORDIC_COMPANY_ID)
    if payload is None:
        return False
    # The "TURBOHMI" string appears at bytes [0:8] of the payload
    # (company ID already stripped by bleak)
    return ADVERTISING_MAGIC in payload


# ---------------------------------------------------------------------------
# Command builders (read-only focus, but included for completeness)
# ---------------------------------------------------------------------------


def build_request(sender: int, channel: int) -> bytes:
    """
    Build the 2-byte payload to write to CHAR_REQUEST_WRITE
    in order to query a specific field value.
    """
    return bytes([sender, channel])
