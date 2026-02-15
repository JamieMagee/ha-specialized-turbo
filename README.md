# Specialized Turbo for Home Assistant

Custom integration that reads telemetry from Specialized Turbo e-bikes (Vado, Levo, Creo) over Bluetooth Low Energy. Discovers your bike automatically and exposes 19 sensor entities.

## Sensors

| Sensor | Unit | What it is |
|---|---|---|
| Battery | % | State of charge |
| Battery capacity | Wh | Total capacity |
| Battery remaining | Wh | Energy left |
| Battery health | % | Health percentage |
| Battery temperature | °C | Battery temp |
| Charge cycles | count | Total charge cycles |
| Battery voltage | V | Voltage |
| Battery current | A | Current draw |
| Speed | km/h | Current speed |
| Rider power | W | Your pedal power |
| Motor power | W | Motor power |
| Cadence | RPM | Pedaling cadence |
| Odometer | km | Total distance |
| Motor temperature | °C | Motor temp |
| Assist level | -- | Off / Eco / Trail / Turbo |
| ECO assist | % | ECO mode percentage (off by default) |
| Trail assist | % | Trail mode percentage (off by default) |
| Turbo assist | % | Turbo mode percentage (off by default) |

## Install

### HACS (easiest)

1. Open HACS in Home Assistant
2. Click **Integrations** → **⋮** → **Custom repositories**
3. Add `https://github.com/JamieMagee/ha-specialized-turbo` as type **Integration**
4. Click **Download**
5. Restart Home Assistant

### Manual install

1. Copy the `custom_components/specialized_turbo` folder to your `config/custom_components/` directory
2. Restart Home Assistant

## Setup

1. Turn on your bike
2. It should appear in Settings > Devices & Services
3. Enter the pairing PIN from the bike's TCU screen
4. Sensors show up after the first BLE notification arrives

If auto-discovery doesn't work, add it manually: Settings > Devices & Services > Add Integration > Specialized Turbo.

## Requirements

- Home Assistant 2024.1.0+
- A Bluetooth adapter HA can reach (local USB or ESPHome proxy with `active: true`)
- Specialized Turbo bike with BLE, 2017+ models with TCU

## Protocol

Uses the Gen 2 "TURBOHMI2017" BLE protocol. The protocol parser is embedded in the integration, so no extra pip packages are needed (bleak ships with HA).

The standalone library is at [specialized-turbo](https://github.com/JamieMagee/specialized-turbo), which has the full protocol reference and Python API.

## How it works

```
custom_components/specialized_turbo/
├── __init__.py          # Setup and teardown
├── manifest.json        # BLE discovery matcher
├── config_flow.py       # Auto-discovery + manual flow with PIN entry
├── const.py             # Domain, config keys
├── coordinator.py       # BLE connect, subscribe, parse notifications
├── sensor.py            # 19 sensor entities
├── strings.json         # UI text
├── translations/en.json
└── lib/                 # Protocol parser (from specialized-turbo)
    ├── protocol.py
    └── models.py
```

The coordinator is an `ActiveBluetoothDataUpdateCoordinator`. It picks up BLE advertisements passively, connects when needed, subscribes to GATT notifications, and pushes parsed data to the sensor entities.

## Credits

Protocol reverse-engineered by [Sepp62/LevoEsp32Ble](https://github.com/Sepp62/LevoEsp32Ble) (C++/ESP32, MIT license).

## License

MIT
