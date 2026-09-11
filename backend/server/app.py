from __future__ import annotations

import argparse
import asyncio
import sys

from websockets.asyncio.server import ServerConnection, serve

from config.load import load_harness_config
from config.schema import HarnessConfig
from protocol.frame import RpcNotification, dumps_message
from server.rpc import RpcDispatcher
from pathlib import Path

from server.session import ThreadStore

THREADS_PATH = Path.home() / ".harness" / "threads.json"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
QUEUE_SIZE = 32
OVERLOAD_CODE = -32001


def assert_loopback(host: str) -> None:
    if host not in LOOPBACK:
        raise ValueError("bind host must be loopback")


class Outbound:
    def __init__(self, maxsize: int = QUEUE_SIZE) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=maxsize)

    def try_put(self, message: str) -> str | None:
        try:
            self._queue.put_nowait(message)
            return None
        except asyncio.QueueFull:
            return dumps_message(
                RpcNotification(
                    method="error",
                    params={"code": OVERLOAD_CODE, "message": "Server overloaded; retry later."},
                )
            )

    async def put(self, message: str) -> None:
        await self._queue.put(message)

    async def get(self) -> str:
        return await self._queue.get()


async def _client(ws: ServerConnection, store: ThreadStore, *, cfg) -> None:
    dispatcher = RpcDispatcher(store=store, cfg=cfg)
    outbound = Outbound()

    async def _pump() -> None:
        while True:
            await ws.send(await outbound.get())

    pump = asyncio.create_task(_pump())
    try:
        async for raw in ws:
            if not isinstance(raw, str):
                raw = raw.decode("utf-8")
            async for message in dispatcher.ahandle_stream(raw):
                await outbound.put(message)
    finally:
        pump.cancel()


def ready_lines(host: str, port: int, cfg: HarnessConfig | None = None) -> list[str]:
    cfg = cfg or HarnessConfig()
    model = cfg.deepseek_model or cfg.model
    key = "ok" if cfg.deepseek_api_key else "missing（.env 里填 DEEPSEEK_API_KEY）"
    return [
        "harness App Server ready 启动成功！",
        f"  listen    ws://{host}:{port}",
        f"  model     {model}  key={key}",
        "  CLI       harness   |  harness ask \"你好\"",
        "  Web       http://127.0.0.1:5173  （另开：cd frontend && npm run dev:web）",
        "  stop      Ctrl+C",
    ]


def print_ready(host: str, port: int, cfg: HarnessConfig | None = None) -> None:
    sys.stdout.write("\n".join(ready_lines(host, port, cfg)) + "\n")
    sys.stdout.flush()


async def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    assert_loopback(host)
    cfg = load_harness_config()
    store = ThreadStore(THREADS_PATH)
    async with serve(lambda ws: _client(ws, store, cfg=cfg), host, port):
        print_ready(host, port, cfg)
        await asyncio.Future()


def main() -> None:
    cfg = load_harness_config()
    parser = argparse.ArgumentParser(prog="harness-server")
    parser.add_argument("--host", default=cfg.ws_bind or DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=cfg.ws_port or DEFAULT_PORT)
    args = parser.parse_args()
    asyncio.run(run_server(args.host, args.port))


if __name__ == "__main__":
    main()
