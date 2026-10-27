"""Command line interface for the Charge Amps Cloud API."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .client import ChargeAmpsClient
from .const import API_BASE_URL, DEFAULT_RFID_FORMAT
from .exceptions import ChargeAmpsError
from .models import ChargePoint, ChargingSession

DEFAULT_ENV_FILE = Path(".env")


def load_env(path: Path) -> None:
    """Load a simple ``KEY=VALUE`` file without overriding the environment."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _client(args: argparse.Namespace) -> ChargeAmpsClient:
    email = _env("CHARGEAMPS_EMAIL")
    password = _env("CHARGEAMPS_PASSWORD")
    api_key = _env("CHARGEAMPS_API_KEY")
    if not email or not password or not api_key:
        raise SystemExit("CHARGEAMPS_EMAIL, CHARGEAMPS_PASSWORD and CHARGEAMPS_API_KEY must be set (see .env.example)")
    return ChargeAmpsClient(
        email,
        password,
        api_key,
        base_url=args.base_url or _env("CHARGEAMPS_BASE_URL", API_BASE_URL),
    )


def _as_json(value: Any) -> str:
    def default(obj: Any) -> Any:
        if hasattr(obj, "__dataclass_fields__"):
            return {key: getattr(obj, key) for key in obj.__dataclass_fields__}
        return str(obj)

    return json.dumps(value, indent=2, default=default, ensure_ascii=False)


async def _pick_chargepoint(client: ChargeAmpsClient, chargepoint_id: str | None) -> ChargePoint:
    chargepoints = await client.get_chargepoints()
    if not chargepoints:
        raise SystemExit("No charge points found for this account")
    if chargepoint_id:
        for chargepoint in chargepoints:
            if chargepoint.id == chargepoint_id or chargepoint.name == chargepoint_id:
                return chargepoint
        raise SystemExit(f"Charge point {chargepoint_id!r} not found")
    preferred = _env("CHARGEAMPS_CHARGEPOINT_ID")
    if preferred:
        for chargepoint in chargepoints:
            if chargepoint.id == preferred or chargepoint.name == preferred:
                return chargepoint
    return chargepoints[0]


def _connector_id(chargepoint: ChargePoint, value: int | None) -> int:
    if value is not None:
        return value
    configured = _env("CHARGEAMPS_CONNECTOR_ID")
    if configured:
        return int(configured)
    if chargepoint.connectors:
        return chargepoint.connectors[0].connector_id
    return 1


async def cmd_whoami(args: argparse.Namespace) -> None:
    async with _client(args) as client:
        user = await client.get_current_user()
        if args.json:
            print(_as_json(user))
        else:
            print(f"User: {user.name} <{user.email}>")
            print(f"ID:   {user.id}")
            print("RFID tags:")
            for tag in user.rfid_tags:
                print(f"  - {tag.rfid}  dec={tag.rfid_dec} reverse={tag.rfid_dec_reverse} active={tag.active}")


async def cmd_chargepoints(args: argparse.Namespace) -> None:
    async with _client(args) as client:
        chargepoints = await client.get_chargepoints()
        if args.json:
            print(_as_json(chargepoints))
            return
        if not chargepoints:
            print("No charge points found")
            return
        for chargepoint in chargepoints:
            print(
                f"{chargepoint.id}  {chargepoint.name or ''}  type={chargepoint.type or '?'}  ocpp={chargepoint.ocpp_version or '?'}"
            )
            for connector in chargepoint.connectors:
                print(f"  connector {connector.connector_id}: {connector.type or '?'}")


async def cmd_status(args: argparse.Namespace) -> None:
    async with _client(args) as client:
        chargepoint = await _pick_chargepoint(client, args.chargepoint)
        status = await client.get_chargepoint_status(chargepoint.id)
        sessions: list[ChargingSession] = []
        if not args.json:
            sessions = await client.get_charging_sessions(chargepoint.id)
        if args.json:
            print(_as_json({"chargepoint": chargepoint, "status": status, "sessions": sessions if sessions else None}))
            return
        print(f"{chargepoint.name or chargepoint.id}: {status.status}")
        for connector in status.connector_statuses:
            print(
                f"  connector {connector.connector_id}: {connector.status}  "
                f"power={connector.charging_power_kw or 0:.2f} kW  "
                f"session={connector.session_id or '-'}  "
                f"energy={connector.total_consumption_kwh:.2f} kWh"
            )
            for phase in connector.measurements:
                print(f"    {phase.phase}: {phase.current or 0:.1f} A / {phase.voltage or 0:.0f} V")
            if connector.session_id:
                session = next((item for item in sessions if item.id == connector.session_id), None)
                if session:
                    print(f"    started={session.start_time} rfid={session.rfid} user={session.user_id}")


async def cmd_sessions(args: argparse.Namespace) -> None:
    async with _client(args) as client:
        chargepoint = await _pick_chargepoint(client, args.chargepoint)
        start = datetime.now(UTC) - timedelta(days=args.days) if args.days else None
        sessions = await client.get_charging_sessions(chargepoint.id, start_time=start)
        if args.json:
            print(_as_json(sessions))
            return
        for session in sorted(
            sessions, key=lambda item: item.start_time or datetime.min.replace(tzinfo=UTC), reverse=True
        ):
            end = session.end_time.isoformat() if session.end_time else "active"
            print(
                f"{session.id:>6}  connector={session.connector_id}  "
                f"{session.start_time} -> {end}  {session.total_consumption_kwh:.2f} kWh  "
                f"rfid={session.rfid or '-'} user={session.user_id or '-'}"
            )


