"""Specialized Turbo BLE integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, format_mac

from specialized_turbo import (
    BikeAdvertisement,
    BLEProfile,
    ProtocolEncryptionMethod,
)

from .const import (
    CONF_HMI_HARDWARE,
    CONF_HMI_SERIAL,
    CONF_WRAPPED_KEY,
)
from .coordinator import SpecializedTurboCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

type SpecializedTurboConfigEntry = ConfigEntry[SpecializedTurboCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: SpecializedTurboConfigEntry
) -> bool:
    """Set up Specialized Turbo from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    _async_migrate_device_registry(hass, entry, address)
    wrapped_key: str | None = entry.data.get(CONF_WRAPPED_KEY)
    hmi_hardware: str | None = entry.data.get(CONF_HMI_HARDWARE)
    hmi_serial: str | None = entry.data.get(CONF_HMI_SERIAL)
    advertisement = (
        BikeAdvertisement(
            generation=BLEProfile.TCX,
            encryption=ProtocolEncryptionMethod.AES_CTR,
            hmi_hardware=hmi_hardware,
            hmi_serial=hmi_serial,
        )
        if hmi_hardware is not None and hmi_serial is not None
        else None
    )

    def request_reauth(current_advertisement: BikeAdvertisement) -> None:
        data = dict(entry.data)
        data[CONF_HMI_HARDWARE] = current_advertisement.hmi_hardware
        data[CONF_HMI_SERIAL] = current_advertisement.hmi_serial
        hass.config_entries.async_update_entry(entry, data=data)
        hass.async_create_task(
            entry.async_start_reauth(hass),
            f"Reauthenticate Specialized Turbo {address}",
        )

    coordinator = SpecializedTurboCoordinator(
        hass,
        _LOGGER,
        address=address,
        wrapped_key=wrapped_key,
        advertisement=advertisement,
        reauth_callback=request_reauth,
    )

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start the coordinator. It will connect and subscribe on first poll.
    # async_start() returns a callback that stops the coordinator.
    entry.async_on_unload(coordinator.async_start())

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SpecializedTurboConfigEntry
) -> bool:
    """Unload a Specialized Turbo config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok and (coordinator := getattr(entry, "runtime_data", None)) is not None:
        await coordinator.async_shutdown()

    return unload_ok


@callback
def _async_migrate_device_registry(
    hass: HomeAssistant,
    entry: SpecializedTurboConfigEntry,
    address: str,
) -> None:
    """Normalize legacy HACS Bluetooth connections and merge duplicates."""
    normalized_address = format_mac(address)
    device_registry = dr.async_get(hass)
    matching_devices = [
        device
        for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        if any(
            connection_type == CONNECTION_BLUETOOTH
            and format_mac(connection_value) == normalized_address
            for connection_type, connection_value in device.connections
        )
    ]
    legacy_device = next(
        (
            device
            for device in matching_devices
            if (CONNECTION_BLUETOOTH, normalized_address) not in device.connections
        ),
        None,
    )
    if legacy_device is None:
        return

    entity_registry = er.async_get(hass)
    for duplicate in matching_devices:
        if duplicate.id == legacy_device.id:
            continue
        for entity in er.async_entries_for_device(
            entity_registry,
            duplicate.id,
            include_disabled_entities=True,
        ):
            if entity.config_entry_id == entry.entry_id:
                entity_registry.async_update_entity(
                    entity.entity_id,
                    device_id=legacy_device.id,
                )
        device_registry.async_remove_device(duplicate.id)

    legacy_connections = {
        connection
        for connection in legacy_device.connections
        if connection[0] == CONNECTION_BLUETOOTH
        and format_mac(connection[1]) == normalized_address
    }
    device_registry.async_update_device(
        legacy_device.id,
        new_connections=(legacy_device.connections - legacy_connections)
        | {(CONNECTION_BLUETOOTH, normalized_address)},
    )


async def async_migrate_entry(
    hass: HomeAssistant,
    entry: SpecializedTurboConfigEntry,
) -> bool:
    """Remove the legacy PIN field while preserving key material."""
    if entry.version < 3:
        data = dict(entry.data)
        data.pop("pin", None)
        hass.config_entries.async_update_entry(entry, data=data, version=3)
    return True
