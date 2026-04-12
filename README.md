# Specialized Turbo for Home Assistant

Custom integration that reads telemetry from Specialized Turbo e-bikes over Bluetooth Low Energy. Auto-discovers your bike and exposes 26 sensors.

Supports four protocol generations (TCU1, TCX2, TCX3, TCX4).

## Sensors

### Core sensors (all bikes)

| Sensor | Unit | Description |
| --- | --- | --- |
| Battery | % | State of charge |
| Battery capacity | Wh | Total capacity |
| Battery remaining | Wh | Energy left |
| Battery health | % | Health percentage |
| Battery temperature | °C | Battery temp |
| Charge cycles | count | Total charge cycles |
| Battery voltage | V | Voltage |
| Battery current | A | Current draw |
| Speed | km/h | Current speed |
| Rider power | W | Pedal power |
| Motor power | W | Motor power |
| Cadence | RPM | Pedaling cadence |
| Odometer | km | Total distance |
| Motor temperature | °C | Motor temp |
| Assist level | -- | Off / Eco / Trail / Turbo |
| ECO assist | % | ECO mode percentage (off by default) |
| Trail assist | % | Trail mode percentage (off by default) |
| Turbo assist | % | Turbo mode percentage (off by default) |

### TCX2+ sensors (newer bikes, disabled by default)

| Sensor | Unit | Description |
| --- | --- | --- |
| Range (long) | km | Estimated range (long mode) |
| Range (short) | km | Estimated range (short mode) |
| Altitude | m | Current altitude |
| Altitude gain | m | Cumulative climb |
| Gradient | % | Current gradient |
| System temperature | °C | System temp |
| Consumption | Wh/km | Energy consumption |
| Calories | kcal | Calories burned |

## Install

### HACS

1. Open HACS in Home Assistant
2. Click **Integrations** > three-dot menu > **Custom repositories**
3. Add `https://github.com/JamieMagee/ha-specialized-turbo` as type **Integration**
4. Click **Download**
5. Restart Home Assistant

### Manual

Copy the `custom_components/specialized_turbo` folder to your `config/custom_components/` directory and restart Home Assistant.

## Setup

1. Turn on your bike
2. It should appear in Settings > Devices & Services
3. Enter the pairing PIN from the bike's TCU screen (if prompted)
4. Sensors show up after the first BLE notification arrives

If auto-discovery doesn't work, add it manually: Settings > Devices & Services > Add Integration > Specialized Turbo.

Some newer bikes use numeric comparison pairing instead of a PIN. On those, pair through your OS Bluetooth settings first, then set up the integration without a PIN.

## Requirements

- Home Assistant 2024.1.0+
- A Bluetooth adapter HA can reach (local USB or ESPHome proxy with `active: true`)
- Specialized Turbo bike with BLE

## Data updates

The integration connects over BLE and subscribes to GATT notifications. The bike pushes telemetry as values change. For TCU1 bikes, the integration also polls fields that aren't pushed via notifications. For TCX2+ bikes, it runs an identification handshake on connect and polls system fields periodically.

The coordinator reconnects automatically if the BLE connection drops.

## Known limitations

- BLE range is typically 5-10 meters.
- Only one BLE client at a time. If Mission Control is connected, HA can't connect.
- Read-only -- the integration reads telemetry but cannot change settings or assist levels.
- When the bike sleeps, BLE stops and the connection is lost. Data resumes when it wakes.
- Some newer bikes encrypt their BLE communication. The integration tries to negotiate encryption keys, but this hasn't been verified on all models. Falls back to unencrypted if negotiation fails.

## Troubleshooting

### Bike not discovered

- Make sure the bike is powered on and awake (pedal or press the power button).
- Verify your Bluetooth adapter is working: check Settings > Devices & Services > Bluetooth.
- If using an ESPHome Bluetooth proxy, ensure `active: true` is set.
- The bike must be within BLE range of the adapter.

### Sensors show "Unavailable"

- The bike may be out of range or in sleep mode.
- Check if another app has an active BLE connection -- only one client at a time.
- Try restarting the integration from Settings > Devices & Services.

### Pairing PIN not accepted

- The PIN is displayed on the bike's TCU screen during pairing.
- If you don't see a PIN prompt, the bike may already be paired with another device.
- Some newer bikes use numeric comparison instead of PIN entry. Pair via your OS Bluetooth settings first, then set up the integration without a PIN.

## Protocol

Uses the [specialized-turbo](https://github.com/JamieMagee/specialized-turbo) Python library, which supports TCU1, TCX2, TCX3, and TCX4 protocol generations. See the library's [protocol reference](https://github.com/JamieMagee/specialized-turbo/blob/main/docs/protocol.md) for wire format details.

## License

MIT
