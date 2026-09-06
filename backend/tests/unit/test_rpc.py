import pytest

from protocol.frame import RpcNotification, RpcRequest, RpcResponse, parse_message
from protocol.methods import (
    ApprovalResolveParams,
    InitializeParams,
    SkillsWriteParams,
    ThreadResumeParams,
    ThreadStartParams,
    TurnInterruptParams,
    TurnStartParams,
)
from server.rpc import RpcDispatcher
from server.session import ThreadStore


def _req(method: str, params: dict, id: int | str = 1) -> str:
    return RpcRequest(id=id, method=method, params=params).model_dump_json(exclude_none=True)


def test_rejects_before_initialize() -> None:
    disp = RpcDispatcher()
    out = disp.handle(_req("thread/start", ThreadStartParams(workspace="E:/repo").model_dump()))
    msg = parse_message(out[0])
    assert isinstance(msg, RpcResponse)
    assert msg.error is not None
    assert msg.error.message == "Not initialized"


def test_initialize_then_thread_start() -> None:
    disp = RpcDispatcher()
    init = disp.handle(
        _req(
            "initialize",
            InitializeParams(client="cli", cwd="E:/repo").model_dump(mode="json"),
        )
    )
    ready = parse_message(init[0])
    assert isinstance(ready, RpcResponse)
    assert ready.error is None
    assert ready.result["server_name"] == "harness"

    started = disp.handle(_req("thread/start", ThreadStartParams(workspace="E:/repo").model_dump(), id=2))
    info = parse_message(started[0])
    assert isinstance(info, RpcResponse)
    from server.session import normalize_workspace

    assert normalize_workspace(info.result["workspace"]) == normalize_workspace("E:/repo")
    assert info.result["thread_id"]


def test_fake_turn_emits_agent_message() -> None:
    disp = RpcDispatcher()
    disp.handle(
        _req(
            "initialize",
            InitializeParams(client="cli", cwd="E:/repo").model_dump(mode="json"),
        )
    )
    thread = disp.handle(_req("thread/start", ThreadStartParams(workspace="E:/repo").model_dump(), id=2))
    thread_id = parse_message(thread[0]).result["thread_id"]

    messages = [
        parse_message(raw)
        for raw in disp.handle(_req("turn/start", TurnStartParams(thread_id=thread_id, text="hi").model_dump(), id=3))
    ]
    notes = [m for m in messages if isinstance(m, RpcNotification)]
    assert any(m.method == "item/delta" and m.params.get("text") for m in notes)
    assert any(m.method == "turn/completed" for m in notes)
    reply = next(m for m in messages if isinstance(m, RpcResponse))
    assert reply.id == 3
    assert reply.error is None


def _init(disp: RpcDispatcher) -> None:
    disp.handle(
        _req("initialize", InitializeParams(client="cli", cwd="E:/repo").model_dump(mode="json"))
    )


def test_thread_list_resume_archive(tmp_path) -> None:
    disp = RpcDispatcher(store=ThreadStore(tmp_path / "threads.json"))
    _init(disp)
    started = parse_message(
        disp.handle(_req("thread/start", ThreadStartParams(workspace="E:/repo").model_dump(), id=2))[0]
    )
    thread_id = started.result["thread_id"]

    listed = parse_message(disp.handle(_req("thread/list", {}, id=3))[0])
    assert listed.result["threads"][0]["thread_id"] == thread_id

    resumed = parse_message(
        disp.handle(_req("thread/resume", ThreadResumeParams(thread_id=thread_id).model_dump(), id=4))[0]
    )
    from server.session import normalize_workspace

    assert normalize_workspace(resumed.result["workspace"]) == normalize_workspace("E:/repo")

    disp.handle(_req("thread/archive", ThreadResumeParams(thread_id=thread_id).model_dump(), id=5))
    listed = parse_message(disp.handle(_req("thread/list", {}, id=6))[0])
    assert listed.result["threads"] == []
    listed = parse_message(disp.handle(_req("thread/list", {"include_archived": True}, id=7))[0])
    assert listed.result["threads"][0]["archived"] is True
    disp.handle(_req("thread/unarchive", ThreadResumeParams(thread_id=thread_id).model_dump(), id=8))
    listed = parse_message(disp.handle(_req("thread/list", {}, id=9))[0])
    assert listed.result["threads"][0]["thread_id"] == thread_id


