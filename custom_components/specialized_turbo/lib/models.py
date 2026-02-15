"""
Data models for Specialized Turbo bike telemetry.

Provides mutable dataclass containers that accumulate decoded BLE messages
into a coherent snapshot of the bike's state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .protocol import (
    AssistLevel,
    ParsedMessage,
    Sender,
    BatteryChannel,
    MotorChannel,
    BikeSettingsChannel,
)


@dataclass
class BatteryState:
    """Snapshot of a single battery pack."""

    capacity_wh: float | None = None
    remaining_wh: float | None = None
    health_pct: int | None = None
    temp_c: int | None = None
    charge_cycles: int | None = None
    voltage_v: float | None = None
    current_a: float | None = None
    charge_pct: int | None = None

    _CHANNEL_MAP: dict[int, str] = field(default_factory=lambda: {
        BatteryChannel.SIZE_WH: "capacity_wh",
        BatteryChannel.REMAIN_WH: "remaining_wh",
        BatteryChannel.HEALTH: "health_pct",
        BatteryChannel.TEMP: "temp_c",
        BatteryChannel.CHARGE_CYCLES: "charge_cycles",
        BatteryChannel.VOLTAGE: "voltage_v",
        BatteryChannel.CURRENT: "current_a",
        BatteryChannel.CHARGE_PERCENT: "charge_pct",
    }, repr=False)

    def update(self, channel: int, value: Any) -> bool:
        """Update a field from a parsed message. Returns True if field was known."""
        attr = self._CHANNEL_MAP.get(channel)
        if attr is not None:
            setattr(self, attr, value)
            return True
        return False

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in {
            "capacity_wh": self.capacity_wh,
            "remaining_wh": self.remaining_wh,
            "health_pct": self.health_pct,
            "temp_c": self.temp_c,
            "charge_cycles": self.charge_cycles,
            "voltage_v": self.voltage_v,
            "current_a": self.current_a,
            "charge_pct": self.charge_pct,
        }.items() if v is not None}


@dataclass
class MotorState:
    """Snapshot of motor and rider data."""

    rider_power_w: float | None = None
    cadence_rpm: float | None = None
    speed_kmh: float | None = None
    odometer_km: float | None = None
    assist_level: AssistLevel | int | None = None
    motor_temp_c: int | None = None
    motor_power_w: float | None = None
    peak_assist: tuple[int, int, int] | None = None
    shuttle: int | None = None

    _CHANNEL_MAP: dict[int, str] = field(default_factory=lambda: {
        MotorChannel.RIDER_POWER: "rider_power_w",
        MotorChannel.CADENCE: "cadence_rpm",
        MotorChannel.SPEED: "speed_kmh",
        MotorChannel.ODOMETER: "odometer_km",
        MotorChannel.ASSIST_LEVEL: "assist_level",
        MotorChannel.MOTOR_TEMP: "motor_temp_c",
        MotorChannel.MOTOR_POWER: "motor_power_w",
        MotorChannel.PEAK_ASSIST: "peak_assist",
        MotorChannel.SHUTTLE: "shuttle",
    }, repr=False)

    def update(self, channel: int, value: Any) -> bool:
        """Update a field from a parsed message. Returns True if field was known."""
        attr = self._CHANNEL_MAP.get(channel)
        if attr is not None:
            setattr(self, attr, value)
            return True
        return False

    def as_dict(self) -> dict[str, Any]:
        assist = self.assist_level
        if isinstance(assist, AssistLevel):
            assist = assist.name
        return {k: v for k, v in {
            "rider_power_w": self.rider_power_w,
            "cadence_rpm": self.cadence_rpm,
            "speed_kmh": self.speed_kmh,
            "odometer_km": self.odometer_km,
            "assist_level": assist,
            "motor_temp_c": self.motor_temp_c,
            "motor_power_w": self.motor_power_w,
            "peak_assist": self.peak_assist,
            "shuttle": self.shuttle,
        }.items() if v is not None}


@dataclass
class BikeSettings:
    """Snapshot of bike configuration values."""

    wheel_circumference_mm: int | None = None
    assist_lev1_pct: int | None = None
    assist_lev2_pct: int | None = None
    assist_lev3_pct: int | None = None
    fake_channel: int | None = None
    acceleration_pct: float | None = None

    _CHANNEL_MAP: dict[int, str] = field(default_factory=lambda: {
        BikeSettingsChannel.WHEEL_CIRCUMFERENCE: "wheel_circumference_mm",
        BikeSettingsChannel.ASSIST_LEV1: "assist_lev1_pct",
        BikeSettingsChannel.ASSIST_LEV2: "assist_lev2_pct",
        BikeSettingsChannel.ASSIST_LEV3: "assist_lev3_pct",
        BikeSettingsChannel.FAKE_CHANNEL: "fake_channel",
        BikeSettingsChannel.ACCELERATION: "acceleration_pct",
    }, repr=False)

    def update(self, channel: int, value: Any) -> bool:
        """Update a field from a parsed message. Returns True if field was known."""
        attr = self._CHANNEL_MAP.get(channel)
        if attr is not None:
            setattr(self, attr, value)
            return True
        return False

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in {
            "wheel_circumference_mm": self.wheel_circumference_mm,
            "assist_lev1_pct": self.assist_lev1_pct,
            "assist_lev2_pct": self.assist_lev2_pct,
            "assist_lev3_pct": self.assist_lev3_pct,
            "fake_channel": self.fake_channel,
            "acceleration_pct": self.acceleration_pct,
        }.items() if v is not None}


@dataclass
class TelemetrySnapshot:
    """
    Aggregated view of all bike telemetry, updated incrementally as
    BLE notifications arrive.

    This is the main object you interact with — it collects data from
    all senders into a single coherent state.
    """

    battery: BatteryState = field(default_factory=BatteryState)
    battery2: BatteryState = field(default_factory=BatteryState)
    motor: MotorState = field(default_factory=MotorState)
    settings: BikeSettings = field(default_factory=BikeSettings)
    last_updated: float = field(default_factory=time.monotonic)
    message_count: int = 0
    unknown_messages: list[ParsedMessage] = field(default_factory=list, repr=False)

    def update_from_message(self, msg: ParsedMessage) -> None:
        """
        Route a parsed BLE message to the appropriate sub-model.

        Parameters
        ----------
        msg : ParsedMessage
            A message decoded by ``protocol.parse_message()``.
        """
        self.last_updated = time.monotonic()
        self.message_count += 1

        sender = msg.sender
        channel = msg.channel
        value = msg.converted_value

        if sender == Sender.BATTERY:
            if not self.battery.update(channel, value):
                self.unknown_messages.append(msg)
        elif sender == Sender.BATTERY_2:
            if not self.battery2.update(channel, value):
                self.unknown_messages.append(msg)
        elif sender == Sender.MOTOR:
            if not self.motor.update(channel, value):
                self.unknown_messages.append(msg)
        elif sender == Sender.BIKE_SETTINGS:
            if not self.settings.update(channel, value):
                self.unknown_messages.append(msg)
        else:
            self.unknown_messages.append(msg)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary of all known values."""
        result: dict[str, Any] = {}
        result["battery"] = self.battery.as_dict()
        batt2 = self.battery2.as_dict()
        if batt2:
            result["battery2"] = batt2
        result["motor"] = self.motor.as_dict()
        settings = self.settings.as_dict()
        if settings:
            result["settings"] = settings
        result["message_count"] = self.message_count
        return result
