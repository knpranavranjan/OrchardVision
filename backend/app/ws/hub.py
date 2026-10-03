"""Live channel to the browser.

Every message is an envelope: {"type", "topic", "time", "data"}.

    vehicle / telemetry   one VehicleState, several times a second
    vehicle / event       one VehicleEvent
    vehicle / status      link, mission and pre-flight summary, once a second
"""

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

from app.core.conventions import to_iso_ms, utc_now

log = logging.getLogger(__name__)


def envelope(type_: str, data: Any = None, topic: str = "system") -> dict:
    return {"type": type_, "topic": topic, "time": to_iso_ms(utc_now()), "data": data}


class Hub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._loop = asyncio.get_running_loop()
        self._clients.add(ws)
        await ws.send_json(envelope("hello", {"clients": self.client_count}))

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, type_: str, data: Any = None, topic: str = "system") -> None:
        if not self._clients:
            return
        message = envelope(type_, data, topic)
        clients = list(self._clients)
        results = await asyncio.gather(
            *(c.send_json(message) for c in clients), return_exceptions=True
        )
        for client, result in zip(clients, results, strict=True):
            if isinstance(result, Exception):
                self.disconnect(client)

    def publish(self, type_: str, data: Any = None, topic: str = "system") -> None:
        """Fire-and-forget broadcast from synchronous code. Safe to call from any thread."""
        if not self._clients:
            return

        def send() -> None:
            task = asyncio.ensure_future(self.broadcast(type_, data, topic))
            task.add_done_callback(lambda t: t.exception())

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            if self._loop is not None:
                self._loop.call_soon_threadsafe(send)
        else:
            send()
