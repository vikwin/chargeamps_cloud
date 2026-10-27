# Python client

`chargeamps-cloud` is an asynchronous client for the Charge Amps Cloud API
(eAPI v5). It requires an account email, password, and API key.

## Install

From the repository:

```bash
uv sync --project lib --all-extras
uv run --project lib python -c "import chargeamps_cloud; print(chargeamps_cloud.__version__)"
```

Or from a release wheel:

```bash
pip install chargeamps_cloud-0.1.1-py3-none-any.whl
```

## Usage

```python
import asyncio

from chargeamps_cloud import ChargeAmpsClient


async def main() -> None:
    async with ChargeAmpsClient("you@example.com", "password", "your-api-key") as client:
        for chargepoint in await client.get_chargepoints():
            status = await client.get_chargepoint_status(chargepoint.id)
            print(chargepoint.name, status.status)

            settings = await client.get_connector_settings(chargepoint.id, 1)
            settings.max_current = 10
            await client.set_connector_settings(settings)

            await client.remote_start(chargepoint.id, 1)


asyncio.run(main())
```

The client refreshes its bearer token automatically. A `401` response triggers
one re-login attempt before the error is raised.

## Charge points

| Method | Description |
| --- | --- |
| `get_chargepoints()` | Owned charge points, falling back to organisations |
| `get_owned_chargepoints()` | Charge points owned by the account |
| `get_organisation_chargepoints(org_id)` | Charge points of an organisation |
| `get_chargepoint(id)` | Charge point details |
| `get_chargepoint_status(id)` | Online status and connector statuses |
| `get_chargepoint_settings(id)` | Dimmer, downlight, maximum current |
| `set_chargepoint_settings(settings)` | Write charge point settings |
| `get_connector_settings(id, connector)` | Mode, RFID lock, cable lock, current |
| `set_connector_settings(settings)` | Write connector settings |
| `reboot(id)` | Reboot the charge point |

`ChargePointStatus.connector(connector_id)` returns the live state of one
connector, including per-phase measurements, power, session ID, and start time.

## Charging control

```python
await client.remote_start("charge-point-id", 1)
await client.remote_stop("charge-point-id", 1)
```

`remote_start` uses the first active RFID tag on the account when no tag is
passed. Pass `rfid`, `rfid_format`, and `rfid_length` to override it. Remote
start only takes effect when RFID lock is enabled on the connector.

The API accepts a placeholder tag when an account has no tag; pass
`allow_placeholder_tag=True` only if your charger accepts it.

## Sessions

```python
from datetime import UTC, datetime, timedelta

sessions = await client.get_charging_sessions(
    "charge-point-id",
    start_time=datetime.now(UTC) - timedelta(days=7),
)
for session in sessions:
    print(session.start_time, session.end_time, session.total_consumption_kwh, session.rfid)
```

`get_charging_session()` fetches one session, `get_connector_sessions()` returns
the sessions of a connector.

## Schedules and callbacks

```python
schedules = await client.get_schedules("charge-point-id")
await client.override_schedule("charge-point-id", 1)
await client.get_schedule_override_status("charge-point-id")

await client.enable_callbacks(["charge-point-id"])
await client.disable_callbacks(["charge-point-id"])
```

Schedules are supported for CAPI charge points by the external API. The Home
Assistant integration does not expose them.

## Organisation and partner endpoints

The client includes the organisation and partner endpoints of eAPI v5:
charge points, statuses, sessions, users, RFID tags, and partner RFID tags.
These endpoints require the appropriate account role.

## Errors

```python
from chargeamps_cloud import (
    ChargeAmpsApiError,
    ChargeAmpsAuthError,
    ChargeAmpsConnectionError,
    ChargeAmpsForbiddenError,
    ChargeAmpsNotFoundError,
    ChargeAmpsRateLimitError,
)
```

`ChargeAmpsRateLimitError.retry_after` contains the `Retry-After` header when
the API provides it.

## CLI

The CLI reads `.env` from the current directory (see `.env.example`):

```bash
uv run --project lib chargeamps whoami
uv run --project lib chargeamps chargepoints
uv run --project lib chargeamps status
uv run --project lib chargeamps sessions --days 7
uv run --project lib chargeamps rfids
uv run --project lib chargeamps start --connector 1
uv run --project lib chargeamps stop
uv run --project lib chargeamps mode On
uv run --project lib chargeamps current 16
uv run --project lib chargeamps raw GET /api/v5/chargepoints/owned
```

`--json` prints machine-readable output.

## Tests

```bash
uv run --project lib pytest
```

The tests use a local aiohttp server and recorded response fixtures; no
credentials are required.
