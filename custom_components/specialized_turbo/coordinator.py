"""BLE coordinator for Specialized Turbo bikes."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import cast

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.active_update_coordinator import (
    ActiveBluetoothDataUpdateCoordinator,
)
from homeassistant.core import HomeAssistant, callback

from specialized_turbo import (
    BikeAdvertisement,
    BikeInfo,
    DecryptionError,
    EncryptionKeyProviderError,
    EncryptionKeyRequiredError,
    SpecializedConnection,
    TelemetryMonitor,
    TelemetrySnapshot,
    parse_bike_advertisement,
    parse_bike_info,
)

_LOGGER = logging.getLogger(__name__)

_POLL_INTERVAL = 60


class SpecializedTurboCoordinator(
    ActiveBluetoothDataUpdateCoordinator[TelemetrySnapshot]
):
    """Manage one Specialized Turbo bike through the upstream library."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        *,
        address: str,
        wrapped_key: str | None = None,
        advertisement: BikeAdvertisement | None = None,
        reauth_callback: Callable[[BikeAdvertisement], None] | None = None,
    ) -> None:
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
        self._wrapped_key = wrapped_key
        self._advertisement = advertisement
        self._bike_info: BikeInfo | None = None
        self._connection: SpecializedConnection | None = None
        self._monitor: TelemetryMonitor | None = None
        self._snapshot = TelemetrySnapshot()
        self._reauth_callback = reauth_callback
        self._reauth_requested = False
        self._was_unavailable = False
        self.data = self._snapshot

    @property
    def snapshot(self) -> TelemetrySnapshot:
        """Return the current telemetry snapshot."""
        return self._snapshot

    @callback
    def _needs_poll(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        seconds_since_last_poll: float | None,
    ) -> bool:
        """Return whether the bike needs a connection or periodic poll."""
        self._update_protocol_metadata(service_info)
        return (
            not self.connected
            or seconds_since_last_poll is None
            or seconds_since_last_poll >= _POLL_INTERVAL
        )

    async def _do_poll(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
    ) -> TelemetrySnapshot:
        """Connect if needed and poll the active protocol."""
        await self._ensure_connected(service_info)
        if self._monitor is not None:
            await self._monitor.poll()
        return self._snapshot

    async def _ensure_connected(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak | None = None,
    ) -> None:
        """Create the upstream connection and telemetry monitor."""
        if self.connected:
            return

        if service_info is not None:
            self._update_protocol_metadata(service_info)
            ble_device = service_info.device
        else:
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass,
                self._address,
                connectable=True,
            )

        if ble_device is None:
            if not self._was_unavailable:
                _LOGGER.info("Specialized Turbo at %s is unavailable", self._address)
                self._was_unavailable = True
            return

        async def client_factory(
            address_or_device: str | BLEDevice,
            disconnected_callback: Callable[[BleakClient], None] | None,
        ) -> BleakClient:
            return await establish_connection(
                BleakClient,
                cast(BLEDevice, address_or_device),
                self._address,
                disconnected_callback=disconnected_callback,
            )

        connection = SpecializedConnection(
            ble_device,
            advertisement=self._advertisement,
            bike_info=self._bike_info,
            wrapped_key=self._wrapped_key,
            discovery_timeout=0,
            disconnect_callback=self._on_disconnect,
            client_factory=client_factory,
        )
        try:
            await connection.connect()
        except (
            DecryptionError,
            EncryptionKeyProviderError,
            EncryptionKeyRequiredError,
        ):
            self._request_reauth()
            raise

        monitor = TelemetryMonitor(
            connection,
            notification_loop=self.hass.loop,
        )
        monitor.on_update = self._handle_monitor_update
        try:
            await monitor.start(prime=False)
        except Exception:
            await connection.disconnect()
            raise

        self._connection = connection
        self._monitor = monitor
        self._snapshot = monitor.snapshot
        self.data = self._snapshot

        if self._was_unavailable:
            _LOGGER.info("Specialized Turbo at %s is available again", self._address)
            self._was_unavailable = False

    def _update_protocol_metadata(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
    ) -> None:
        """Retain the most complete advertisement and bike metadata."""
        advertisement = parse_bike_advertisement(
            service_info.manufacturer_data,
            local_name=service_info.name,
            service_uuids=service_info.service_uuids,
        )
        current_has_hmi = (
            self._advertisement is not None
            and self._advertisement.hmi_hardware is not None
            and self._advertisement.hmi_serial is not None
        )
        new_has_hmi = (
            advertisement is not None
            and advertisement.hmi_hardware is not None
            and advertisement.hmi_serial is not None
        )
        if advertisement is not None and (new_has_hmi or not current_has_hmi):
            self._advertisement = advertisement

        bike_info = parse_bike_info(
            service_info.name or "",
            service_info.manufacturer_data,
        )
        if bike_info.complete or self._bike_info is None:
            self._bike_info = bike_info

    def _request_reauth(self) -> None:
        if (
            self._reauth_requested
            or self._reauth_callback is None
            or self._advertisement is None
        ):
            return
        self._reauth_requested = True
        self._reauth_callback(self._advertisement)

    def _handle_monitor_update(
        self,
        _message: object,
        snapshot: TelemetrySnapshot,
    ) -> None:
        """Publish an upstream notification update to Home Assistant."""
        self._snapshot = snapshot
        self.data = snapshot
        self.async_update_listeners()

    @property
    def connected(self) -> bool:
        """Return whether the upstream BLE connection is active."""
        return self._connection is not None and self._connection.is_connected

    def _on_disconnect(self, _client: BleakClient) -> None:
        """Schedule disconnect handling on the Home Assistant event loop."""
        self.hass.loop.call_soon_threadsafe(self._handle_disconnect)

    @callback
    def _handle_disconnect(self) -> None:
        """Clear connection state and publish unavailability."""
        if not self._was_unavailable:
            _LOGGER.info("Disconnected from Specialized Turbo at %s", self._address)
            self._was_unavailable = True
        self._connection = None
        self._monitor = None
        self.async_update_listeners()

    async def async_shutdown(self) -> None:
        """Stop monitoring and close the upstream connection."""
        monitor = self._monitor
        connection = self._connection
        self._monitor = None
        self._connection = None
        if monitor is not None:
            try:
                await monitor.stop()
            except Exception:
                _LOGGER.debug("Error stopping telemetry monitor", exc_info=True)
        if connection is not None:
            try:
                await connection.disconnect()
            except Exception:
                _LOGGER.debug("Error disconnecting", exc_info=True)
