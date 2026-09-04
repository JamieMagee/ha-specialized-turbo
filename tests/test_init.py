"""Tests for Specialized Turbo integration setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from pytest_homeassistant_custom_component.common import MockConfigEntry
from specialized_turbo import TelemetrySnapshot

from custom_components.specialized_turbo import async_migrate_entry
from custom_components.specialized_turbo.const import CONF_PIN, DOMAIN

from .conftest import MOCK_ADDRESS, MOCK_ADDRESS_FORMATTED


async def test_setup_entry(hass: HomeAssistant) -> None:
    """Test successful setup of a config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: MOCK_ADDRESS, CONF_PIN: 1234},
        unique_id=MOCK_ADDRESS_FORMATTED,
    )
    entry.add_to_hass(hass)

    mock_coordinator = MagicMock()
    mock_coordinator.snapshot = TelemetrySnapshot()
    mock_coordinator.async_start.return_value = lambda: None
    mock_coordinator.async_shutdown = AsyncMock()

    with patch(
        "custom_components.specialized_turbo.SpecializedTurboCoordinator",
        return_value=mock_coordinator,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is mock_coordinator


async def test_setup_entry_device_not_in_range(hass: HomeAssistant) -> None:
    """Test setup succeeds even when bike is not in BLE range."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: MOCK_ADDRESS, CONF_PIN: 1234},
        unique_id=MOCK_ADDRESS_FORMATTED,
    )
    entry.add_to_hass(hass)

    mock_coordinator = MagicMock()
    mock_coordinator.snapshot = TelemetrySnapshot()
    mock_coordinator.async_start.return_value = lambda: None
    mock_coordinator.async_shutdown = AsyncMock()

    with patch(
        "custom_components.specialized_turbo.SpecializedTurboCoordinator",
        return_value=mock_coordinator,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED


async def test_setup_entry_no_pin(hass: HomeAssistant) -> None:
    """Test setup entry without a PIN."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: MOCK_ADDRESS},
        unique_id=MOCK_ADDRESS_FORMATTED,
    )
    entry.add_to_hass(hass)

    mock_coordinator = MagicMock()
    mock_coordinator.snapshot = TelemetrySnapshot()
    mock_coordinator.async_start.return_value = lambda: None
    mock_coordinator.async_shutdown = AsyncMock()

    with patch(
        "custom_components.specialized_turbo.SpecializedTurboCoordinator",
        return_value=mock_coordinator,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED


async def test_setup_merges_hacs_and_core_devices(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test setup preserves the legacy device and removes the Core duplicate."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: MOCK_ADDRESS},
        unique_id=MOCK_ADDRESS_FORMATTED,
    )
    entry.add_to_hass(hass)
    legacy_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(CONNECTION_BLUETOOTH, MOCK_ADDRESS)},
        name="Garage bike",
    )
    core_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(CONNECTION_BLUETOOTH, MOCK_ADDRESS_FORMATTED)},
        name="Specialized Turbo",
    )
    registry_entry = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{MOCK_ADDRESS_FORMATTED}_battery_charge_percent",
        config_entry=entry,
        device_id=core_device.id,
        suggested_object_id="bike_battery",
    )

    mock_coordinator = MagicMock()
    mock_coordinator.snapshot = TelemetrySnapshot()
    mock_coordinator.async_start.return_value = lambda: None
    mock_coordinator.async_shutdown = AsyncMock()

    with patch(
        "custom_components.specialized_turbo.SpecializedTurboCoordinator",
        return_value=mock_coordinator,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    assert [device.id for device in devices] == [legacy_device.id]
    assert legacy_device.name == "Garage bike"
    assert device_registry.async_get(legacy_device.id).connections == {
        (CONNECTION_BLUETOOTH, MOCK_ADDRESS_FORMATTED)
    }
    assert device_registry.async_get(core_device.id) is None
    assert (
        entity_registry.async_get(registry_entry.entity_id).device_id
        == legacy_device.id
    )


async def test_unload_entry(hass: HomeAssistant) -> None:
    """Test successful unloading of a config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: MOCK_ADDRESS, CONF_PIN: 1234},
        unique_id=MOCK_ADDRESS_FORMATTED,
    )
    entry.add_to_hass(hass)

    mock_coordinator = MagicMock()
    mock_coordinator.snapshot = TelemetrySnapshot()
    mock_coordinator.async_start.return_value = lambda: None
    mock_coordinator.async_shutdown = AsyncMock()

    with patch(
        "custom_components.specialized_turbo.SpecializedTurboCoordinator",
        return_value=mock_coordinator,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert result is True
    assert entry.state is ConfigEntryState.NOT_LOADED
    mock_coordinator.async_shutdown.assert_called_once()


async def test_migrate_removes_legacy_pin(hass: HomeAssistant) -> None:
    """Test migration removes the unused legacy PIN."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        data={CONF_ADDRESS: MOCK_ADDRESS, CONF_PIN: 1234},
        unique_id=MOCK_ADDRESS_FORMATTED,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    assert entry.version == 3
    assert CONF_PIN not in entry.data
