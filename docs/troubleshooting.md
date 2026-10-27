# Troubleshooting

## Setup fails with "invalid auth"

- Check the email and password.
- Check the API key. It is required and is not included with this project. If
  you do not have a key, request one from
  [Charge Amps support](https://www.chargeamps.com/support/).
- Use **Reauthenticate** on the integration entry after changing the password or
  key.

## Setup fails with "no charge points"

The account must own the charge point. For organisation-owned chargers, the
integration falls back to the organisations of the account; if the account has
no access there either, setup aborts.

You can enter an organisation ID in the setup form to query one organisation
explicitly.

## Entities are unavailable or stale

- Check whether the charger is online in the Charge Amps app.
- Check the Home Assistant log for `chargeamps_cloud` errors.
- Trigger **Refresh data** from the service or reload the entry.
- The cloud API may be temporarily unavailable.

## Remote start does not work

Remote start requires:

1. RFID lock enabled on the connector, and
2. an RFID tag (service call, options, or the first active tag on the account).

If the account has no tag, the button cannot start a session. Add a tag or use a
charger mode that starts automatically.

## The start button succeeds but the car does not charge

- The connector may be in `Off` mode.
- The cable may not be fully inserted; check the connector status.
- The charger may be offline or paused by the vehicle.
- Check the **Connector status** and **Mode** sensors.

## Rate limits and polling

The cloud API is not documented for rate limits. The default poll interval is
30 seconds; do not set it below 10 seconds. If you see HTTP 429 errors, increase
the interval.

## API key stops working

The key can be revoked or replaced by Charge Amps. Update it in the integration
options/reauth flow. The repository does not contain any key.

## Debug logging

```yaml
logger:
  default: warning
  logs:
    custom_components.chargeamps_cloud: debug
    chargeamps_cloud: debug
```

Do not paste credentials or tokens into issues. Diagnostics redact email,
password, API key, and tokens.

## Manual installation

HACS cannot install private repositories. If the repository is private, copy
`custom_components/chargeamps_cloud` into your Home Assistant configuration and
restart. The integration is self-contained; no package download is required.

## Repairs and reauthentication

If Home Assistant shows a repair for the integration, open it and enter the
password and API key again. The integration reloads automatically after a
successful reauthentication.
