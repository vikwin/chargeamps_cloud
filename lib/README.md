# Charge Amps Cloud

Unofficial Python client for the Charge Amps Cloud API (eAPI v5). It uses the
account email, password, and the API key supplied by the user.

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

The full documentation is in the repository root and in `docs/`.
