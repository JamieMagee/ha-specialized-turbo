# Copilot Instructions — ha-specialized-turbo

## Project Overview

Custom Home Assistant integration that reads telemetry from Specialized Turbo e-bikes over Bluetooth Low Energy. It uses the [`specialized-turbo`](https://pypi.org/project/specialized-turbo/) PyPI package for BLE protocol parsing and data models. Distributed via HACS.

## Architecture

Data flows in one direction: **BLE notification → protocol parser → coordinator snapshot → sensor entities**.

- **`specialized-turbo` (PyPI)** — External library providing BLE protocol definitions (UUIDs, enums, `parse_message()`), data models (`BatteryState`, `MotorState`, `BikeSettings`, `TelemetrySnapshot`), and advertisement matching (`is_specialized_advertisement()`). See [github.com/JamieMagee/specialized-turbo](https://github.com/JamieMagee/specialized-turbo).
- **`coordinator.py`** — `ActiveBluetoothDataUpdateCoordinator` subclass. Manages BLE connection lifecycle, subscribes to GATT `CHAR_NOTIFY`, calls `parse_message()` on each notification, updates `self.snapshot`, and pushes to HA via `async_set_updated_data(None)`. The coordinator passes `None` as data — entities read directly from `coordinator.snapshot`.
- **`sensor.py`** — Defines `SENSOR_DESCRIPTIONS` tuple of `SpecializedSensorEntityDescription` (frozen dataclass extending `SensorEntityDescription` with a `value_fn` lambda). Each sensor reads from the snapshot. Sensors are available only after `snapshot.message_count > 0`.
- **`config_flow.py`** — Two entry points: `async_step_bluetooth` (auto-discovery) and `async_step_user` (manual). Both collect an optional pairing PIN. Discovery matching uses `is_specialized_advertisement()` from `specialized_turbo`.
- **`__init__.py`** — Stores coordinator in `entry.runtime_data`; sensor platform retrieves it from there.

## Key Patterns

### Adding a new sensor
1. If the BLE field is new: add it to the upstream `specialized-turbo` library first, then bump the version pin in `manifest.json`.
2. Add a `SpecializedSensorEntityDescription` entry to `SENSOR_DESCRIPTIONS` in `sensor.py` with a `value_fn` lambda reading from the snapshot.
3. Add translation keys in both `strings.json` and `translations/en.json` under `entity.sensor.<key>`.

### Adding a new sender/subsystem
1. Add it to the upstream `specialized-turbo` library first (sender enum, channel enum, state dataclass, snapshot routing).
2. Bump the version pin in `manifest.json`.
3. Add sensor descriptions in `sensor.py` for any new fields.

### Coordinator data flow
The coordinator's generic type is `None` — it calls `async_set_updated_data(None)` because state lives in `coordinator.snapshot`, not in the data payload. Entities access `self.coordinator.snapshot` directly. The coordinator is stored in `entry.runtime_data` (typed via `ConfigEntry[SpecializedTurboCoordinator]`).

## Conventions

- **Type alias**: `type SpecializedTurboConfigEntry = ConfigEntry[SpecializedTurboCoordinator]` is defined in `__init__.py` for type narrowing. Coordinator is stored in `entry.runtime_data`.
- **Sensor descriptions**: Use frozen dataclasses with `kw_only=True`; each has a `value_fn: Callable[[TelemetrySnapshot], Any]` lambda.
- **Disabled-by-default sensors**: Set `entity_registry_enabled_default=False` (e.g., assist percentage sensors).
- **Translation**: `strings.json` and `translations/en.json` must stay in sync with identical content. Entity names go under `entity.sensor.<translation_key>`.
- **BLE UUIDs**: All UUIDs use the custom base `000000xx-3731-3032-494d-484f42525554` ("TURBOHMI2017" reversed). Defined in the `specialized-turbo` library.
- **Protocol fields**: Defined in the `specialized-turbo` library via `_reg()`. Conversion functions handle scaling (e.g., `v / 10.0` for speed/cadence, `v / 5.0 + 20.0` for voltage).
- **Discovery matching**: `manifest.json` uses `manufacturer_id: 89` (Nordic) with `manufacturer_data_start` matching "TURBOHMI" ASCII bytes.

## Project Structure

```
custom_components/specialized_turbo/
├── __init__.py          # Entry setup/teardown, stores coordinator in entry.runtime_data
├── config_flow.py       # BLE auto-discovery + manual flow with PIN
├── const.py             # DOMAIN, CONF_PIN
├── coordinator.py       # ActiveBluetoothDataUpdateCoordinator subclass
├── sensor.py            # 18 sensor entity descriptions + entity class
├── manifest.json        # BLE discovery matcher (manufacturer_id 89)
├── strings.json         # UI strings (must match translations/en.json)
└── translations/
    └── en.json          # English translations (must match strings.json)
```

Protocol parsing and data models come from the [`specialized-turbo`](https://github.com/JamieMagee/specialized-turbo) PyPI package.
