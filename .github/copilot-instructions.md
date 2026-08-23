# Copilot instructions for ha-specialized-turbo

## Project overview

Custom Home Assistant integration for Specialized Turbo e-bikes over Bluetooth Low Energy. Uses the [`specialized-turbo`](https://github.com/JamieMagee/specialized-turbo) PyPI package for BLE protocol parsing. Distributed via HACS.

## Architecture

Data flows one direction: library connection and telemetry monitor to the
coordinator snapshot, then to sensor entities.

- **`specialized-turbo` (PyPI)** provides advertisement parsing, pairing,
  service detection, identification, encrypted transport, telemetry parsing,
  polling, and the `TelemetrySnapshot` data model.
- **`coordinator.py`** is a thin `ActiveBluetoothDataUpdateCoordinator`
  adapter around `SpecializedConnection` and `TelemetryMonitor`. Home Assistant
  supplies the managed BLE client factory and event loop.
- **`sensor.py`** defines the 26 sensor descriptions. Each sensor reads from
  the coordinator snapshot.
- **`config_flow.py`** handles Bluetooth/manual setup, encrypted-bike account
  or wrapped-key setup, reauthentication, and key reconfiguration. Passwords and
  cloud tokens are transient; config entries store only the per-bike wrapped
  key and HMI identifiers.
- **`__init__.py`** stores the coordinator in `entry.runtime_data` and removes
  the unused legacy PIN during migration.

## Key types from specialized-turbo

- `BLEProfile(StrEnum)` -- `TCU1` or `TCX`. Controls which GATT UUIDs to use.
- `SpecializedConnection` owns pairing, protocol selection, identification,
  and polling for TCU1 and TCX bikes.
- `TelemetryMonitor` owns notification parsing and publishes updated snapshots.
- `TelemetrySnapshot` contains battery, motor, bike, and ride state.

## Conventions

- Coordinator state lives in `coordinator.snapshot` and `coordinator.data`.
- Sensor descriptions use frozen dataclasses with `kw_only=True` and `value_fn: Callable[[TelemetrySnapshot], Any]`.
- Disabled-by-default sensors: `entity_registry_enabled_default=False`.
- `strings.json` and `translations/en.json` must stay in sync.
- Discovery matching in `manifest.json` covers legacy `TURBOHMI`, modern
  10-byte Nordic advertisements through Specialized service UUIDs, and TCU1.
- Do not request or store a pairing PIN. The Bluetooth backend manages pairing.
- Wrapped keys, HMI identifiers, and legacy PINs must be redacted from diagnostics.

## Adding a new sensor

1. If the field is new upstream: add it to `specialized-turbo` first, bump the version pin in `manifest.json`.
2. Add a `SpecializedSensorEntityDescription` to `SENSOR_DESCRIPTIONS` in `sensor.py` with a `value_fn` lambda.
3. Add translation keys in `strings.json` and `translations/en.json` under `entity.sensor.<key>`.

## Project structure

```
custom_components/specialized_turbo/
  __init__.py       Entry setup/teardown
  config_flow.py    BLE discovery, key setup, reauth, and reconfigure flows
  const.py          Domain and config-entry constants
  coordinator.py    Home Assistant adapter for the library connection
  sensor.py         26 sensor descriptions and entity class
  manifest.json     BLE discovery matcher (manufacturer_id 89)
  strings.json      UI strings
  translations/
    en.json         English translations (must match strings.json)
```
