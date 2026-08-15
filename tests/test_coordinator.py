"""Tests for Specialized Turbo coordinator."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bleak import BleakError

from homeassistant.core import HomeAssistant

from custom_components.specialized_turbo.coordinator import (
    SpecializedTurboCoordinator,
)
from specialized_turbo import (
    CHAR_NOTIFY,
    CHAR_NOTIFY_TCU1,
    BikeAdvertisement,
    BikeEncryptionKey,
    BLEProfile,
    EncryptionKeyRequiredError,
    ProtocolRevision,
    ProtocolEncryptionMethod,
    TCXGeneration,
)
from specialized_turbo.session import TCXSession

from .conftest import (
    MOCK_ADDRESS,
    MOCK_ENCRYPTED_MANUFACTURER_DATA,
    MOCK_GEN1_MANUFACTURER_DATA,
    make_service_info,
    make_wrapped_key,
)

_LOGGER = logging.getLogger(__name__)


def _make_coordinator(
    hass: HomeAssistant,
    pin: str | None = None,
    *,
    wrapped_key: str | None = None,
    advertisement: BikeAdvertisement | None = None,
    reauth_callback: MagicMock | None = None,
) -> SpecializedTurboCoordinator:
    """Create a coordinator with mocked parent class."""
    with patch(
        "custom_components.specialized_turbo.coordinator.ActiveBluetoothDataUpdateCoordinator.__init__",
        return_value=None,
    ):
        coord = SpecializedTurboCoordinator(
            hass,
            _LOGGER,
            address=MOCK_ADDRESS,
            pin=pin,
            wrapped_key=wrapped_key,
            advertisement=advertisement,
            reauth_callback=reauth_callback,
        )
    coord.hass = hass
    coord.async_update_listeners = MagicMock()
    return coord


# --- needs_poll ---


async def test_needs_poll_no_client(hass: HomeAssistant) -> None:
    """Test needs_poll returns True when no client exists."""
    coord = _make_coordinator(hass)
    assert coord._needs_poll(MagicMock(), None) is True


async def test_needs_poll_connected(hass: HomeAssistant) -> None:
    """Test needs_poll returns False when client is connected."""
    coord = _make_coordinator(hass)
    mock_client = MagicMock()
    mock_client.is_connected = True
    coord._client = mock_client
    assert coord._needs_poll(MagicMock(), None) is False


async def test_needs_poll_disconnected_client(hass: HomeAssistant) -> None:
    """Test needs_poll returns True when client exists but is disconnected."""
    coord = _make_coordinator(hass)
    mock_client = MagicMock()
    mock_client.is_connected = False
    coord._client = mock_client
    assert coord._needs_poll(MagicMock(), None) is True


async def test_needs_poll_after_disconnect_reconnect(hass: HomeAssistant) -> None:
    """Test needs_poll triggers reconnection after bike leaves and returns."""
    coord = _make_coordinator(hass)

    # Simulate first connection with data received
    mock_client = MagicMock()
    mock_client.is_connected = True
    coord._client = mock_client
    coord.snapshot.message_count = 100
    assert coord._needs_poll(MagicMock(), None) is False

    # Simulate bike leaving (disconnect callback fires)
    coord._handle_disconnect()
    assert coord._client is None

    # Bike comes back in range — needs_poll must return True to reconnect
    assert coord._needs_poll(MagicMock(), None) is True


async def test_encrypted_bike_without_key_requests_reauth(
    hass: HomeAssistant,
) -> None:
    """Test explicit failure and reauth for missing encrypted-bike key."""
    advertisement = BikeAdvertisement(
        generation=BLEProfile.TCX,
        encryption=ProtocolEncryptionMethod.AES_CTR,
        hmi_hardware="3.2.1",
        hmi_serial="123456789",
    )
    reauth = MagicMock()
    coord = _make_coordinator(
        hass,
        advertisement=advertisement,
        reauth_callback=reauth,
    )

    with pytest.raises(EncryptionKeyRequiredError):
        await coord._resolve_bike_key()

    reauth.assert_called_once_with(advertisement)


async def test_encrypted_bike_resolves_stored_wrapped_key(
    hass: HomeAssistant,
) -> None:
    """Test stored wrapped key is converted to the 16-byte bike key."""
    coord = _make_coordinator(
        hass,
        wrapped_key=make_wrapped_key(),
        advertisement=BikeAdvertisement(
            generation=BLEProfile.TCX,
            encryption=ProtocolEncryptionMethod.AES_CTR,
            hmi_hardware="3.2.1",
            hmi_serial="123456789",
        ),
    )

    assert await coord._resolve_bike_key() == bytes.fromhex(
        "00112233445566778899aabbccddeeff"
    )


async def test_needs_poll_decodes_tcx_wire_profile(hass: HomeAssistant) -> None:
    """Test a modern advertisement selects its TCX generation."""
    coord = _make_coordinator(hass)
    service_info = make_service_info(
        name="WSBC001057439S",
        manufacturer_data=MOCK_ENCRYPTED_MANUFACTURER_DATA,
    )

    coord._needs_poll(service_info, None)

    assert coord._bike_info is not None
    assert coord._bike_info.hmi_hardware_version == "B.3.3"
    assert coord._bike_info.tcx_generation is TCXGeneration.TCX2


async def test_partial_advertisement_does_not_drop_encryption_metadata(
    hass: HomeAssistant,
) -> None:
    """Test split Apple frames cannot replace known encrypted-bike metadata."""
    encrypted = BikeAdvertisement(
        generation=BLEProfile.TCX,
        encryption=ProtocolEncryptionMethod.AES_CTR,
        hmi_hardware="B.3.3",
        hmi_serial="80005338",
    )
    coord = _make_coordinator(hass, advertisement=encrypted)
    service_info = make_service_info(
        name="WSBC001057439S",
        manufacturer_data={
            0x004C: bytes.fromhex("0215545552424f484d4932303137010000005fe033060a")
        },
    )
    service_info.service_uuids = []

    coord._needs_poll(service_info, None)

    assert coord._advertisement == encrypted


async def test_ensure_connected_uses_profile_aware_identification(
    hass: HomeAssistant,
) -> None:
    """Test encrypted bikes use the mapped TCX identification state machine."""
    coord = _make_coordinator(
        hass,
        wrapped_key=make_wrapped_key(),
    )
    service_info = make_service_info(
        name="WSBC001057439S",
        manufacturer_data=MOCK_ENCRYPTED_MANUFACTURER_DATA,
    )
    service_info.device = MagicMock()
    client = AsyncMock()
    client.is_connected = True
    transport = MagicMock()
    transport.session = TCXSession()
    transport.subscribe_for_realtime = AsyncMock()
    transport.set_realtime_enabled = AsyncMock()
    revision = ProtocolRevision(TCXGeneration.TCX2, 0x12)
    identification = MagicMock()
    identification.run = AsyncMock(
        return_value=SimpleNamespace(protocol_revision=revision)
    )

    with (
        patch(
            "custom_components.specialized_turbo.coordinator.establish_connection",
            new_callable=AsyncMock,
            return_value=client,
        ),
        patch(
            "custom_components.specialized_turbo.coordinator.TCXNotificationTransport",
            return_value=transport,
        ),
        patch(
            "custom_components.specialized_turbo.coordinator.TCXIdentification",
            return_value=identification,
        ) as identification_type,
    ):
        await coord._ensure_connected(service_info)

    key = identification_type.call_args.args[2]
    assert isinstance(key, BikeEncryptionKey)
    assert key.raw == bytes.fromhex("00112233445566778899aabbccddeeff")
    assert coord._protocol_revision == revision
    identification.run.assert_awaited_once()
    transport.set_realtime_enabled.assert_awaited_once_with(True)


# --- async_poll ---


async def test_async_poll(hass: HomeAssistant) -> None:
    """Test that polling calls _ensure_connected."""
    coord = _make_coordinator(hass)

    with patch.object(coord, "_ensure_connected", new_callable=AsyncMock) as mock:
        await coord._do_poll()
        mock.assert_called_once()


# --- notification_handler ---


async def test_notification_handler_valid(hass: HomeAssistant) -> None:
    """Test notification handler parses valid data and updates snapshot."""
    coord = _make_coordinator(hass)

    # Battery charge percent: sender=0x00, channel=0x0C, value=85 (0x55)
    data = bytearray([0x00, 0x0C, 0x55])
    coord._handle_notification(bytes(data))

    assert coord.snapshot.battery.charge_pct == 85
    assert coord.snapshot.message_count == 1
    coord.async_update_listeners.assert_called_once()


async def test_empty_notification_is_ignored(hass: HomeAssistant) -> None:
    """Test proxy subscription events do not produce parse errors or updates."""
    coord = _make_coordinator(hass)

    coord._handle_notification(b"")

    assert coord.snapshot.message_count == 0
    coord.async_update_listeners.assert_not_called()


async def test_notification_handler_speed(hass: HomeAssistant) -> None:
    """Test notification handler with speed value."""
    coord = _make_coordinator(hass)

    # Speed: sender=0x01, channel=0x02, value=255 (25.5 km/h) as 2 bytes LE
    data = bytearray([0x01, 0x02, 0xFF, 0x00])
    coord._handle_notification(bytes(data))

    assert coord.snapshot.motor.speed_kmh == 25.5
    assert coord.snapshot.message_count == 1


async def test_notification_handler_parse_error(hass: HomeAssistant) -> None:
    """Test notification handler handles parse errors gracefully."""
    coord = _make_coordinator(hass)

    # Too short to parse (< 3 bytes)
    data = bytearray([0x00])
    coord._handle_notification(bytes(data))

    assert coord.snapshot.message_count == 0
    coord.async_update_listeners.assert_not_called()


async def test_notification_handler_unknown_field(hass: HomeAssistant) -> None:
    """Test notification handler handles unknown fields."""
    coord = _make_coordinator(hass)

    # Unknown sender 0x03
    data = bytearray([0x03, 0x00, 0x42])
    coord._handle_notification(bytes(data))

    assert coord.snapshot.message_count == 1
    coord.async_update_listeners.assert_called_once()


# --- ensure_connected ---


async def test_ensure_connected_already_connected(hass: HomeAssistant) -> None:
    """Test ensure_connected returns early if already connected."""
    coord = _make_coordinator(hass)

    mock_client = MagicMock()
    mock_client.is_connected = True
    coord._client = mock_client

    await coord._ensure_connected()

    assert coord._client is mock_client


async def test_ensure_connected_device_not_found(hass: HomeAssistant) -> None:
    """Test ensure_connected sets unavailable when device not found."""
    coord = _make_coordinator(hass)

    with patch(
        "custom_components.specialized_turbo.coordinator.bluetooth.async_ble_device_from_address",
        return_value=None,
    ):
        await coord._ensure_connected()

    assert coord._was_unavailable is True
    assert coord._client is None


async def test_ensure_connected_device_not_found_no_repeat_log(
    hass: HomeAssistant,
) -> None:
    """Test that unavailable message is only logged once."""
    coord = _make_coordinator(hass)
    coord._was_unavailable = True

    with patch(
        "custom_components.specialized_turbo.coordinator.bluetooth.async_ble_device_from_address",
        return_value=None,
    ):
        await coord._ensure_connected()

    assert coord._was_unavailable is True


async def test_ensure_connected_success(hass: HomeAssistant) -> None:
    """Test ensure_connected connects and subscribes to notifications."""
    coord = _make_coordinator(hass)

    mock_client = AsyncMock()
    mock_client.is_connected = True

    with (
        patch(
            "custom_components.specialized_turbo.coordinator.bluetooth.async_ble_device_from_address",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.specialized_turbo.coordinator.establish_connection",
            new_callable=AsyncMock,
            return_value=mock_client,
        ),
    ):
        await coord._ensure_connected()

    assert coord._client is mock_client
    mock_client.start_notify.assert_called_once_with(
        CHAR_NOTIFY, coord._notification_handler
    )


async def test_ensure_connected_reconnect_after_unavailable(
    hass: HomeAssistant,
) -> None:
    """Test that reconnection after unavailable clears the flag."""
    coord = _make_coordinator(hass)
    coord._was_unavailable = True

    mock_client = AsyncMock()

    with (
        patch(
            "custom_components.specialized_turbo.coordinator.bluetooth.async_ble_device_from_address",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.specialized_turbo.coordinator.establish_connection",
            new_callable=AsyncMock,
            return_value=mock_client,
        ),
    ):
        await coord._ensure_connected()

    assert coord._was_unavailable is False
    assert coord._client is mock_client


async def test_ensure_connected_with_pin(hass: HomeAssistant) -> None:
    """Test ensure_connected triggers pairing when PIN is set."""
    coord = _make_coordinator(hass, pin="1234")

    mock_client = AsyncMock()

    with (
        patch(
            "custom_components.specialized_turbo.coordinator.bluetooth.async_ble_device_from_address",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.specialized_turbo.coordinator.establish_connection",
            new_callable=AsyncMock,
            return_value=mock_client,
        ),
    ):
        await coord._ensure_connected()

    mock_client.pair.assert_called_once_with(protection_level=2)


async def test_ensure_connected_pairing_not_implemented(
    hass: HomeAssistant,
) -> None:
    """Test pairing gracefully handles NotImplementedError."""
    coord = _make_coordinator(hass, pin="1234")

    mock_client = AsyncMock()
    mock_client.pair.side_effect = NotImplementedError

    with (
        patch(
            "custom_components.specialized_turbo.coordinator.bluetooth.async_ble_device_from_address",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.specialized_turbo.coordinator.establish_connection",
            new_callable=AsyncMock,
            return_value=mock_client,
        ),
    ):
        await coord._ensure_connected()

    mock_client.start_notify.assert_called_once()


async def test_ensure_connected_pairing_error(hass: HomeAssistant) -> None:
    """Test pairing gracefully handles generic errors."""
    coord = _make_coordinator(hass, pin="1234")

    mock_client = AsyncMock()
    mock_client.pair.side_effect = RuntimeError("Pair failed")

    with (
        patch(
            "custom_components.specialized_turbo.coordinator.bluetooth.async_ble_device_from_address",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.specialized_turbo.coordinator.establish_connection",
            new_callable=AsyncMock,
            return_value=mock_client,
        ),
    ):
        await coord._ensure_connected()

    mock_client.start_notify.assert_called_once()


# --- connected property ---


async def test_connected_no_client(hass: HomeAssistant) -> None:
    """Test connected is False when no client exists."""
    coord = _make_coordinator(hass)
    assert coord.connected is False


async def test_connected_when_connected(hass: HomeAssistant) -> None:
    """Test connected is True when client is connected."""
    coord = _make_coordinator(hass)
    mock_client = MagicMock()
    mock_client.is_connected = True
    coord._client = mock_client
    assert coord.connected is True


async def test_connected_when_disconnected(hass: HomeAssistant) -> None:
    """Test connected is False when client exists but is disconnected."""
    coord = _make_coordinator(hass)
    mock_client = MagicMock()
    mock_client.is_connected = False
    coord._client = mock_client
    assert coord.connected is False


# --- on_disconnect ---


async def test_on_disconnect(hass: HomeAssistant) -> None:
    """Test disconnect callback sets unavailable flag and notifies listeners."""
    coord = _make_coordinator(hass)
    coord._client = MagicMock()

    coord._handle_disconnect()

    assert coord._was_unavailable is True
    assert coord._client is None
    coord.async_update_listeners.assert_called_once()


async def test_on_disconnect_already_unavailable(hass: HomeAssistant) -> None:
    """Test disconnect when already unavailable doesn't re-log."""
    coord = _make_coordinator(hass)
    coord._was_unavailable = True
    coord._client = MagicMock()

    coord._handle_disconnect()

    assert coord._was_unavailable is True
    assert coord._client is None
    coord.async_update_listeners.assert_called_once()


