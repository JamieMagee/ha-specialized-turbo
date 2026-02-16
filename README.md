# Specialized Turbo for Home Assistant

Custom integration that reads telemetry from Specialized Turbo e-bikes (Vado, Levo, Creo) over Bluetooth Low Energy. Discovers your bike automatically and exposes 19 sensor entities.

## Sensors

| Sensor | Unit | What it is |
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

## Removal

1. Go to **Settings** > **Devices & Services**
2. Find **Specialized Turbo** and click the three-dot menu
3. Click **Delete**
4. If installed via HACS, open HACS > **Integrations**, find Specialized Turbo, click the three-dot menu > **Remove**
5. Restart Home Assistant

## Requirements

- Home Assistant 2024.1.0+
- A Bluetooth adapter HA can reach (local USB or ESPHome proxy with `active: true`)
- Specialized Turbo bike with BLE, 2017+ models with TCU

## Supported devices

Specialized Turbo e-bikes with the Gen 2 BLE TCU ("TURBOHMI2017" protocol), including:

- **Turbo Vado** (all SL and full-power variants)
- **Turbo Levo** (all SL and full-power variants)
- **Turbo Creo** (all SL and full-power variants)
- **Turbo Como** (SL and full-power)
- **Turbo Tero**

Generally, any 2017+ Specialized Turbo bike that broadcasts a "TURBOHMI" BLE advertisement should work. Older bikes without a TCU display are not supported.

## Data updates

The integration uses a push-based approach. It connects to the bike over BLE, subscribes to GATT notifications on the telemetry characteristic, and receives updates whenever the bike broadcasts new data. No polling is performed. The coordinator reconnects automatically if the BLE connection drops.

## Known limitations

- **Range**: BLE range is typically 5-10 meters. The bike must be within range of a Bluetooth adapter that Home Assistant can access.
- **Single connection**: Only one BLE client can be connected to the bike at a time. If the Specialized Mission Control app is connected, Home Assistant cannot connect simultaneously.
- **No write support**: The integration is read-only. It cannot change assist levels, settings, or send commands to the bike.
- **Secondary battery**: Range-extender (Battery 2) data is parsed but not currently exposed as sensor entities.
- **Sleep mode**: When the bike enters sleep mode, BLE advertisements stop and the connection is lost. Data resumes when the bike wakes up.

## Use cases

Here are some ways you can use this integration:

- **Battery monitoring**: Track battery charge level over time using statistics and long-term graphs.
- **Ride tracking**: Use the odometer and speed sensors to log rides.
- **Maintenance alerts**: Create automations that notify you when charge cycles exceed a threshold or battery health drops.
- **Garage presence**: Use the bike's BLE presence to trigger automations when you arrive home.

## Automation examples

### Notify when battery is fully charged

```yaml
automation:
  - alias: "Bike battery full"
    trigger:
      - platform: numeric_state
        entity_id: sensor.specialized_turbo_battery
        above: 99
    action:
      - service: notify.mobile_app
        data:
          message: "Your bike is fully charged!"
```

### Notify when battery health drops below 80%

```yaml
automation:
  - alias: "Bike battery health warning"
    trigger:
      - platform: numeric_state
        entity_id: sensor.specialized_turbo_battery_health
        below: 80
    action:
      - service: notify.mobile_app
        data:
          message: "Bike battery health is {{ states('sensor.specialized_turbo_battery_health') }}%. Consider scheduling a service."
```

## Troubleshooting

### Bike not discovered

- Make sure the bike is powered on and awake (pedal or press the power button).
- Verify your Bluetooth adapter is working: check **Settings > Devices & Services > Bluetooth**.
- If using an ESPHome Bluetooth proxy, ensure `active: true` is set in the config.
- The bike must be within BLE range (~5-10 meters) of the adapter.

### Sensors show "Unavailable"

- The bike may be out of range or in sleep mode.
- Check if another app (e.g., Mission Control) has an active BLE connection to the bike — only one client can connect at a time.
- Try restarting the integration from **Settings > Devices & Services**.

### Pairing PIN not accepted

- The PIN is displayed on the bike's TCU screen during the pairing process.
- If you don't see a PIN prompt, the bike may already be paired with another device. Reset the BLE pairing on the bike if needed.
- Some Bluetooth backends don't support programmatic PIN pairing. In that case, pair via your OS Bluetooth settings first, then set up the integration without a PIN.

## Protocol

Uses the Gen 2 "TURBOHMI2017" BLE protocol. The standalone library is at [specialized-turbo](https://github.com/JamieMagee/specialized-turbo), which has the full protocol reference and Python API.

## How it works

```plain
custom_components/specialized_turbo/
├── __init__.py          # Setup and teardown
├── manifest.json        # BLE discovery matcher
├── config_flow.py       # Auto-discovery + manual flow with PIN entry
├── const.py             # Domain, config keys
├── coordinator.py       # BLE connect, subscribe, parse notifications
├── sensor.py            # 19 sensor entities
├── strings.json         # UI text
└── translations/en.json
```

The coordinator is an `ActiveBluetoothDataUpdateCoordinator`. It picks up BLE advertisements passively, connects when needed, subscribes to GATT notifications, and pushes parsed data to the sensor entities.

## Credits

Protocol reverse-engineered by [Sepp62/LevoEsp32Ble](https://github.com/Sepp62/LevoEsp32Ble) (C++/ESP32, MIT license).

## License

MIT
