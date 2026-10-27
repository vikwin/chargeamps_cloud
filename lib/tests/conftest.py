"""Shared fixtures for the library tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(Path(__file__).parent))

from fake_api import FakeApi  # noqa: E402


@pytest.fixture
async def api():
    instance = FakeApi()
    await instance.start()
    try:
        yield instance
    finally:
        await instance.stop()


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def login_payload() -> dict[str, Any]:
    return fixture("login")


@pytest.fixture
def chargepoints_payload() -> list[dict[str, Any]]:
    return fixture("chargepoints")


@pytest.fixture
def status_payload() -> dict[str, Any]:
    return fixture("status")


@pytest.fixture
def connector_settings_payload() -> dict[str, Any]:
    return fixture("connector_settings")


@pytest.fixture
def sessions_payload() -> list[dict[str, Any]]:
    return fixture("sessions")
