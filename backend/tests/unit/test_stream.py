import asyncio

import pytest

from protocol.frame import RpcNotification
from server.stream import FakeTurnStreamer, TurnRunner


@pytest.mark.asyncio
async def test_fake_stream_emits_item_then_turn_completed() -> None:
    notes = [note async for note in FakeTurnStreamer().run("hi")]
    assert [n.method for n in notes[:3]] == ["item/started", "item/delta", "item/completed"]
    assert notes[-1].method == "turn/completed"
    assert any(isinstance(n, RpcNotification) and n.params.get("text") == "echo: hi" for n in notes)


@pytest.mark.asyncio
async def test_interrupt_stops_slow_turn() -> None:
    runner = TurnRunner(FakeTurnStreamer(delay_s=1.0))
    task = asyncio.create_task(runner.start("t1", "slow"))
    await asyncio.sleep(0.05)
    assert runner.is_busy("t1")
    assert runner.interrupt("t1") is True
    notes = await task
    assert any(n.method == "turn/completed" for n in notes)
    assert runner.is_busy("t1") is False


def test_map_ai_chunk_to_agent_delta() -> None:
    from langchain_core.messages import AIMessageChunk

    from server.stream import map_stream_event

    notes = map_stream_event("messages", (AIMessageChunk(content="hello"), {}))
    assert notes
    assert notes[0].method == "item/delta"
    assert notes[0].params["type"] == "agent_message"
    assert notes[0].params["text"] == "hello"


def test_map_ai_tool_call_starts_item() -> None:
    from langchain_core.messages import AIMessageChunk

    from server.stream import map_stream_event

    notes = map_stream_event(
        "messages",
        (
            AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": "ls", "args": '{"path":"/memories"}', "id": "c1", "index": 0}],
            ),
            {},
        ),
    )
    started = [n for n in notes if n.method == "item/started"]
    assert started
    assert started[0].params["type"] == "tool_call"
    assert started[0].params["tool"] == "ls"


def test_map_reasoning_block() -> None:
    from langchain_core.messages import AIMessageChunk

    from server.stream import map_stream_event

    notes = map_stream_event(
        "messages",
        (
            AIMessageChunk(content=[{"type": "thinking", "thinking": "先看记忆"}]),
            {},
        ),
    )
    assert notes[0].params["type"] == "reasoning"
    assert "记忆" in notes[0].params["text"]


def test_map_tool_message_to_command() -> None:
    from langchain_core.messages import ToolMessage

    from server.stream import map_stream_event

    notes = map_stream_event(
        "messages",
        (ToolMessage(content="ok", tool_call_id="c1", name="execute"), {}),
    )
    assert notes[0].method == "item/completed"
    assert notes[0].params["type"] == "command_execution"


@pytest.mark.asyncio
async def test_second_turn_rejected_while_busy() -> None:
    runner = TurnRunner(FakeTurnStreamer(delay_s=1.0))
    task = asyncio.create_task(runner.start("t1", "one"))
    await asyncio.sleep(0.05)
    with pytest.raises(RuntimeError, match="Turn already running"):
        await runner.start("t1", "two")
    runner.interrupt("t1")
    await task
