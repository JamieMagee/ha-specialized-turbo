"""BLE coordinator for Specialized Turbo bikes.

Connects over BLE, subscribes to GATT notifications, parses incoming
telemetry, and pushes updates to HA entities.
"""

from __future__ import annotations

import logging

from bleak import BleakClient

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.active_update_coordinator import (
    ActiveBluetoothDataUpdateCoordinator,
)
from homeassistant.core import HomeAssistant, callback

from specialized_turbo import (
    CHAR_NOTIFY,
    TelemetrySnapshot,
    parse_message,
)

_LOGGER = logging.getLogger(__name__)


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
            poll_method=self._async_poll,
            mode=bluetooth.BluetoothScanningMode.ACTIVE,
            connectable=True,
        )
        self._address = address
        self._pin = pin
        self.snapshot = TelemetrySnapshot()
        self._client: BleakClient | None = None

    @callback
    def _needs_poll(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        seconds_since_last_update: float | None,
    ) -> bool:
        """True if we haven't received any data yet (need to connect)."""
        return self.snapshot.message_count == 0

    async def _async_poll(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak | None = None,
    ) -> None:
        """Connect to the bike and subscribe to notifications."""
        await self._ensure_connected()

    async def _ensure_connected(self) -> None:
        """Establish BLE connection and subscribe to notifications."""
        if self._client and self._client.is_connected:
            return

        _LOGGER.info("Connecting to Specialized Turbo at %s", self._address)

        ble_device = await bluetooth.async_ble_device_from_address(
            self.hass, self._address, connectable=True
        )

        if ble_device is None:
            _LOGGER.warning("Could not find BLE device at %s", self._address)
            return

        client = BleakClient(
            ble_device,
            disconnected_callback=self._on_disconnect,
        )
        await client.connect()
        self._client = client

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
        await client.start_notify(CHAR_NOTIFY, self._notification_handler)
        _LOGGER.info("Subscribed to telemetry notifications")

    def _notification_handler(self, sender_handle: int, data: bytearray) -> None:
        """Parse a BLE notification and push the update to HA."""
        try:
            msg = parse_message(data)
        except Exception:
            _LOGGER.debug("Failed to parse notification: %s", data.hex(), exc_info=True)
            return

        self.snapshot.update_from_message(msg)

        # Push the update to HA — this triggers entity state writes
        self.async_set_updated_data(None)

        if msg.field_name:
            _LOGGER.debug("%s = %s %s", msg.field_name, msg.converted_value, msg.unit)

    @callback
    def _on_disconnect(self, client: BleakClient) -> None:
        """Handle unexpected disconnection."""
        _LOGGER.warning("Disconnected from Specialized Turbo at %s", self._address)
        self._client = None

    async def async_shutdown(self) -> None:
        """Clean up BLE connection on unload."""
        if self._client and self._client.is_connected:
            try:
                await self._client.stop_notify(CHAR_NOTIFY)
            except Exception:
                _LOGGER.debug("Error stopping notifications", exc_info=True)
            try:
                await self._client.disconnect()
            except Exception:
                _LOGGER.debug("Error disconnecting", exc_info=True)
        self._client = None
