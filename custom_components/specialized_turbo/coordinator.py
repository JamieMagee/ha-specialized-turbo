"""BLE coordinator for Specialized Turbo bikes.

Connects over BLE, subscribes to GATT notifications, parses incoming
telemetry, and pushes updates to HA entities.

Gen 1 bikes only push a handful of fields via notifications. The
coordinator uses the request-read GATT pattern to poll the remaining
fields periodically.
"""

from __future__ import annotations

import asyncio
import logging
import time

from bleak import BleakClient, BleakError
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak_retry_connector import establish_connection

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.active_update_coordinator import (
    ActiveBluetoothDataUpdateCoordinator,
)
from homeassistant.core import HomeAssistant, callback

from specialized_turbo import (
    CHAR_NOTIFY,
    GEN1_POLL_FIELDS,
    ProtocolGeneration,
    TelemetrySnapshot,
    build_request,
    detect_generation,
    get_char_notify,
    get_char_request_read,
    get_char_request_write,
    parse_message,
)

_LOGGER = logging.getLogger(__name__)

# How often to re-poll Gen 1 fields (seconds)
_GEN1_POLL_INTERVAL = 60


class SpecializedTurboCoordinator(ActiveBluetoothDataUpdateCoordinator[None]):
    """Manages the BLE connection and notification subscription for one bike."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        *,
        address: str,
        pin: int | None = None,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass=hass,
            logger=logger,
            address=address,
            needs_poll_method=self._needs_poll,
            poll_method=self._do_poll,
            mode=bluetooth.BluetoothScanningMode.ACTIVE,
            connectable=True,
        )
        self._address = address
        self._pin = pin
        self.snapshot = TelemetrySnapshot()
        self._client: BleakClient | None = None
        self._was_unavailable = False
        self._generation: ProtocolGeneration | None = None
        self._char_request_write: str | None = None
        self._char_request_read: str | None = None
        self._last_poll_time: float = 0

    @callback
    def _needs_poll(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        seconds_since_last_update: float | None,
    ) -> bool:
        """True if we need to (re)connect or re-poll Gen 1 fields."""
        # Detect generation early from advertisement data
        if self._generation is None:
            gen = detect_generation(service_info.manufacturer_data)
            if gen is not None:
                self._generation = gen
        if self._client is None or not self._client.is_connected:
            return True
        # Gen 1: periodically re-poll request-read fields
        if self._generation == ProtocolGeneration.GEN_1:
            return (time.monotonic() - self._last_poll_time) >= _GEN1_POLL_INTERVAL
        return False

    async def _do_poll(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak | None = None,
    ) -> None:
        """Connect to the bike and subscribe to notifications."""
        try:
            await self._ensure_connected()
        except BleakError as err:
            _LOGGER.debug("BLE connection unavailable for %s: %s", self._address, err)
            self._client = None
            return

        # Poll Gen 1 fields via request-read
        if (
            self._generation == ProtocolGeneration.GEN_1
            and self._client
            and self._client.is_connected
        ):
            await self._poll_gen1_fields()

    async def _ensure_connected(self) -> None:
        """Establish BLE connection and subscribe to notifications."""
        if self._client and self._client.is_connected:
            return

        _LOGGER.debug("Connecting to Specialized Turbo at %s", self._address)

        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self._address, connectable=True
        )

        if ble_device is None:
            if not self._was_unavailable:
                _LOGGER.info("Specialized Turbo at %s is unavailable", self._address)
                self._was_unavailable = True
            return

        client = await establish_connection(
            BleakClient,
            ble_device,
            self._address,
            disconnected_callback=self._on_disconnect,
        )
        self._client = client

        if self._was_unavailable:
            _LOGGER.info("Specialized Turbo at %s is available again", self._address)
            self._was_unavailable = False

        char_notify = (
            get_char_notify(self._generation)
            if self._generation is not None
            else CHAR_NOTIFY
        )

        # Resolve request-read UUIDs for Gen 1 polling
        if self._generation is not None:
            self._char_request_write = get_char_request_write(self._generation)
            self._char_request_read = get_char_request_read(self._generation)

        # Trigger pairing if PIN is provided
        if self._pin is not None:
            try:
                await client.pair(protection_level=2)
                _LOGGER.info("Paired with PIN")
            except NotImplementedError:
                _LOGGER.debug("Backend does not support programmatic pairing")
            except Exception:
                _LOGGER.warning("Pairing failed", exc_info=True)

        # Subscribe to telemetry notifications
        await client.start_notify(char_notify, self._notification_handler)
        _LOGGER.info("Subscribed to telemetry notifications")

    def _notification_handler(
        self, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Parse a BLE notification and push the update to HA."""
        try:
            msg = parse_message(data)
        except Exception:
            _LOGGER.debug("Failed to parse notification: %s", data.hex(), exc_info=True)
            return

        self.snapshot.update_from_message(msg)

        # Push the update to HA — this triggers entity state writes
        self.async_update_listeners()

        if msg.field_name:
            _LOGGER.debug("%s = %s %s", msg.field_name, msg.converted_value, msg.unit)

    async def _poll_gen1_fields(self) -> None:
        """Query all Gen 1 fields via the request-read GATT pattern."""
        if self._client is None or self._char_request_write is None:
            return

        updated = False
        for sender, channel in GEN1_POLL_FIELDS:
            try:
                await self._client.write_gatt_char(
                    self._char_request_write, build_request(sender, channel)
                )
                await asyncio.sleep(0.1)
                response = await self._client.read_gatt_char(
                    self._char_request_read
                )
                msg = parse_message(response)
                if msg.sender == sender and msg.channel == channel:
                    self.snapshot.update_from_message(msg)
                    updated = True
                    if msg.field_name:
                        _LOGGER.debug(
                            "poll %s = %s %s",
                            msg.field_name,
                            msg.converted_value,
                            msg.unit,
                        )
            except Exception:
                _LOGGER.debug(
                    "Failed to poll field (%02x, %02x)",
                    sender,
                    channel,
                    exc_info=True,
                )

        self._last_poll_time = time.monotonic()
        if updated:
            self.async_update_listeners()

    @property
    def connected(self) -> bool:
        """Return True if the BLE client is connected."""
        return self._client is not None and self._client.is_connected

    @callback
    def _on_disconnect(self, client: BleakClient) -> None:
        """Handle unexpected disconnection."""
        if not self._was_unavailable:
            _LOGGER.info("Disconnected from Specialized Turbo at %s", self._address)
            self._was_unavailable = True
        self._client = None
        # Notify listeners so entities mark themselves unavailable
        self.async_update_listeners()

    async def async_shutdown(self) -> None:
        """Clean up BLE connection on unload."""
        if self._client and self._client.is_connected:
            char_notify = (
                get_char_notify(self._generation)
                if self._generation is not None
                else CHAR_NOTIFY
            )
            try:
                await self._client.stop_notify(char_notify)
            except Exception:
                _LOGGER.debug("Error stopping notifications", exc_info=True)
            try:
                await self._client.disconnect()
            except Exception:
                _LOGGER.debug("Error disconnecting", exc_info=True)
        self._client = None