def test_rename_thread(tmp_path) -> None:
    disp = RpcDispatcher(store=ThreadStore(tmp_path / "threads.json"))
    _init(disp)
    started = parse_message(
        disp.handle(_req("thread/start", ThreadStartParams(workspace="E:/repo").model_dump(), id=2))[0]
    )
    thread_id = started.result["thread_id"]

    renamed = parse_message(
        disp.handle(_req("thread/rename", {"thread_id": thread_id, "title": "重构计划"}, id=3))[0]
    )
    assert renamed.result["title"] == "重构计划"
    listed = parse_message(disp.handle(_req("thread/list", {}, id=4))[0])
    assert listed.result["threads"][0]["title"] == "重构计划"

    missing = parse_message(disp.handle(_req("thread/rename", {"thread_id": "nope", "title": "x"}, id=5))[0])
    assert missing.error is not None


@pytest.mark.asyncio
async def test_delete_thread(tmp_path) -> None:
    disp = RpcDispatcher(store=ThreadStore(tmp_path / "threads.json"))
    _init(disp)
    started = parse_message(
        disp.handle(_req("thread/start", ThreadStartParams(workspace="E:/repo").model_dump(), id=2))[0]
    )
    thread_id = started.result["thread_id"]

    reply = parse_message((await disp.ahandle(_req("thread/delete", {"thread_id": thread_id}, id=3)))[-1])
    assert reply.error is None
    listed = parse_message(disp.handle(_req("thread/list", {"include_archived": True}, id=4))[0])
    assert listed.result["threads"] == []

    again = parse_message((await disp.ahandle(_req("thread/delete", {"thread_id": thread_id}, id=5)))[-1])
    assert again.error is not None


def test_set_workspace_on_existing_thread(tmp_path) -> None:
    disp = RpcDispatcher(store=ThreadStore(tmp_path / "threads.json"))
    _init(disp)
    started = parse_message(
        disp.handle(_req("thread/start", ThreadStartParams(workspace="E:/repo").model_dump(), id=2))[0]
    )
    thread_id = started.result["thread_id"]
    moved = parse_message(
        disp.handle(
            _req("thread/set_workspace", {"thread_id": thread_id, "workspace": "E:/other"}, id=3)
        )[0]
    )
    from server.session import normalize_workspace

    assert normalize_workspace(moved.result["workspace"]) == normalize_workspace("E:/other")
    listed = parse_message(disp.handle(_req("thread/list", {}, id=4))[0])
    assert normalize_workspace(listed.result["threads"][0]["workspace"]) == normalize_workspace("E:/other")


def test_shared_store_across_dispatchers(tmp_path) -> None:
    store = ThreadStore(tmp_path / "threads.json")
    a = RpcDispatcher(store=store)
    b = RpcDispatcher(store=store)
    _init(a)
    _init(b)
    started = parse_message(
        a.handle(_req("thread/start", ThreadStartParams(workspace="E:/repo").model_dump(), id=2))[0]
    )
    listed = parse_message(b.handle(_req("thread/list", {}, id=3))[0])
    assert listed.result["threads"][0]["thread_id"] == started.result["thread_id"]


def test_skills_personal_write_only(tmp_path) -> None:
    disp = RpcDispatcher(skills_root=tmp_path)
    _init(disp)
    denied = parse_message(
        disp.handle(
            _req(
                "skills/write",
                SkillsWriteParams(path="/skills/shared/x/SKILL.md", content="# no").model_dump(),
                id=2,
            )
        )[0]
    )
    assert denied.error is not None

    ok = parse_message(
        disp.handle(
            _req(
                "skills/write",
                SkillsWriteParams(path="/skills/personal/demo/SKILL.md", content="# demo").model_dump(),
                id=3,
            )
        )[0]
    )
    assert ok.error is None
    listed = parse_message(disp.handle(_req("skills/list", {}, id=4))[0])
    names = {s["name"] for s in listed.result["skills"]}
    assert "demo" in names


def test_config_get_set() -> None:
    disp = RpcDispatcher()
    _init(disp)
    got = parse_message(disp.handle(_req("config/get", {}, id=2))[0])
    assert got.result["config"]["server_transport"] == "ws"
    disp.handle(_req("config/set", {"values": {"model": "test-model"}}, id=3))
    got = parse_message(disp.handle(_req("config/get", {}, id=4))[0])
    assert got.result["config"]["model"] == "test-model"


def test_approval_resolve_unknown() -> None:
    disp = RpcDispatcher()
    _init(disp)
    msg = parse_message(
        disp.handle(
            _req(
                "approval/resolve",
                ApprovalResolveParams(request_id="nope", decision="reject").model_dump(mode="json"),
                id=2,
            )
        )[0]
    )
    assert msg.error is not None


def test_turn_interrupt_unknown_thread() -> None:
    disp = RpcDispatcher()
    _init(disp)
    msg = parse_message(
        disp.handle(_req("turn/interrupt", TurnInterruptParams(thread_id="missing").model_dump(), id=2))[0]
    )
    assert msg.error is not None
