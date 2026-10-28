# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Release notes are generated from the matching section below.

## 0.2.0 - 2026-10-28

### Added

- Optional API key: the integration and CLI can authenticate through the Charge
  Amps portal session with email and password only
- `ChargeAmpsPortalClient` with charge points, live status, settings, connector
  settings, sessions, RFID tags, remote start/stop, and reboot
- Portal-mode tests and documentation
- Session data for portal mode is refreshed every two minutes

### Changed

- The API key is now optional in the Home Assistant config and reauth flows; an
  empty key selects the portal session
- The coordinator supports both authentication modes with the same entities and
  services
- Version bumped to 0.2.0

### Fixed

- Portal session timestamps are normalized to UTC
- Portal connector selection keeps both charger and Schuko connectors when the
  detail endpoint only returns one
- The placeholder RFID tag is ignored for remote start when real tags exist

## 0.1.1 - 2026-10-27

### Added

- Documentation that an API key can be requested from Charge Amps support
- HACS brand icon, release workflow, security policy, and publishing checklist
- Follow-up release notes in `CHANGELOG.md`

### Changed

- Version bumped to 0.1.1

### Fixed

- Compatibility with Home Assistant 2026.2 and newer device registry APIs
- Service definitions now use `device_id` fields accepted by hassfest
- Remote-start placeholder keyword mismatch in the coordinator

## 0.1.0 - 2026-10-27

### Added

- Python client for the Charge Amps Cloud API (eAPI v5)
- Authentication with email, password, and a user-provided API key
- Charge point status, power, per-phase measurements, and session history
- Remote start/stop, mode, current limit, cable lock, RFID lock, and reboot
- Home Assistant integration with sensors, binary sensors, switches, number,
  lock, buttons, services, and events
- Blueprint for authorizing a plugged-in car
- English documentation and CLI
