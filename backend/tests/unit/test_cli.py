import pytest
from langchain_core.messages import AIMessageChunk

from protocol.frame import RpcRequest, dumps_message, parse_message
from protocol.methods import InitializeParams, ThreadStartParams, TurnStartParams
from server.rpc import RpcDispatcher


class _FakeAgent:
    async def astream(self, *_args, **_kwargs):
        yield ("messages", (AIMessageChunk(content="from-agent"), {}))


def _req(method: str, params: dict, id: int | str = 1) -> str:
    return RpcRequest(id=id, method=method, params=params).model_dump_json(exclude_none=True)


def _init(disp: RpcDispatcher) -> None:
    disp.handle(_req("initialize", InitializeParams(client="cli", cwd="E:/repo").model_dump(mode="json")))


@pytest.mark.asyncio
async def test_ahandle_turn_uses_agent() -> None:
    disp = RpcDispatcher(agent=_FakeAgent())
    _init(disp)
    started = parse_message(
        disp.handle(_req("thread/start", ThreadStartParams(workspace="E:/repo").model_dump(), id=2))[0]
    )
    thread_id = started.result["thread_id"]
    messages = [
        parse_message(raw)
        for raw in await disp.ahandle(
            _req("turn/start", TurnStartParams(thread_id=thread_id, text="hi").model_dump(), id=3)
        )
    ]
    texts = [getattr(m, "params", {}).get("text") for m in messages if getattr(m, "method", "") == "item/delta"]
    assert "from-agent" in texts


def test_banner_renders_wordmark() -> None:
    from io import StringIO

    from rich.console import Console

    from harness_cli.banner import render_banner

    buf = StringIO()
    console = Console(file=buf, width=88, force_terminal=True, color_system=None)
    render_banner(
        console,
        workspace="E:/repo",
        host="127.0.0.1",
        port=8765,
        thread_id="abc-123",
        resumed=False,
    )
    text = buf.getvalue()
    assert "HARNESS" in text or "██" in text
    assert "E:/repo" in text
    assert "ws://127.0.0.1:8765" in text
    assert "abc-123" in text


def test_same_workspace_normalizes() -> None:
    from pathlib import Path

    from harness_cli.tui import _same_workspace

    root = Path.cwd()
    assert _same_workspace(str(root), str(root / "."))


def test_client_builds_request_line() -> None:
    from harness_cli.client import next_request

    raw, req_id = next_request("initialize", {"client": "cli", "cwd": "/tmp"}, req_id=7)
    msg = parse_message(raw)
    assert isinstance(msg, RpcRequest)
    assert msg.id == 7
    assert msg.method == "initialize"
    assert dumps_message(msg)
