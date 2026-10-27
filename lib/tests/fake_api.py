"""A tiny local HTTP server used instead of a mocking library."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from aiohttp import web
from aiohttp.test_utils import TestServer


@dataclass
class RecordedRequest:
    method: str
    path: str
    headers: dict[str, str]
    json: Any
    query: dict[str, str]


class FakeApi:
    """Serve queued responses and record incoming requests."""

    def __init__(self) -> None:
        self.app = web.Application()
        self.app.router.add_route("*", "/{tail:.*}", self._handle)
        self._server = TestServer(self.app)
        self.requests: list[RecordedRequest] = []
        self._responses: dict[tuple[str, str], list[tuple[int, str, dict[str, str]]]] = {}

    async def start(self) -> None:
        await self._server.start_server()

    async def stop(self) -> None:
        await self._server.close()

    @property
    def base_url(self) -> str:
        return str(self._server.make_url("")).rstrip("/")

    def add(
        self,
        method: str,
        path: str,
        *,
        payload: Any = None,
        body: str | None = None,
        status: int = 200,
        headers: dict[str, str] | None = None,
        repeat: int = 1,
    ) -> None:
        response_headers = dict(headers or {})
        if payload is not None:
            body = json.dumps(payload)
            response_headers.setdefault("Content-Type", "application/json")
        for _ in range(repeat):
            self._responses.setdefault((method.upper(), path), []).append((status, body or "", response_headers))

    def requests_for(self, method: str, path: str) -> list[RecordedRequest]:
        return [request for request in self.requests if request.method == method.upper() and request.path == path]

    def last(self, method: str, path: str) -> RecordedRequest:
        matches = self.requests_for(method, path)
        assert matches, f"No {method} {path} request was made; got {[(r.method, r.path) for r in self.requests]}"
        return matches[-1]

    async def _handle(self, request: web.Request) -> web.Response:
        raw = await request.text()
        try:
            json_body = json.loads(raw) if raw else None
        except ValueError:
            json_body = None
        self.requests.append(
            RecordedRequest(
                method=request.method,
                path=request.path,
                headers=dict(request.headers),
                json=json_body,
                query=dict(request.query),
            )
        )
        queue = self._responses.get((request.method, request.path))
        if not queue:
            return web.Response(status=404, text=f"No mocked response for {request.method} {request.path}")
        status, body, headers = queue.pop(0)
        return web.Response(status=status, body=body.encode(), headers=headers)
