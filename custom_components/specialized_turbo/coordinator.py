"""BLE coordinator for Specialized Turbo bikes."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

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
    TCU1_POLL_FIELDS,
    TCX_POLL_PARAMS,
    BikeAdvertisement,
    BikeEncryptionKey,
    BikeInfo,
    BLEProfile,
    EncryptionKeyRequiredError,
    IdentificationError,
    ProtocolRevision,
    ProtocolEncryptionMethod,
    StaticKeyProvider,
    TCXIdentification,
    TCXNotificationTransport,
    TelemetrySnapshot,
    build_request,
    get_char_notify,
    get_char_request_read,
    get_char_request_write,
    identify_tcx,
    parse_bike_advertisement,
    parse_bike_info,
    parse_message,
    parse_tcx_notification,
    parse_tcx_message,
    poll_tcx,
    resolve_bike_key,
)
from specialized_turbo.session import ProtocolSession, TCU1Session, TCXSession

_LOGGER = logging.getLogger(__name__)

_TCU1_POLL_INTERVAL = 60


class SpecializedTurboCoordinator(ActiveBluetoothDataUpdateCoordinator[None]):
    """Manage the BLE connection and notifications for one bike."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        *,
        address: str,
        pin: str | None = None,
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
        self._pin = pin
        self._wrapped_key = wrapped_key
        self._advertisement = advertisement
        self._reauth_callback = reauth_callback
        self._reauth_requested = False
        self.snapshot = TelemetrySnapshot()
        self._client: BleakClient | None = None
        self._was_unavailable = False
        self._generation: BLEProfile | None = None
        self._bike_info: BikeInfo | None = None
        self._protocol_revision: ProtocolRevision | None = None
        self._session: ProtocolSession = TCU1Session()
        self._tcx_transport: TCXNotificationTransport | None = None
        self._char_request_write: str | None = None
        self._char_request_read: str | None = None
        self._last_poll_time: float = 0
        self._uses_tcx_messages: bool | None = None

    @callback
    def _needs_poll(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        seconds_since_last_update: float | None,
    ) -> bool:
        """Return whether the coordinator needs to connect or poll."""
        del seconds_since_last_update
        self._update_protocol_metadata(service_info)
        if self._client is None or not self._client.is_connected:
            return True
        if self._last_poll_time == 0:
            return False
        return (time.monotonic() - self._last_poll_time) >= _TCU1_POLL_INTERVAL

    async def _do_poll(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak | None = None,
    ) -> None:
        """Connect to the bike and poll fields that are not pushed."""
        try:
            await self._ensure_connected(service_info)
        except BleakError:
            self._client = None
            raise

        if self._client and self._client.is_connected:
            if self._uses_tcx_messages is True:
                await self._poll_tcx_fields()
            else:
                await self._poll_tcu1_fields()

    async def _ensure_connected(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak | None = None,
    ) -> None:
        """Establish the BLE connection and notification subscriptions."""
        if self._client and self._client.is_connected:
            return

        _LOGGER.debug("Connecting to Specialized Turbo at %s", self._address)

        if service_info is not None:
            self._update_protocol_metadata(service_info)

        bike_key = await self._resolve_bike_key()

        ble_device = (
            service_info.device
            if service_info is not None
            else bluetooth.async_ble_device_from_address(
                self.hass, self._address, connectable=True
            )
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

        if self._generation is not None:
            self._char_request_write = get_char_request_write(self._generation)
            self._char_request_read = get_char_request_read(self._generation)

        if self._generation == BLEProfile.TCX:
            self._session = TCXSession()
        else:
            self._session = TCU1Session()

        if self._pin is not None:
            try:
                await client.pair(protection_level=2)
                _LOGGER.info("Paired with bike")
            except NotImplementedError:
                _LOGGER.debug("Backend does not support programmatic pairing")
            except Exception:
                _LOGGER.warning("Pairing failed", exc_info=True)

        if self._generation == BLEProfile.TCX:
            transport = TCXNotificationTransport(client, session=TCXSession())
            self._tcx_transport = transport
            encryption_required = (
                self._advertisement is not None
                and self._advertisement.encryption == ProtocolEncryptionMethod.AES_CTR
            )
            if encryption_required:
                if (
                    self._bike_info is None
                    or not self._bike_info.complete
                    or self._bike_info.tcx_generation is None
                    or bike_key is None
                ):
                    self._request_reauth()
                    raise EncryptionKeyRequiredError(
                        "Encrypted bike is missing protocol or key metadata"
                    )
                identification = TCXIdentification(
                    transport,
                    self._bike_info,
                    BikeEncryptionKey(raw=bike_key),
                )
                try:
                    result = await identification.run()
                except IdentificationError as exc:
                    self._request_reauth()
                    raise EncryptionKeyRequiredError(
                        "Encrypted bike identification failed"
                    ) from exc
                self._session = transport.session
                self._protocol_revision = result.protocol_revision
            else:
                await transport.subscribe_for_identification()
                self._session = await identify_tcx(transport)
                transport.session = self._session
            transport.add_listener(self._notification_handler)
            await transport.subscribe_for_realtime()
            if self._protocol_revision is not None:
                await transport.set_realtime_enabled(True)
            self._uses_tcx_messages = True
        else:
            char_notify = (
                get_char_notify(self._generation)
                if self._generation is not None
                else CHAR_NOTIFY
            )
            await client.start_notify(char_notify, self._notification_handler)
        _LOGGER.info("Subscribed to telemetry notifications")

    def _update_protocol_metadata(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
    ) -> None:
        """Update protocol metadata from the latest advertisement."""
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
            self._generation = advertisement.generation

        bike_info = parse_bike_info(
            service_info.name or "",
            service_info.manufacturer_data,
        )
        if bike_info.complete:
            self._bike_info = bike_info
            if bike_info.ble_profile is not None:
                self._generation = bike_info.ble_profile

    async def _resolve_bike_key(self) -> bytes | None:
        advertisement = self._advertisement
        if (
            advertisement is None
            or advertisement.encryption != ProtocolEncryptionMethod.AES_CTR
        ):
            return None
        if (
            self._wrapped_key is None
            or advertisement.hmi_hardware is None
            or advertisement.hmi_serial is None
        ):
            self._request_reauth()
            raise EncryptionKeyRequiredError(
                "Encrypted bike requires a wrapped key and HMI identifiers"
            )
        try:
            return await resolve_bike_key(
                StaticKeyProvider(self._wrapped_key),
                hmi_hardware=advertisement.hmi_hardware,
                hmi_serial=advertisement.hmi_serial,
            )
        except Exception:
            self._request_reauth()
            raise

    def _request_reauth(self) -> None:
        if (
            self._reauth_requested
            or self._reauth_callback is None
            or self._advertisement is None
        ):
            return
        self._reauth_requested = True
        self._reauth_callback(self._advertisement)

    def _notification_handler(
        self,
        sender: BleakGATTCharacteristic | int,
        data: bytearray,
    ) -> None:
        """Forward a BLE notification to the Home Assistant event loop."""
        del sender
        self.hass.loop.call_soon_threadsafe(self._handle_notification, bytes(data))

    @callback
    def _handle_notification(self, data: bytes) -> None:
        """Parse a notification and update the snapshot."""
        _LOGGER.debug(
            "notify raw (%d bytes, gen=%s, session=%s): %s",
            len(data),
            self._generation,
            type(self._session).__name__,
            data.hex(),
        )

        framed = self._generation == BLEProfile.TCX
        if self._uses_tcx_messages is None:
            self._uses_tcx_messages = framed
            _LOGGER.info(
                "Auto-detected message format: %s",
                "TCX" if framed else "TCU1",
            )

        try:
            if framed:
                if (
                    isinstance(self._session, TCXSession)
                    and self._protocol_revision is not None
                ):
                    msg = parse_tcx_notification(
                        self._session,
                        data,
                        self._protocol_revision,
                    )
                else:
                    unpacked = self._session.unpack(data)
                    msg = parse_tcx_message(unpacked)
            else:
                msg = parse_message(data)
        except Exception:
            _LOGGER.debug("Failed to parse notification: %s", data.hex(), exc_info=True)
            return

        self.snapshot.update_from_message(msg)
        self.async_update_listeners()

    async def _poll_tcu1_fields(self) -> None:
        """Query TCU1 fields with the request-read GATT pattern."""
        if self._client is None or self._char_request_write is None:
            return

        updated = False
        for sender, channel in TCU1_POLL_FIELDS:
            try:
                await self._client.write_gatt_char(
                    self._char_request_write, build_request(sender, channel)
                )
                await asyncio.sleep(0.1)
                response = await self._client.read_gatt_char(self._char_request_read)
                msg = parse_message(response)
                if msg.sender == sender and msg.channel == channel:
                    self.snapshot.update_from_message(msg)
                    updated = True
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

    async def _poll_tcx_fields(self) -> None:
        """Query TCX fields through the upstream notification transport."""
        if self._tcx_transport is None:
            return

        if self._protocol_revision is not None:
            updated = await poll_tcx(
                self._tcx_transport,
                self.snapshot,
                self._protocol_revision,
            )
        else:
            updated = await self._poll_legacy_tcx_fields()
        self._last_poll_time = time.monotonic()
        if updated:
            self.async_update_listeners()

    async def _poll_legacy_tcx_fields(self) -> bool:
        """Poll legacy TCX sessions that have no negotiated wire profile."""
        if self._tcx_transport is None:
            return False

        updated = False
        for param in TCX_POLL_PARAMS:
            try:
                response = await self._tcx_transport.request_parameter(int(param))
                msg = parse_tcx_message(response)
                if msg.nak_reason is None:
                    self.snapshot.update_from_message(msg)
                    updated = True
            except Exception:
                _LOGGER.debug(
                    "Failed to poll legacy TCX param %d",
                    int(param),
                    exc_info=True,
                )
        return updated

    @property
    def connected(self) -> bool:
        """Return whether the BLE client is connected."""
        return self._client is not None and self._client.is_connected

    def _on_disconnect(self, client: BleakClient) -> None:
        """Handle an unexpected BLE disconnection."""
        del client
        self.hass.loop.call_soon_threadsafe(self._handle_disconnect)

    @callback
    def _handle_disconnect(self) -> None:
        """Process disconnection on the Home Assistant event loop."""
        if not self._was_unavailable:
            _LOGGER.info("Disconnected from Specialized Turbo at %s", self._address)
            self._was_unavailable = True
        self._client = None
        self._tcx_transport = None
        self._protocol_revision = None
        self.async_update_listeners()

    async def async_shutdown(self) -> None:
        """Clean up the BLE connection."""
        if self._client and self._client.is_connected:
            if self._tcx_transport is not None:
                if self._protocol_revision is not None:
                    try:
                        await self._tcx_transport.set_realtime_enabled(False)
                    except Exception:
                        _LOGGER.debug(
                            "Error disabling real-time data",
                            exc_info=True,
                        )
                try:
                    await self._tcx_transport.unsubscribe_all()
                except Exception:
                    _LOGGER.debug("Error stopping notifications", exc_info=True)
            else:
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
        self._tcx_transport = None
        self._protocol_revision = None