# --- async_shutdown ---


async def test_async_shutdown_connected(hass: HomeAssistant) -> None:
    """Test shutdown cleanly disconnects a connected client."""
    coord = _make_coordinator(hass)
    mock_client = AsyncMock()
    mock_client.is_connected = True
    coord._client = mock_client

    await coord.async_shutdown()

    mock_client.stop_notify.assert_called_once_with(CHAR_NOTIFY)
    mock_client.disconnect.assert_called_once()
    assert coord._client is None


async def test_async_shutdown_not_connected(hass: HomeAssistant) -> None:
    """Test shutdown with no active connection."""
    coord = _make_coordinator(hass)

    await coord.async_shutdown()

    assert coord._client is None


async def test_async_shutdown_errors(hass: HomeAssistant) -> None:
    """Test shutdown handles errors during cleanup."""
    coord = _make_coordinator(hass)
    mock_client = AsyncMock()
    mock_client.is_connected = True
    mock_client.stop_notify.side_effect = Exception("stop error")
    mock_client.disconnect.side_effect = Exception("disconnect error")
    coord._client = mock_client

    await coord.async_shutdown()

    assert coord._client is None


# --- BleakError handling in _do_poll ---


async def test_do_poll_bleak_error_from_start_notify(hass: HomeAssistant) -> None:
    """Test that BleakError during start_notify propagates and client is cleared."""
    coord = _make_coordinator(hass)

    mock_client = AsyncMock()
    mock_client.is_connected = True
    mock_client.start_notify.side_effect = BleakError("Not connected")

    with (
        patch(
            "custom_components.specialized_turbo.coordinator.bluetooth.async_ble_device_from_address",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.specialized_turbo.coordinator.establish_connection",
            new_callable=AsyncMock,
            return_value=mock_client,
        ),
        pytest.raises(BleakError),
    ):
        await coord._do_poll()

    assert coord._client is None


