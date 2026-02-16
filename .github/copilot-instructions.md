# Copilot Instructions — ha-specialized-turbo

## Project Overview

Custom Home Assistant integration that reads telemetry from Specialized Turbo e-bikes over Bluetooth Low Energy. It uses the Gen 2 "TURBOHMI2017" BLE protocol with no external pip packages beyond `bleak` (ships with HA). Distributed via HACS.

## Architecture

Data flows in one direction: **BLE notification → protocol parser → coordinator snapshot → sensor entities**.

- **`lib/protocol.py`** — Standalone BLE protocol definition. Contains UUID constants, sender/channel enums (`Sender`, `BatteryChannel`, `MotorChannel`, `BikeSettingsChannel`), field registration via `_reg()`, and `parse_message()` which decodes raw bytes into `ParsedMessage`. Field definitions map `(sender, channel)` pairs to names, units, sizes, and conversion lambdas. The secondary battery (sender `0x04`) auto-duplicates all primary battery field defs.
- **`lib/models.py`** — Mutable dataclass state containers (`BatteryState`, `MotorState`, `BikeSettings`) with `_CHANNEL_MAP` dicts routing channel IDs to attribute names. `TelemetrySnapshot` aggregates all sub-models and routes messages via `update_from_message()`.
- **`coordinator.py`** — `ActiveBluetoothDataUpdateCoordinator` subclass. Manages BLE connection lifecycle, subscribes to GATT `CHAR_NOTIFY`, calls `parse_message()` on each notification, updates `self.snapshot`, and pushes to HA via `async_set_updated_data(None)`. The coordinator passes `None` as data — entities read directly from `coordinator.snapshot`.
- **`sensor.py`** — Defines `SENSOR_DESCRIPTIONS` tuple of `SpecializedSensorEntityDescription` (frozen dataclass extending `SensorEntityDescription` with a `value_fn` lambda). Each sensor reads from the snapshot. Sensors are available only after `snapshot.message_count > 0`.
- **`config_flow.py`** — Two entry points: `async_step_bluetooth` (auto-discovery) and `async_step_user` (manual). Both collect an optional pairing PIN. Discovery matching uses `is_specialized_advertisement()` from `lib/`.
- **`__init__.py`** — Stores coordinator in `hass.data[DOMAIN][entry.entry_id]`; sensor platform retrieves it from there.

## Key Patterns

### Adding a new sensor
1. If the BLE field is new: add a `_reg()` call in `lib/protocol.py` with sender, channel, name, unit, byte size, and conversion function.
2. Add the attribute to the corresponding state dataclass in `lib/models.py` and its `_CHANNEL_MAP`.
3. Add a `SpecializedSensorEntityDescription` entry to `SENSOR_DESCRIPTIONS` in `sensor.py` with a `value_fn` lambda reading from the snapshot.
4. Add translation keys in both `strings.json` and `translations/en.json` under `entity.sensor.<key>`.

### Adding a new sender/subsystem
1. Add the sender to the `Sender` enum and create a channel `IntEnum` in `protocol.py`.
2. Create a new state dataclass in `models.py` with `_CHANNEL_MAP` and `update()`/`as_dict()`.
3. Add it as a field on `TelemetrySnapshot` and add routing in `update_from_message()`.

### Coordinator data flow
The coordinator's generic type is `None` — it calls `async_set_updated_data(None)` because state lives in `coordinator.snapshot`, not in the data payload. Entities access `self.coordinator.snapshot` directly.

## Conventions

- **Type alias**: `SpecializedTurboConfigEntry = ConfigEntry` is defined in `__init__.py` for type narrowing.
- **Sensor descriptions**: Use frozen dataclasses with `kw_only=True`; each has a `value_fn: Callable[[TelemetrySnapshot], Any]` lambda.
- **Disabled-by-default sensors**: Set `entity_registry_enabled_default=False` (e.g., assist percentage sensors).
- **Translation**: `strings.json` and `translations/en.json` must stay in sync with identical content. Entity names go under `entity.sensor.<translation_key>`.
- **BLE UUIDs**: All UUIDs use the custom base `000000xx-3731-3032-494d-484f42525554` ("TURBOHMI2017" reversed). Use `_uuid(short)` to generate.
- **Protocol fields**: Registered via `_reg(sender, channel, name, unit, size, convert)` in `protocol.py`. Conversion functions handle scaling (e.g., `v / 10.0` for speed/cadence, `v / 5.0 + 20.0` for voltage).
- **Discovery matching**: `manifest.json` uses `manufacturer_id: 89` (Nordic) with `manufacturer_data_start` matching "TURBOHMI" ASCII bytes.

## Project Structure

```
custom_components/specialized_turbo/
├── __init__.py          # Entry setup/teardown, stores coordinator in hass.data
├── config_flow.py       # BLE auto-discovery + manual flow with PIN
├── const.py             # DOMAIN, CONF_PIN, DEFAULT_SCAN_TIMEOUT
├── coordinator.py       # ActiveBluetoothDataUpdateCoordinator subclass
├── sensor.py            # 18 sensor entity descriptions + entity class
├── manifest.json        # BLE discovery matcher (manufacturer_id 89)
├── strings.json         # UI strings (must match translations/en.json)
└── lib/                 # Embedded protocol library (no HA dependencies)
    ├── __init__.py      # Re-exports all public symbols
    ├── protocol.py      # UUIDs, enums, field defs, parse_message()
    └── models.py        # BatteryState, MotorState, BikeSettings, TelemetrySnapshot
```

The `lib/` package is intentionally HA-independent — it can be tested standalone and mirrors the upstream [specialized-turbo](https://github.com/JamieMagee/specialized-turbo) library.
