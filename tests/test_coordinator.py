"""Tests for the Specialized Turbo coordinator adapter."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BleakError
from homeassistant.core import HomeAssistant
from specialized_turbo import (
    BikeAdvertisement,
    BLEProfile,
    DecryptionError,
    EncryptionKeyProviderError,
    EncryptionKeyRequiredError,
    ProtocolEncryptionMethod,
    TelemetrySnapshot,
)

from custom_components.specialized_turbo.coordinator import (
    _POLL_INTERVAL,
    SpecializedTurboCoordinator,
)

from .conftest import (
    MOCK_ADDRESS,
    MOCK_ENCRYPTED_MANUFACTURER_DATA,
    make_service_info,
)

_LOGGER = logging.getLogger(__name__)


def _make_coordinator(
    hass: HomeAssistant,
    *,
    wrapped_key: str | None = None,
    advertisement: BikeAdvertisement | None = None,
    reauth_callback: MagicMock | None = None,
) -> SpecializedTurboCoordinator:
    coordinator = SpecializedTurboCoordinator(
        hass,
        _LOGGER,
        address=MOCK_ADDRESS,
        wrapped_key=wrapped_key,
        advertisement=advertisement,
        reauth_callback=reauth_callback,
    )
    coordinator.async_update_listeners = MagicMock()
    return coordinator


class _FakeConnection:
    def __init__(self, *_args, **_kwargs) -> None:
        self.is_connected = False
        self.connect = AsyncMock(side_effect=self._connect)
        self.disconnect = AsyncMock(side_effect=self._disconnect)

    async def _connect(self) -> None:
        self.is_connected = True

    async def _disconnect(self) -> None:
        self.is_connected = False


class _FakeMonitor:
    def __init__(self, connection: _FakeConnection, **_kwargs) -> None:
        self.connection = connection
        self.snapshot = TelemetrySnapshot()
        self.on_update = None
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self.poll = AsyncMock(return_value=True)


def test_needs_poll_tracks_connection_and_interval(hass: HomeAssistant) -> None:
    coordinator = _make_coordinator(hass)
    service_info = make_service_info()

    assert coordinator._needs_poll(service_info, None) is True

    connection = _FakeConnection()
    connection.is_connected = True
    coordinator._connection = connection

    assert coordinator._needs_poll(service_info, _POLL_INTERVAL - 1) is False
    assert coordinator._needs_poll(service_info, _POLL_INTERVAL) is True


async def test_do_poll_connects_and_uses_monitor(
    hass: HomeAssistant,
) -> None:
    coordinator = _make_coordinator(hass)
    service_info = make_service_info()

    with (
        patch(
            "custom_components.specialized_turbo.coordinator.SpecializedConnection",
            _FakeConnection,
        ),
        patch(
            "custom_components.specialized_turbo.coordinator.TelemetryMonitor",
            _FakeMonitor,
        ),
    ):
        snapshot = await coordinator._do_poll(service_info)

    assert coordinator.connected is True
    assert coordinator._monitor is not None
    coordinator._monitor.start.assert_awaited_once_with(prime=False)
    coordinator._monitor.poll.assert_awaited_once()
    assert snapshot is coordinator.snapshot


async def test_connection_error_propagates(hass: HomeAssistant) -> None:
    coordinator = _make_coordinator(hass)
    service_info = make_service_info()

    class _FailingConnection(_FakeConnection):
        async def _connect(self) -> None:
            raise BleakError("failed")

    with (
        patch(
            "custom_components.specialized_turbo.coordinator.SpecializedConnection",
            _FailingConnection,
        ),
        pytest.raises(BleakError),
    ):
        await coordinator._do_poll(service_info)


@pytest.mark.parametrize(
    "error",
    [
        EncryptionKeyRequiredError("missing"),
        EncryptionKeyProviderError("invalid"),
        DecryptionError("stale"),
    ],
)
async def test_encryption_errors_request_reauth(
    hass: HomeAssistant,
    error: Exception,
) -> None:
    advertisement = BikeAdvertisement(
        generation=BLEProfile.TCX,
        encryption=ProtocolEncryptionMethod.AES_CTR,
        hmi_hardware="B.3.3",
        hmi_serial="80005338",
    )
    reauth = MagicMock()
    coordinator = _make_coordinator(
        hass,
        advertisement=advertisement,
        reauth_callback=reauth,
    )
    service_info = make_service_info(manufacturer_data=MOCK_ENCRYPTED_MANUFACTURER_DATA)

    class _MissingKeyConnection(_FakeConnection):
        async def _connect(self) -> None:
            raise error

    with (
        patch(
            "custom_components.specialized_turbo.coordinator.SpecializedConnection",
            _MissingKeyConnection,
        ),
        pytest.raises(type(error)),
    ):
        await coordinator._do_poll(service_info)

    reauth.assert_called_once()


def test_monitor_update_publishes_snapshot(hass: HomeAssistant) -> None:
    coordinator = _make_coordinator(hass)
    snapshot = TelemetrySnapshot()
    snapshot.battery.charge_pct = 75

    coordinator._handle_monitor_update(MagicMock(), snapshot)

    assert coordinator.snapshot is snapshot
    assert coordinator.data is snapshot
    coordinator.async_update_listeners.assert_called_once()


def test_disconnect_clears_runtime_connection(hass: HomeAssistant) -> None:
    coordinator = _make_coordinator(hass)
    coordinator._connection = _FakeConnection()
    coordinator._monitor = _FakeMonitor(coordinator._connection)

    coordinator._handle_disconnect()

    assert coordinator.connected is False
    assert coordinator._monitor is None
    coordinator.async_update_listeners.assert_called_once()


async def test_shutdown_stops_monitor_and_connection(hass: HomeAssistant) -> None:
    coordinator = _make_coordinator(hass)
    connection = _FakeConnection()
    connection.is_connected = True
    monitor = _FakeMonitor(connection)
    coordinator._connection = connection
    coordinator._monitor = monitor

    await coordinator.async_shutdown()

    monitor.stop.assert_awaited_once()
    connection.disconnect.assert_awaited_once()
    assert coordinator.connected is False


def test_partial_advertisement_keeps_hmi_metadata(hass: HomeAssistant) -> None:
    advertisement = BikeAdvertisement(
        generation=BLEProfile.TCX,
        encryption=ProtocolEncryptionMethod.AES_CTR,
        hmi_hardware="B.3.3",
        hmi_serial="80005338",
    )
    coordinator = _make_coordinator(hass, advertisement=advertisement)

    coordinator._update_protocol_metadata(
        make_service_info(manufacturer_data=MOCK_ENCRYPTED_MANUFACTURER_DATA)
    )
    complete_advertisement = coordinator._advertisement
    complete_bike_info = coordinator._bike_info
    partial = make_service_info(manufacturer_data={0x0059: b"TURBOHMI2017"})
    coordinator._update_protocol_metadata(partial)

    assert coordinator._advertisement is complete_advertisement
    assert complete_bike_info is not None
    assert complete_bike_info.complete is True
    assert coordinator._bike_info is complete_bike_info