async def cmd_rfids(args: argparse.Namespace) -> None:
    async with _client(args) as client:
        user = await client.get_current_user()
        if args.json:
            print(_as_json(user.rfid_tags))
            return
        if not user.rfid_tags:
            print("No RFID tags on this account; remote start needs an explicit tag")
            return
        for tag in user.rfid_tags:
            print(f"{tag.rfid}  dec={tag.rfid_dec}  reverse={tag.rfid_dec_reverse}  active={tag.active}")


async def cmd_start(args: argparse.Namespace) -> None:
    async with _client(args) as client:
        chargepoint = await _pick_chargepoint(client, args.chargepoint)
        connector_id = _connector_id(chargepoint, args.connector)
        rfid = args.rfid or _env("CHARGEAMPS_RFID")
        rfid_format = args.rfid_format or _env("CHARGEAMPS_RFID_FORMAT", DEFAULT_RFID_FORMAT)
        rfid_length = args.rfid_length
        if rfid_length is None and _env("CHARGEAMPS_RFID_LENGTH"):
            rfid_length = int(_env("CHARGEAMPS_RFID_LENGTH") or 0)
        start_auth = await client.remote_start(
            chargepoint.id,
            connector_id,
            rfid=rfid,
            rfid_format=rfid_format,
            rfid_length=rfid_length,
            allow_placeholder_tag=args.placeholder_tag,
        )
        if args.json:
            print(_as_json(start_auth))
        else:
            print(
                f"Remote start sent to {chargepoint.name or chargepoint.id} connector {connector_id} with RFID {start_auth.rfid}"
            )


async def cmd_stop(args: argparse.Namespace) -> None:
    async with _client(args) as client:
        chargepoint = await _pick_chargepoint(client, args.chargepoint)
        connector_id = _connector_id(chargepoint, args.connector)
        await client.remote_stop(chargepoint.id, connector_id)
        print(f"Remote stop sent to {chargepoint.name or chargepoint.id} connector {connector_id}")


async def cmd_mode(args: argparse.Namespace) -> None:
    async with _client(args) as client:
        chargepoint = await _pick_chargepoint(client, args.chargepoint)
        connector_id = _connector_id(chargepoint, args.connector)
        settings = await client.get_connector_settings(chargepoint.id, connector_id)
        settings.mode = args.mode
        await client.set_connector_settings(settings)
        print(f"Mode of {chargepoint.name or chargepoint.id} connector {connector_id} set to {args.mode}")


async def cmd_current(args: argparse.Namespace) -> None:
    async with _client(args) as client:
        chargepoint = await _pick_chargepoint(client, args.chargepoint)
        connector_id = _connector_id(chargepoint, args.connector)
        settings = await client.get_connector_settings(chargepoint.id, connector_id)
        settings.max_current = args.amps
        await client.set_connector_settings(settings)
        print(f"Max current of {chargepoint.name or chargepoint.id} connector {connector_id} set to {args.amps} A")


async def cmd_raw(args: argparse.Namespace) -> None:
    async with _client(args) as client:
        body = json.loads(args.body) if args.body else None
        result = await client.request(args.method.upper(), args.path, json_body=body)
        print(_as_json(result))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chargeamps", description="Charge Amps Cloud API command line client")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE), help="Path to a .env file (default: .env)")
    parser.add_argument("--base-url", default=None, help=f"API base URL (default: {API_BASE_URL})")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("whoami", help="Show the logged in user and RFID tags")
    subparsers.add_parser("chargepoints", help="List charge points")
    subparsers.add_parser("rfids", help="List RFID tags")

    status = subparsers.add_parser("status", help="Show the current charge point status")
    status.add_argument("--chargepoint", default=None, help="Charge point id or name")

    sessions = subparsers.add_parser("sessions", help="Show charging sessions")
    sessions.add_argument("--chargepoint", default=None, help="Charge point id or name")
    sessions.add_argument("--days", type=int, default=None, help="Limit to the last N days")

    start = subparsers.add_parser("start", help="Start charging")
    start.add_argument("--chargepoint", default=None)
    start.add_argument("--connector", type=int, default=None)
    start.add_argument("--rfid", default=None, help="RFID tag in hex (default: first tag on the account)")
    start.add_argument("--rfid-format", default=None, choices=("Hex", "Dec", "ReverseDec"))
    start.add_argument("--rfid-length", type=int, default=None, choices=(4, 7, 10))
    start.add_argument("--placeholder-tag", action="store_true", help="Use a placeholder tag if the account has no tag")

    stop = subparsers.add_parser("stop", help="Stop charging")
    stop.add_argument("--chargepoint", default=None)
    stop.add_argument("--connector", type=int, default=None)

    mode = subparsers.add_parser("mode", help="Set the connector mode")
    mode.add_argument("mode", choices=("Off", "On", "Schedule"))
    mode.add_argument("--chargepoint", default=None)
    mode.add_argument("--connector", type=int, default=None)

    current = subparsers.add_parser("current", help="Set the maximum charging current")
    current.add_argument("amps", type=float)
    current.add_argument("--chargepoint", default=None)
    current.add_argument("--connector", type=int, default=None)

    raw = subparsers.add_parser("raw", help="Call an arbitrary API endpoint")
    raw.add_argument("method")
    raw.add_argument("path")
    raw.add_argument("--body", default=None, help="JSON request body")

    return parser


async def async_main(args: argparse.Namespace) -> int:
    commands = {
        "whoami": cmd_whoami,
        "chargepoints": cmd_chargepoints,
        "rfids": cmd_rfids,
        "status": cmd_status,
        "sessions": cmd_sessions,
        "start": cmd_start,
        "stop": cmd_stop,
        "mode": cmd_mode,
        "current": cmd_current,
        "raw": cmd_raw,
    }
    await commands[args.command](args)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    load_env(Path(args.env_file))
    try:
        return asyncio.run(async_main(args))
    except ChargeAmpsError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
