# Specialized Turbo for Home Assistant

Custom integration that reads telemetry from Specialized Turbo e-bikes over Bluetooth Low Energy. Auto-discovers your bike and exposes 26 sensors.

Supports TCU1, TCX1, TCX2, TCX3, and TCX4 bikes.

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
3. For a newer encrypted bike, choose either:
   - sign in to your Specialized account so Home Assistant can retrieve the
     bike's wrapped key; or
   - enter the 64-character wrapped key manually.
4. Sensors show up after the encrypted identification handshake completes

Account passwords and cloud tokens are not stored. The integration persists
only the per-bike wrapped key and HMI identifiers. Diagnostics redact the
wrapped key, HMI identifiers, and any PIN left by an older config entry.

If auto-discovery doesn't work, add it manually: Settings > Devices & Services > Add Integration > Specialized Turbo.

Older bikes that advertise only a `WSBC...` local name are supported. The
integration connects first, then selects the TCU1 or TCX protocol from the
bike's GATT services.

The integration asks the Bluetooth backend to pair when the bike requires it.
If your Bluetooth adapter or ESPHome proxy cannot provide the required pairing
agent, pair the bike through the operating system first.

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
- Newer bikes require internet access once during setup to retrieve their
  wrapped key, unless it is entered manually.
- Bikes that advertise AES encryption fail clearly and start reauthentication
  if their key is missing or invalid; they do not silently fall back to
  unencrypted traffic.

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

### Pairing fails

- Make sure the bike is not connected to another app or adapter.
- Some bikes require operating-system confirmation or numeric comparison.
- ESPHome Bluetooth proxies may not support the required pairing agent. Pair
  through a local Bluetooth adapter or the operating system first.

## Protocol

Uses the [specialized-turbo](https://github.com/JamieMagee/specialized-turbo)
Python library, which supports TCU1 and TCX1 through TCX4. See the library's
[protocol reference](https://github.com/JamieMagee/specialized-turbo/blob/main/docs/protocol.md)
for wire format details.

## License

MIT
