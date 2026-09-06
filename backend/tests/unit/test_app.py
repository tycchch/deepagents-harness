import asyncio

import pytest

from protocol.frame import parse_message
from config.schema import HarnessConfig
from server.app import Outbound, assert_loopback, ready_lines


def test_reject_non_loopback() -> None:
    with pytest.raises(ValueError, match="loopback"):
        assert_loopback("0.0.0.0")


def test_allow_loopback() -> None:
    assert_loopback("127.0.0.1")
    assert_loopback("localhost")


def test_outbound_overflow_emits_overload() -> None:
    out = Outbound(maxsize=1)
    assert out.try_put("one") is None
    dumped = out.try_put("two")
    assert dumped is not None
    msg = parse_message(dumped)
    assert msg.method == "error"
    assert msg.params["code"] == -32001


@pytest.mark.asyncio
async def test_outbound_put_backpressures() -> None:
    out = Outbound(maxsize=1)
    await out.put("one")

    async def _take() -> str:
        await asyncio.sleep(0.01)
        return await out.get()

    taker = asyncio.create_task(_take())
    await out.put("two")
    assert await taker == "one"
    assert await out.get() == "two"


def test_ready_lines_after_bind() -> None:
    lines = ready_lines("127.0.0.1", 8765, HarnessConfig(deepseek_api_key="", deepseek_model="deepseek-chat"))
    text = "\n".join(lines)
    assert "ready" in text
    assert "ws://127.0.0.1:8765" in text
    assert "harness ask" in text
    assert "127.0.0.1:5173" in text
    assert "key=missing" in text
    assert "sk-" not in text