async def test_do_poll_bleak_error_from_establish_connection(
    hass: HomeAssistant,
) -> None:
    """Test that BleakError during establish_connection propagates."""
    coord = _make_coordinator(hass)

    with (
        patch(
            "custom_components.specialized_turbo.coordinator.bluetooth.async_ble_device_from_address",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.specialized_turbo.coordinator.establish_connection",
            new_callable=AsyncMock,
            side_effect=BleakError("Failed to connect"),
        ),
        pytest.raises(BleakError),
    ):
        await coord._do_poll()

    assert coord._client is None


# --- TCU1 support ---


async def test_needs_poll_detects_tcu1(hass: HomeAssistant) -> None:
    """Test _needs_poll detects TCU1 protocol from manufacturer data."""
    coord = _make_coordinator(hass)
    service_info = MagicMock()
    service_info.manufacturer_data = MOCK_GEN1_MANUFACTURER_DATA
    coord._needs_poll(service_info, None)
    assert coord._generation == BLEProfile.TCU1


async def test_ensure_connected_tcu1_uses_tcu1_char_notify(
    hass: HomeAssistant,
) -> None:
    """Test ensure_connected subscribes to TCU1 CHAR_NOTIFY UUID."""
    coord = _make_coordinator(hass)
    coord._generation = BLEProfile.TCU1

    mock_client = AsyncMock()
    mock_client.is_connected = True

    with (
        patch(
            "custom_components.specialized_turbo.coordinator.bluetooth.async_ble_device_from_address",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.specialized_turbo.coordinator.establish_connection",
            new_callable=AsyncMock,
            return_value=mock_client,
        ),
    ):
        await coord._ensure_connected()

    mock_client.start_notify.assert_called_once_with(
        CHAR_NOTIFY_TCU1, coord._notification_handler
    )


