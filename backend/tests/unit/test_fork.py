from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.memory import MemorySaver

from protocol.frame import RpcRequest, RpcResponse, parse_message
from protocol.methods import InitializeParams
from server.checkpoints import clone_checkpoint
from server.rpc import RpcDispatcher
from server.session import ThreadStore
from server.turns import TurnStore
from server.workspaces import WorkspaceSnapshotStore


async def _seed_checkpoint(saver, thread_id: str, message: str) -> str:
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"messages": [message]}
    checkpoint["channel_versions"] = {"messages": "1"}
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    saved = await saver.aput(config, checkpoint, {"step": 1, "source": "loop"}, {"messages": "1"})
    return str(saved["configurable"]["checkpoint_id"])


async def test_clone_checkpoint_creates_independent_thread_root() -> None:
    source = MemorySaver()
    target = MemorySaver()
    source_id = await _seed_checkpoint(source, "source", "hello")

    target_id = await clone_checkpoint(
        source,
        target,
        source_thread_id="source",
        source_checkpoint_id=source_id,
        target_thread_id="target",
    )
    cloned = await target.aget_tuple(
        {"configurable": {"thread_id": "target", "checkpoint_ns": ""}}
    )

    assert cloned is not None
    assert target_id != source_id
    assert cloned.checkpoint["channel_values"]["messages"] == ["hello"]
    assert cloned.metadata["forked_from_thread_id"] == "source"


def test_workspace_snapshot_restores_selected_content(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("version one", encoding="utf-8")
    (source / ".venv").mkdir()
    (source / ".venv" / "ignored.txt").write_text("large", encoding="utf-8")
    snapshots = WorkspaceSnapshotStore(tmp_path / "snapshots")
    manifest_id = snapshots.capture(source)
    assert manifest_id is not None

    (source / "a.txt").write_text("version two", encoding="utf-8")
    destination = tmp_path / "fork"
    snapshots.materialize(manifest_id, destination)

    assert (destination / "a.txt").read_text(encoding="utf-8") == "version one"
    assert not (destination / ".venv").exists()


def test_thread_and_turn_metadata_describe_fork(tmp_path) -> None:
    threads = ThreadStore(tmp_path / "threads.json")
    turns = TurnStore(tmp_path / "turns.sqlite")
    parent = threads.start(str(tmp_path / "source"))
    turn = turns.start(parent.thread_id)
    turns.finish(
        turn.turn_id,
        status="completed",
        checkpoint_id="checkpoint-1",
        workspace_manifest_id="manifest-1",
    )

    child = threads.fork(
        parent.thread_id,
        turn.turn_id,
        str(tmp_path / "fork"),
    )

    assert child is not None
    assert child.parent_thread_id == parent.thread_id
    assert child.forked_from_turn_id == turn.turn_id
    assert child.root_thread_id == parent.thread_id
    saved_turn = TurnStore(tmp_path / "turns.sqlite").get(turn.turn_id)
    assert saved_turn is not None
    assert saved_turn.workspace_manifest_id == "manifest-1"


async def test_thread_fork_rpc_clones_checkpoint_and_historical_workspace(tmp_path) -> None:
    source_workspace = tmp_path / "source"
    source_workspace.mkdir()
    (source_workspace / "state.txt").write_text("at fork point", encoding="utf-8")
    threads = ThreadStore(tmp_path / "threads.json")
    turns = TurnStore(tmp_path / "turns.sqlite")
    snapshots = WorkspaceSnapshotStore(tmp_path / "snapshots")
    parent = threads.start(str(source_workspace))
    manifest_id = snapshots.capture(source_workspace)
    assert manifest_id is not None

    saver = MemorySaver()
    checkpoint_id = await _seed_checkpoint(saver, parent.thread_id, "history at fork")
    turn = turns.start(parent.thread_id)
    turns.finish(
        turn.turn_id,
        status="completed",
        checkpoint_id=checkpoint_id,
        workspace_manifest_id=manifest_id,
    )
    (source_workspace / "state.txt").write_text("newer parent state", encoding="utf-8")

    agent = type("Agent", (), {"checkpointer": saver})()
    dispatcher = RpcDispatcher(
        store=threads,
        turns=turns,
        workspaces=snapshots,
        agent=agent,
    )
    initialize = RpcRequest(
        id=1,
        method="initialize",
        params=InitializeParams(client="desktop", cwd=str(source_workspace)).model_dump(),
    )
    dispatcher.handle(initialize.model_dump_json())
    request = RpcRequest(
        id=2,
        method="thread/fork",
        params={"thread_id": parent.thread_id, "turn_id": turn.turn_id},
    )

    response = parse_message((await dispatcher.ahandle(request.model_dump_json()))[-1])
    assert isinstance(response, RpcResponse)
    assert response.error is None
    child_id = response.result["thread_id"]
    child_workspace = response.result["workspace"]
    assert response.result["parent_thread_id"] == parent.thread_id
    assert response.result["forked_from_turn_id"] == turn.turn_id
    assert (tmp_path / "snapshots" / "workspaces" / child_id / "state.txt").read_text(
        encoding="utf-8"
    ) == "at fork point"
    assert child_workspace.endswith(child_id)

    cloned = await saver.aget_tuple(
        {"configurable": {"thread_id": child_id, "checkpoint_ns": ""}}
    )
    assert cloned is not None
    assert cloned.checkpoint["channel_values"]["messages"] == ["history at fork"]
