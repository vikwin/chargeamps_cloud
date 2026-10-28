# Charge Amps Cloud

Unofficial Python client for Charge Amps charge points. It supports the Charge
Amps Cloud API (eAPI v5) with an API key, and the portal session with email and
password only.

```python
import asyncio

from chargeamps_cloud import ChargeAmpsClient


async def main() -> None:
    async with ChargeAmpsClient("you@example.com", "password", "your-api-key") as client:
        for chargepoint in await client.get_chargepoints():
            status = await client.get_chargepoint_status(chargepoint.id)
            print(chargepoint.name, status.status)
            await client.remote_start(chargepoint.id, 1)


asyncio.run(main())
```

Portal session without an API key:

```python
import asyncio

from chargeamps_cloud import ChargeAmpsPortalClient


async def main() -> None:
    async with ChargeAmpsPortalClient("you@example.com", "password") as client:
        for chargepoint in await client.get_chargepoints():
            print(chargepoint.name)


asyncio.run(main())
```

The full documentation is in the repository root and in `docs/`.
