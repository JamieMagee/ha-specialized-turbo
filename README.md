# Specialized Turbo — Home Assistant Integration

Home Assistant custom integration for **Specialized Turbo** e-bikes (Vado, Levo, Creo, etc.) via Bluetooth Low Energy.

Automatically discovers your bike over BLE and provides real-time telemetry as sensor entities.

## Features

- **Auto-discovery** via BLE advertising (TURBOHMI manufacturer data)
- **19 sensor entities** — battery, speed, power, cadence, motor temp, odometer, assist level, and more
- **Push-based** — uses BLE notifications for instant updates, no polling
- **HACS compatible** — install via HACS custom repository

## Sensors

| Sensor | Unit | Description |
|---|---|---|
| Battery | % | State of charge |
| Battery capacity | Wh | Total battery capacity |
| Battery remaining | Wh | Remaining energy |
| Battery health | % | Battery health percentage |
| Battery temperature | °C | Battery temperature |
| Charge cycles | count | Total charge cycles |
| Battery voltage | V | Battery voltage |
| Battery current | A | Battery current draw |
| Speed | km/h | Current speed |
| Rider power | W | Human pedal power |
| Motor power | W | Electric motor power |
| Cadence | RPM | Pedaling cadence |
| Odometer | km | Total distance traveled |
| Motor temperature | °C | Motor temperature |
| Assist level | — | Off / Eco / Trail / Turbo |
| ECO assist | % | ECO mode power (disabled by default) |
| Trail assist | % | Trail mode power (disabled by default) |
| Turbo assist | % | Turbo mode power (disabled by default) |

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click **Integrations** → **⋮** → **Custom repositories**
3. Add `https://github.com/your-username/ha-specialized-turbo` as type **Integration**
4. Click **Download**
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/specialized_turbo` folder to your `config/custom_components/` directory
2. Restart Home Assistant

## Setup

1. Power on your Specialized Turbo bike
2. The bike should be auto-discovered in **Settings → Devices & Services**
3. Enter the **pairing PIN** displayed on the bike's TCU (Turbo Connect Unit) screen
4. Sensors will appear once the first BLE notification is received

If auto-discovery doesn't trigger, go to **Settings → Devices & Services → Add Integration → Specialized Turbo** and select your bike manually.

## Requirements

- Home Assistant 2024.1.0 or newer
- Bluetooth adapter accessible to Home Assistant
- Specialized Turbo bike with BLE (2017+ models with TCU)

## Protocol

This integration uses the Gen 2 "TURBOHMI2017" BLE protocol. The protocol library is embedded in the integration — no external Python packages are needed beyond `bleak` (which HA already ships).

See the companion library [specialized-turbo](https://github.com/your-username/specialized-turbo) for the full protocol reference and standalone Python usage.

## Architecture

```
custom_components/specialized_turbo/
├── __init__.py          # Integration setup (async_setup_entry / async_unload_entry)
├── manifest.json        # HA integration metadata, BLE discovery matcher
├── config_flow.py       # Bluetooth auto-discovery + manual user flow with PIN entry
├── const.py             # Domain name, config keys
├── coordinator.py       # ActiveBluetoothDataUpdateCoordinator — BLE connect + notify
├── sensor.py            # 19 SensorEntity definitions using CoordinatorEntity pattern
├── strings.json         # UI strings
├── translations/en.json # English translations
└── lib/                 # Protocol library (from specialized-turbo)
    ├── __init__.py      # Re-exports
    ├── protocol.py      # UUIDs, enums, parse_message(), conversions
    └── models.py        # TelemetrySnapshot, BatteryState, MotorState, BikeSettings
```

The coordinator uses HA's `ActiveBluetoothDataUpdateCoordinator` which:
1. Receives BLE advertisements passively
2. Connects and subscribes to GATT notifications when needed
3. Pushes parsed telemetry to entities via `async_set_updated_data()`

## Credits

Protocol reverse-engineered by [Sepp62/LevoEsp32Ble](https://github.com/Sepp62/LevoEsp32Ble) (C++/ESP32, MIT license).

## License

MIT
