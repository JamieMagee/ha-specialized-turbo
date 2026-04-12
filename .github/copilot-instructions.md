# Copilot Instructions -- ha-specialized-turbo

## Project overview

Custom Home Assistant integration for Specialized Turbo e-bikes over Bluetooth Low Energy. Uses the [`specialized-turbo`](https://github.com/JamieMagee/specialized-turbo) PyPI package for BLE protocol parsing. Distributed via HACS.

## Architecture

Data flows one direction: BLE notification -> protocol parser -> coordinator snapshot -> sensor entities.

- **`specialized-turbo` (PyPI)** -- BLE protocol definitions (UUIDs, enums, `parse_message()`), data models (`TelemetrySnapshot`), advertisement matching (`is_specialized_advertisement()`), CRC-16 framing, AES-128-CTR encryption, and `BikeParameter` enum for TCX2+ bikes.
- **`coordinator.py`** -- `ActiveBluetoothDataUpdateCoordinator` subclass. Manages BLE connection, subscribes to GATT `CHAR_NOTIFY`, calls `parse_message()` on notifications, updates `self.snapshot`. TCU1 bikes get periodic request-read polling via `_poll_tcu1_fields()`. Pushes to HA via `async_set_updated_data(None)` -- entities read from `coordinator.snapshot` directly.
- **`sensor.py`** -- `SENSOR_DESCRIPTIONS` tuple of `SpecializedSensorEntityDescription` (frozen dataclass with `value_fn` lambda). Each sensor reads from snapshot. Available only after `snapshot.message_count > 0`.
- **`config_flow.py`** -- Two entry points: `async_step_bluetooth` (auto-discovery) and `async_step_user` (manual). Both collect an optional pairing PIN. Discovery uses `is_specialized_advertisement()`.
- **`__init__.py`** -- Stores coordinator in `entry.runtime_data`.

## Key types from specialized-turbo

- `BLEProfile(StrEnum)` -- `TCU1` or `TCX`. Controls which GATT UUIDs to use.
- `detect_generation()` -- Returns `BLEProfile.TCU1` or `BLEProfile.TCX` from manufacturer data.
- `parse_message()` -- Parses TCU1 `[sender][channel][data]` format. Handles CRC-framed TCX packets too.
- `TelemetrySnapshot` -- Contains `BatteryState`, `MotorState`, `BikeSettings` sub-models.
- `TCU1_POLL_FIELDS` -- Tuple of `(sender, channel)` pairs to poll on TCU1 bikes.
- `CHAR_NOTIFY`, `CHAR_NOTIFY_TCU1` -- GATT characteristic UUIDs for TCX and TCU1 respectively.

## Conventions

- Coordinator generic type is `None` -- state lives in `coordinator.snapshot`, not the data payload.
- Sensor descriptions use frozen dataclasses with `kw_only=True` and `value_fn: Callable[[TelemetrySnapshot], Any]`.
- Disabled-by-default sensors: `entity_registry_enabled_default=False`.
- `strings.json` and `translations/en.json` must stay in sync.
- Discovery matching in `manifest.json` uses `manufacturer_id: 89` (Nordic) with `TURBOHMI` ASCII bytes.
- PIN is stored as `int | None` in config entries (the coordinator handles pairing directly via bleak, not through `SpecializedConnection`).

## Adding a new sensor

1. If the field is new upstream: add it to `specialized-turbo` first, bump the version pin in `manifest.json`.
2. Add a `SpecializedSensorEntityDescription` to `SENSOR_DESCRIPTIONS` in `sensor.py` with a `value_fn` lambda.
3. Add translation keys in `strings.json` and `translations/en.json` under `entity.sensor.<key>`.

## Project structure

```
custom_components/specialized_turbo/
  __init__.py       Entry setup/teardown
  config_flow.py    BLE auto-discovery + manual flow with PIN
  const.py          DOMAIN, CONF_PIN
  coordinator.py    ActiveBluetoothDataUpdateCoordinator subclass
  sensor.py         18 sensor entity descriptions + entity class
  manifest.json     BLE discovery matcher (manufacturer_id 89)
  strings.json      UI strings
  translations/
    en.json         English translations (must match strings.json)
```
