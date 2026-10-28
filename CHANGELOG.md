# Changelog

## 0.2.0 - 2026-10-28

- Optional API key; the integration can sign in through the Charge Amps portal
  session with email and password only
- Portal-session client with charge point data, sessions, remote start/stop,
  settings, RFID tags, and reboot
- Shared coordinator support for both authentication modes
- Portal session documentation and tests

## 0.1.1 - 2026-10-27

Follow-up release with publication and compatibility fixes.

- Compatibility with Home Assistant 2026.2 and newer (device registry APIs)
- Service definitions fixed for hassfest (`device_id` fields)
- API key request via Charge Amps support documented
- HACS brand icon, release workflow, security policy, publishing checklist

## 0.1.0 - 2026-10-27

Initial release.

- Python client for the Charge Amps Cloud API (eAPI v5)
- Authentication with email, password, and a user-provided API key
- Charge point status, power, per-phase measurements, session history
- Remote start/stop, mode, current limit, cable lock, RFID lock, reboot
- Home Assistant integration with sensors, binary sensors, switches, number,
  lock, buttons, services, and events
- Blueprint for authorizing a plugged-in car
- English documentation and CLI