async def test_ensure_connected_detects_tcu1_from_gatt_services(
    hass: HomeAssistant,
) -> None:
    """Test a missing advertisement cannot make a Gen1 bike use TCX UUIDs."""
    coord = _make_coordinator(hass)
    mock_client = AsyncMock()
    mock_client.is_connected = True
    mock_client.services = MagicMock()
    mock_client.services.get_characteristic.side_effect = lambda uuid: (
        MagicMock() if uuid == CHAR_NOTIFY_TCU1 else None
    )

    with (
        patch(
            "custom_components.specialized_turbo.coordinator.bluetooth.async_ble_device_from_address",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.specialized_turbo.coordinator.establish_connection",
            new_callable=AsyncMock,
            return_value=mock_client,
        ),
    ):
        await coord._ensure_connected()

    assert coord._generation is BLEProfile.TCU1
    mock_client.start_notify.assert_awaited_once_with(
        CHAR_NOTIFY_TCU1,
        coord._notification_handler,
    )


async def test_tcu1_notification_with_ff_padding(hass: HomeAssistant) -> None:
    """Test TCU1 notifications with FF padding parse correctly."""
    coord = _make_coordinator(hass)
    coord._generation = BLEProfile.TCU1

    # 01 05 01 00 FF FF... → assist_level ECO, padded with FF
    data = bytearray.fromhex("01050100" + "ff" * 16)
    coord._handle_notification(bytes(data))

    from specialized_turbo import AssistLevel

    assert coord.snapshot.motor.assist_level == AssistLevel.ECO
    assert coord.snapshot.message_count == 1


