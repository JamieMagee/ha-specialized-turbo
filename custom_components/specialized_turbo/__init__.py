"""Specialized Turbo BLE integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from specialized_turbo import (
    BLEProfile,
    BikeAdvertisement,
    ProtocolEncryptionMethod,
)

from .const import (
    CONF_HMI_HARDWARE,
    CONF_HMI_SERIAL,
    CONF_PIN,
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
    pin_value = entry.data.get(CONF_PIN)
    pin = str(pin_value) if pin_value is not None else None
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
        pin=pin,
        wrapped_key=wrapped_key,
        advertisement=advertisement,
        reauth_callback=request_reauth,
    )

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start the coordinator — it will connect and subscribe on first poll.
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


async def async_migrate_entry(
    hass: HomeAssistant,
    entry: SpecializedTurboConfigEntry,
) -> bool:
    """Migrate legacy PIN storage without forcing reconfiguration."""
    if entry.version == 1:
        data = dict(entry.data)
        pin = data.get(CONF_PIN)
        if pin is not None:
            data[CONF_PIN] = str(pin)
        hass.config_entries.async_update_entry(entry, data=data, version=2)
    return True
