# Automations

All examples use the connector device. Replace the `device_id` with the one from
**Settings → Devices & services → Charge Amps Cloud → your connector → Device
info**.

## Authorize a car when it is plugged in

Use the bundled blueprint:

1. Go to **Settings → Automations & scenes → Blueprints**.
2. Import `custom_components/chargeamps_cloud/blueprints/automation/chargeamps_cloud/auto_start_on_plug.yaml`.
3. Select the **Car connected** binary sensor and the **Start charging** button.

Or write it manually:

```yaml
alias: Authorize car at the charger
trigger:
  - platform: state
    entity_id: binary_sensor.driveway_charger_car_connected
    to: "on"
action:
  - service: chargeamps_cloud.start_charging
    target:
      device_id: 0123456789abcdef0123456789abcdef
mode: single
```

Remote start requires **RFID lock** to be on. If your charger should start
automatically for every car, leave RFID lock off instead.

## Only authorize when someone is home

```yaml
alias: Authorize car when someone is home
trigger:
  - platform: state
    entity_id: binary_sensor.driveway_charger_car_connected
    to: "on"
condition:
  - condition: state
    entity_id: person.alex
    state: home
action:
  - service: chargeamps_cloud.start_charging
    target:
      device_id: 0123456789abcdef0123456789abcdef
```

## Notify when a session ends

```yaml
alias: Charging session finished
trigger:
  - platform: event
    event_type: chargeamps_cloud_session_ended
action:
  - service: notify.mobile_app_phone
    data:
      title: Charging finished
      message: >-
        Session {{ trigger.event.data.session_id }} used
        {{ trigger.event.data.energy_kwh }} kWh
        (tag {{ trigger.event.data.rfid or 'unknown' }}).
```

## Log which car is charging

The charger reports the RFID tag, not the vehicle. Map tags to cars in a
template or automation:

```yaml
alias: Remember the last charging tag
trigger:
  - platform: event
    event_type: chargeamps_cloud_session_started
action:
  - service: input_text.set_value
    target:
      entity_id: input_text.last_charging_tag
    data:
      value: "{{ trigger.event.data.rfid or 'unknown' }}"
```

Give each car its own tag if you want to distinguish them.

## Limit current at night

```yaml
alias: Lower charging current at night
trigger:
  - platform: time
    at: "22:00:00"
action:
  - service: chargeamps_cloud.set_current
    target:
      device_id: 0123456789abcdef0123456789abcdef
    data:
      current: 6
```

## Pause charging when the house needs power

```yaml
alias: Pause charger on high house load
trigger:
  - platform: numeric_state
    entity_id: sensor.house_power
    above: 8000
    for: "00:02:00"
action:
  - service: chargeamps_cloud.set_current
    target:
      device_id: 0123456789abcdef0123456789abcdef
    data:
      current: 6
mode: single
```

## Events reference

| Event | Useful data |
| --- | --- |
| `chargeamps_cloud_car_connected` | `chargepoint_id`, `connector_id` |
| `chargeamps_cloud_car_disconnected` | `chargepoint_id`, `connector_id` |
| `chargeamps_cloud_session_started` | `chargepoint_id`, `connector_id`, `session_id`, `rfid`, `started_at` |
| `chargeamps_cloud_session_ended` | `chargepoint_id`, `connector_id`, `session_id`, `rfid`, `energy_kwh`, `ended_at` |