# --- TCX support ---


async def test_tcx_notification_with_f8ff_is_nak(hass: HomeAssistant) -> None:
    """F8 FF notifications are NAK rejections, not telemetry envelopes.

    The bytes after F8 FF echo the requested parameter ID and a rejection
    reason code.  Before specialized-turbo v0.5.0 the coordinator stripped
    the prefix and parsed the reason byte as data (e.g. SoC=5%).  Now it
    should be recognised as a NAK and skipped — no state update.
    """
    coord = _make_coordinator(hass)
    coord._generation = BLEProfile.TCX

    # f8ff 016b 05 00... + CRC.  Looks like SYSTEM_STATE (363) = 5 if you
    # blindly strip the f8ff, but it's actually a rejection of param 363
    # with reason code 0x05.
    data = bytes.fromhex("f8ff016b050000000000000000000000000048ad")
    coord._handle_notification(data)

    assert coord.snapshot.system.system_state is None
    # message_count still increments — NAKs are still "messages received".
    assert coord.snapshot.message_count == 1
    coord.async_update_listeners.assert_called_once()


async def test_tcx_notification_battery_charge(hass: HomeAssistant) -> None:
    """A normal (non-NAK) TCX notification updates the snapshot."""
    from specialized_turbo.framing import pack_tcx

    coord = _make_coordinator(hass)
    coord._generation = BLEProfile.TCX
    coord._session = TCXSession()
    coord._protocol_revision = ProtocolRevision(TCXGeneration.TCX2, 0x12)

    # BATTERY1_STATE_OF_CHARGE uses wire command 0x0500, data = 0x34 (52%).
    payload = b"\x05\x00\x34"
    data = pack_tcx(payload)
    coord._handle_notification(data)

    assert coord.snapshot.battery.charge_pct == 52
    assert coord.snapshot.message_count == 1


async def test_tcx_poll_uses_negotiated_revision(hass: HomeAssistant) -> None:
    """Test TCX polling uses the active generation and revision map."""
    coord = _make_coordinator(hass)
    coord._tcx_transport = MagicMock()
    coord._protocol_revision = ProtocolRevision(TCXGeneration.TCX2, 0x12)

    with patch(
        "custom_components.specialized_turbo.coordinator.poll_tcx",
        new_callable=AsyncMock,
        return_value=False,
    ) as poll:
        await coord._poll_tcx_fields()

    poll.assert_awaited_once_with(
        coord._tcx_transport,
        coord.snapshot,
        coord._protocol_revision,
    )
