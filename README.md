# Charge Amps Cloud for Home Assistant

An unofficial Home Assistant integration and Python client for Charge Amps
charge points, using the Charge Amps Cloud API (eAPI v5) with your account
credentials and your API key.

The repository contains two deliverables:

| Folder | Purpose |
| --- | --- |
| `custom_components/chargeamps_cloud/` | Home Assistant integration (HACS compatible) |
| `lib/` | Standalone Python client, CLI, and tests |

The integration does not contain or distribute any Charge Amps credentials. You
need your own API key for your Charge Amps account. The key is stored in the
Home Assistant config entry and redacted from diagnostics.

## Features

- Charge point online status and detailed connector state
- Live power, per-phase current and voltage
- Current session energy, duration, start time, and RFID tag
- Lifetime energy and last-session energy
- Start and stop charging remotely
- Charging mode (`Off`, `On`, `Schedule`) and maximum current
- Cable lock and RFID lock
- Reboot button
- Session, car-connected, and car-disconnected events for automations
- Blueprint for authorizing a car when it is plugged in

Schedules, Green Charging, and LED controls are available in the Python client
but are not exposed as Home Assistant entities in this version.

## Requirements

- Home Assistant 2025.1 or newer
- A Charge Amps account (email and password)
- An API key for that account
- The charger must be online in the Charge Amps Cloud

## Installation

### Manual (current)

Copy the integration folder into your Home Assistant configuration:

```bash
cp -r custom_components/chargeamps_cloud /path/to/homeassistant/config/custom_components/
```

Restart Home Assistant, then go to **Settings → Devices & services → Add
integration** and search for **Charge Amps Cloud**.

### HACS

1. Make sure the repository is public.
2. In HACS, open **Custom repositories**.
3. Add `https://github.com/vikwin/chargeamps_cloud` with category **Integration**.
4. Install **Charge Amps Cloud** and restart Home Assistant.

The integration is self-contained; it does not download a package at setup
time.

## Configuration

Enter the email and password of your Charge Amps account and the API key for
that account. The key is validated during setup.

### Options

| Option | Description |
| --- | --- |
| Poll interval | Seconds between status polls (10–300, default 30) |
| RFID tag for remote start | Optional hex tag. Empty means the first active tag on the account is used |
| RFID format | `Hex`, `Dec`, or `ReverseDec` |
| RFID length | `auto`, `4`, `7`, or `10` bytes |

Remote start requires RFID lock on the connector. Enable **RFID lock** if you
want the charger to wait for an authorization instead of starting as soon as a
cable is connected.

## Entities

Each charge point becomes a device; each connector becomes a child device.

### Charge point

| Entity | Type |
| --- | --- |
| Online | binary sensor |
| Status | sensor (`Online` / `Offline`) |
| Firmware | diagnostic sensor |
| Total energy | sensor (kWh) |
| Reboot | diagnostic button |

### Connector

| Entity | Type |
| --- | --- |
| Car connected | binary sensor |
| Charging | binary sensor |
| Connector status | sensor (`Available`, `Preparing`, `Charging`, `SuspendedEV`, …) |
| Power | sensor (W) |
| Session energy | sensor (kWh) |
| Current L1 / L2 / L3 | sensor (A) |
| Voltage L1 / L2 / L3 | sensor (V) |
| Session started | timestamp sensor |
| Session duration | duration sensor |
| Session RFID | diagnostic sensor |
| Last session energy | sensor (kWh) |
| Mode | diagnostic sensor (`Off` / `On` / `Schedule`) |
| Charging enabled | switch |
| RFID lock | switch |
| Maximum current | number (A, 6–installation current) |
| Cable lock | lock |
| Start charging / Stop charging | buttons |

## Services

| Service | Target | Fields |
| --- | --- | --- |
| `chargeamps_cloud.start_charging` | connector device | `rfid`, `rfid_format`, `rfid_length` (all optional) |
| `chargeamps_cloud.stop_charging` | connector device | – |
| `chargeamps_cloud.set_mode` | connector device | `mode`: `Off`, `On`, `Schedule` |
| `chargeamps_cloud.set_current` | connector device | `current`: 6–32 A |
| `chargeamps_cloud.reboot` | charger device | – |
| `chargeamps_cloud.refresh` | – | – |

Example:

```yaml
service: chargeamps_cloud.start_charging
target:
  device_id: 0123456789abcdef0123456789abcdef
```

## Events

| Event | Data |
| --- | --- |
| `chargeamps_cloud_session_started` | `chargepoint_id`, `connector_id`, `session_id`, `rfid`, `started_at` |
| `chargeamps_cloud_session_ended` | `chargepoint_id`, `connector_id`, `session_id`, `rfid`, `energy_kwh`, `ended_at` |
| `chargeamps_cloud_car_connected` | `chargepoint_id`, `connector_id` |
| `chargeamps_cloud_car_disconnected` | `chargepoint_id`, `connector_id` |

## Automations

The blueprint **Charge Amps Cloud - authorize a plugged-in car** starts a
session when the connector reports a plugged-in car. Import it from
`custom_components/chargeamps_cloud/blueprints/automation/chargeamps_cloud/` or
create the automation manually:

```yaml
trigger:
  - platform: state
    entity_id: binary_sensor.driveway_charger_car_connected
    to: "on"
action:
  - service: chargeamps_cloud.start_charging
    target:
      device_id: 0123456789abcdef0123456789abcdef
```

## Python client

```bash
cp .env.example .env   # fill in email, password, and API key
uv sync --project lib --all-extras
uv run --project lib chargeamps whoami
uv run --project lib chargeamps status
```

The client is documented in [docs/library.md](docs/library.md).

## Project layout

```
lib/                                  Python package (chargeamps-cloud)
custom_components/chargeamps_cloud/   Home Assistant integration
tests/                                Home Assistant tests
docs/                                 Documentation
scripts/sync_lib.py                   Copies the library into the integration
```

The integration ships with a generated copy of the library at
`custom_components/chargeamps_cloud/chargeamps_cloud/`. After changing `lib/`,
run:

```bash
python scripts/sync_lib.py
```

## Disclaimer

This project is not affiliated with or supported by Charge Amps AB. It uses a
cloud API that may change without notice. Use it at your own risk and make sure
your use complies with the Charge Amps terms of service.

## License

MIT
