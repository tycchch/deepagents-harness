from __future__ import annotations

import asyncio
import subprocess
import sys
from collections.abc import AsyncIterator

from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from protocol.frame import RpcMessage, RpcRequest, RpcResponse, parse_message

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def next_request(method: str, params: dict, req_id: int | str = 1) -> tuple[str, int | str]:
    raw = RpcRequest(id=req_id, method=method, params=params).model_dump_json(exclude_none=True)
    return raw, req_id


def spawn_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> subprocess.Popen:
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(
        [sys.executable, "-m", "server", "--host", host, "--port", str(port)],
        **kwargs,
    )


class HarnessRpcError(RuntimeError):
    def __init__(self, message: str, code: int = -32000) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class HarnessClient:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        self.host = host
        self.port = port
        self._ws = None
        self._n = 0
        self._inbox: asyncio.Queue[RpcMessage] = asyncio.Queue()
        self._reader: asyncio.Task[None] | None = None

    @property
    def uri(self) -> str:
        return f"ws://{self.host}:{self.port}"

    def _next_id(self) -> int:
        self._n += 1
        return self._n

    async def connect(self, *, spawn: bool = True) -> None:
        self._ws = await connect_or_spawn(self.host, self.port, spawn=spawn)
        self._reader = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                if not isinstance(raw, str):
                    raw = raw.decode("utf-8")
                await self._inbox.put(parse_message(raw))
        except Exception:
            return

    async def close(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
            try:
                await self._reader
            except asyncio.CancelledError:
                pass
            self._reader = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def send_request(self, method: str, params: dict) -> int:
        if self._ws is None:
            raise HarnessRpcError("Not connected")
        raw, req_id = next_request(method, params, req_id=self._next_id())
        await self._ws.send(raw)
        return int(req_id)

    async def request_iter(self, method: str, params: dict) -> AsyncIterator[RpcMessage]:
        req_id = await self.send_request(method, params)
        while True:
            msg = await self._inbox.get()
            yield msg
            if isinstance(msg, RpcResponse) and msg.id == req_id:
                if msg.error is not None:
                    raise HarnessRpcError(msg.error.message, msg.error.code)
                return

    async def request(self, method: str, params: dict) -> tuple[dict, list[RpcMessage]]:
        notes: list[RpcMessage] = []
        result: dict = {}
        async for msg in self.request_iter(method, params):
            if isinstance(msg, RpcResponse):
                result = msg.result or {}
            else:
                notes.append(msg)
        return result, notes


async def connect_or_spawn(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    spawn: bool = True,
    attempts: int = 50,
) -> object:
    uri = f"ws://{host}:{port}"
    try:
        return await connect(uri, open_timeout=0.4)
    except (OSError, TimeoutError, WebSocketException):
        if not spawn:
            raise
    spawn_server(host, port)
    last_exc: Exception | None = None
    for _ in range(attempts):
        await asyncio.sleep(0.1)
        try:
            return await connect(uri, open_timeout=0.4)
        except (OSError, TimeoutError, WebSocketException) as exc:
            last_exc = exc
    raise RuntimeError(f"failed to connect {uri}") from last_exc
