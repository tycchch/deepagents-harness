from types import SimpleNamespace

import pytest

from protocol.frame import RpcNotification, RpcRequest, RpcResponse, parse_message
from protocol.methods import InitializeParams, ThreadStartParams, TurnStartParams
from server.rpc import RpcDispatcher
from server.session import ThreadStore
from server.stream import AgentTurnStreamer
from server.turns import TurnStore


def _req(method: str, params: dict, id: int = 1) -> str:
    return RpcRequest(id=id, method=method, params=params).model_dump_json(exclude_none=True)


class _CheckpointedAgent:
    async def astream(self, *_args, **_kwargs):
        if False:
            yield None

    async def aget_state(self, _config):
        return SimpleNamespace(config={"configurable": {"checkpoint_id": "checkpoint-final"}})


@pytest.mark.asyncio
async def test_agent_streamer_reports_final_checkpoint_and_turn_id() -> None:
    notes = [
        note
        async for note in AgentTurnStreamer(_CheckpointedAgent()).run(
            "hello", thread_id="thread-1", turn_id="turn-1"
        )
    ]

    assert notes[0].method == "turn/started"
    assert notes[0].params["turn_id"] == "turn-1"
    assert notes[-1].method == "turn/completed"
    assert notes[-1].params == {"turn_id": "turn-1", "checkpoint_id": "checkpoint-final"}


@pytest.mark.asyncio
async def test_completed_turn_persists_its_final_checkpoint(tmp_path) -> None:
    turns = TurnStore(tmp_path / "turns.sqlite")
    dispatcher = RpcDispatcher(
        store=ThreadStore(tmp_path / "threads.json"),
        turns=turns,
        agent=_CheckpointedAgent(),
    )
    dispatcher.handle(
        _req("initialize", InitializeParams(client="desktop", cwd="E:/repo").model_dump())
    )
    start_request = _req("thread/start", ThreadStartParams(workspace="E:/repo").model_dump(), 2)
    started = parse_message(dispatcher.handle(start_request)[0])
    assert isinstance(started, RpcResponse)
    thread_id = started.result["thread_id"]

    output = await dispatcher.ahandle(
        _req("turn/start", TurnStartParams(thread_id=thread_id, text="hello").model_dump(), 3)
    )
    messages = [parse_message(raw) for raw in output]
    completed = next(
        message
        for message in messages
        if isinstance(message, RpcNotification) and message.method == "turn/completed"
    )
    turn_id = completed.params["turn_id"]
    record = turns.get(turn_id)

    assert record is not None
    assert record.thread_id == thread_id
    assert record.status == "completed"
    assert record.checkpoint_id == "checkpoint-final"
