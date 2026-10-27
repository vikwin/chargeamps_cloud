# Home Assistant integration

## Architecture

The integration uses one `DataUpdateCoordinator` per config entry:

- Every poll fetches the charge points, live status, charge point settings, and
  connector settings.
- Session history is refreshed every 15 minutes. A newly observed active session
  is fetched individually so its RFID tag is available quickly.
- Lifetime energy is calculated from completed sessions plus the active session.
- The coordinator fires events when a car connects or disconnects and when a
  session starts or ends.

Polling is intentional: the external API is poll-based. The poll interval can be
changed in the options (10–300 seconds, default 30).

## Devices

| Device | Identifier | Parent |
| --- | --- | --- |
| Charge point | charge point ID | – |
| Connector | charge point ID + connector ID | charge point |

The connector device is named after its type (`Charger`, `Schuko`) and is linked
to the charge point as a child device.

## Setup

1. Copy `custom_components/chargeamps_cloud` to the Home Assistant config
   directory.
2. Restart Home Assistant.
3. Add the integration and enter email, password, and API key. If you do not
   have an API key, request one from
   [Charge Amps support](https://www.chargeamps.com/support/).
4. Optionally open **Configure** to set the poll interval, RFID tag, and tag
   format.

The API key is validated during setup. If the account has no charge points, the
flow aborts with a clear message.

## Reauthentication

If the password or API key stops working, Home Assistant starts a reauth flow.
The integration keeps a repair notification in the UI until the credentials are
updated.

## Options

| Key | Default | Notes |
| --- | --- | --- |
| `scan_interval` | 30 | Seconds between polls |
| `rfid` | empty | Hex tag for remote start; empty uses the first active tag |
| `rfid_format` | `Hex` | `Hex`, `Dec`, `ReverseDec` |
| `rfid_length` | `auto` | `4`, `7`, or `10` bytes; `auto` uses the API default |

## Behavior of the charging switch

- **On** enables charging. If RFID lock is disabled, the charger may also start
  automatically when a cable is connected.
- **Off** disables charging.
- If the charger is in `Schedule` mode (configured elsewhere), the switch shows
  on. Turning it off exits schedule mode; turning it on sets `On`.

The raw mode is available as the diagnostic **Mode** sensor.

## Remote start

Remote start requires RFID lock on the connector. The **Start charging** button
and the `start_charging` service use:

1. the RFID tag from the service call, or
2. the tag configured in the options, or
3. the first active tag on the account.

If none of these exist, the action fails with a clear error. The tag format and
length can be overridden per call.

## Services

See the root README for the service table. All device-based services expect the
connector device in the `device_id` field; **Reboot** expects the charge point
device.

## Events

Events are fired on the Home Assistant event bus:

- `chargeamps_cloud_car_connected`
- `chargeamps_cloud_car_disconnected`
- `chargeamps_cloud_session_started`
- `chargeamps_cloud_session_ended`

See [automations.md](automations.md) for examples.

## Diagnostics

**Settings → Devices & services → Charge Amps Cloud → Download diagnostics**
contains the entry configuration (credentials redacted), charge points, status,
settings, sessions, and calculated energy.

## Limitations

- No schedules, Green Charging, LED ring, or firmware updates in the UI.
- No local OCPP connection; all data comes from the cloud.
- The cloud API may change without notice.
