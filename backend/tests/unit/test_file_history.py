from pathlib import Path

import pytest
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver

from agent.file_history import (
    FILE_HISTORY_CHANNEL,
    BlobStore,
    FileHistoryBackend,
    FileHistoryMiddleware,
    FileHistoryState,
)
from config.schema import HarnessConfig, SandboxConfig


class ScriptedChatModel(BaseChatModel):
    """按剧本返回消息的最小模型；只需要支持 bind_tools。"""

    script: list = []
    cursor: int = 0

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        message = self.script[min(self.cursor, len(self.script) - 1)]
        self.cursor += 1
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ANN003, ARG002
        return self

    @property
    def _llm_type(self) -> str:
        return "scripted"


def _calls(*specs: tuple[str, dict, str]) -> list[AIMessage]:
    """把 (工具名, 参数, call_id) 序列编成模型剧本。"""
    return [
        AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": cid}])
        for name, args, cid in specs
    ]


def _build_agent(tmp_path: Path, script: list):
    """返回 (app, config, blobs, workspace)。所有写操作都在图内执行。"""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    blobs = BlobStore(tmp_path / "blobs")
    backend = CompositeBackend(
        default=StateBackend(),
        routes={
            "/workspace/": FileHistoryBackend(
                FilesystemBackend(root_dir=workspace, virtual_mode=True), blobs
            )
        },
    )

    @tool
    def write_file_to(path: str, text: str) -> str:
        """写工作区文件。"""
        result = backend.write(path, text)
        return result.error or "ok"

    @tool
    def edit_file_in(path: str, old: str, new: str) -> str:
        """编辑工作区文件。"""
        result = backend.edit(path, old, new)
        return result.error or "ok"

    @tool
    def delete_file_at(path: str) -> str:
        """删除工作区文件。"""
        result = backend.delete(path)
        return result.error or "ok"

    app = create_agent(
        ScriptedChatModel(script=[*script, AIMessage(content="done")]),
        tools=[write_file_to, edit_file_in, delete_file_at],
        middleware=[FileHistoryMiddleware()],
        checkpointer=MemorySaver(),
        state_schema=FileHistoryState,
    )
    config = {"configurable": {"thread_id": "t1"}}
    return app, config, blobs, workspace


def _run(app, config) -> dict:
    app.invoke({"messages": [{"role": "user", "content": "go"}]}, config)
    return app.get_state(config).values.get(FILE_HISTORY_CHANNEL) or {}


# ----------------------------------------------------------------------
# BlobStore
# ----------------------------------------------------------------------


def test_blob_store_is_content_addressed(tmp_path: Path) -> None:
    store = BlobStore(tmp_path / "blobs")
    first = store.put(b"hello")
    second = store.put(b"hello")
    third = store.put(b"world")

    assert first == second
    assert first != third
    assert store.get(first) == b"hello"
    assert store.has(third)
    # 同一份内容只落一个文件：内容不同才各占一个
    files = [p for p in (tmp_path / "blobs").rglob("*") if p.is_file()]
    assert len(files) == 2


def test_blob_store_rejects_path_traversal(tmp_path: Path) -> None:
    store = BlobStore(tmp_path / "blobs")
    for bad in ("../../etc/passwd", "zzzz", "", "0123456789abcde", "0123456789abcdef0"):
        with pytest.raises(ValueError):
            store.path_for(bad)


def test_blob_store_leaves_no_temp_files(tmp_path: Path) -> None:
    store = BlobStore(tmp_path / "blobs")
    store.put(b"payload")
    assert list((tmp_path / "blobs").rglob("*.tmp")) == []


# ----------------------------------------------------------------------
# 写前备份语义
# ----------------------------------------------------------------------


def test_records_pre_write_content(tmp_path: Path) -> None:
    """第二次写入登记的是第一次写入后的内容。"""
    app, config, blobs, _ws = _build_agent(
        tmp_path,
        _calls(
            ("write_file_to", {"path": "/workspace/a.txt", "text": "v1"}, "c1"),
            ("write_file_to", {"path": "/workspace/a.txt", "text": "v2"}, "c2"),
        ),
    )
    records = _run(app, config)["/workspace/a.txt"]

    assert [r["seq"] for r in records] == [1, 2]
    assert records[0]["blob"] is None  # 第一次写入前文件不存在
    assert blobs.get(records[1]["blob"]) == b"v1"  # 第二次写入前的内容
    assert all(r["at"].endswith("+00:00") for r in records)


def test_empty_file_is_not_null(tmp_path: Path) -> None:
    """文件存在但是空的，与「文件不存在」必须区分开。"""
    app, config, blobs, _ws = _build_agent(
        tmp_path,
        _calls(
            ("write_file_to", {"path": "/workspace/b.txt", "text": ""}, "c1"),
            ("write_file_to", {"path": "/workspace/b.txt", "text": "later"}, "c2"),
        ),
    )
    records = _run(app, config)["/workspace/b.txt"]

    assert records[0]["blob"] is None  # 本来不存在
    assert records[1]["blob"] is not None  # 存在但为空 -> 有 blob
    assert blobs.get(records[1]["blob"]) == b""


def test_table_key_is_full_virtual_path(tmp_path: Path) -> None:
    """表的键是完整虚拟路径，不是 route backend 看到的剥离后路径。"""
    app, config, _blobs, _ws = _build_agent(
        tmp_path,
        _calls(("write_file_to", {"path": "/workspace/deep/nested.py", "text": "x"}, "c1")),
    )
    table = _run(app, config)

    assert "/workspace/deep/nested.py" in table
    assert "/deep/nested.py" not in table


def test_edit_records_previous_content(tmp_path: Path) -> None:
    app, config, blobs, _ws = _build_agent(
        tmp_path,
        _calls(
            ("write_file_to", {"path": "/workspace/c.txt", "text": "alpha"}, "c1"),
            ("edit_file_in", {"path": "/workspace/c.txt", "old": "alpha", "new": "beta"}, "c2"),
        ),
    )
    records = _run(app, config)["/workspace/c.txt"]

    assert len(records) == 2
    assert blobs.get(records[1]["blob"]) == b"alpha"


def test_delete_records_previous_content(tmp_path: Path) -> None:
    app, config, blobs, _ws = _build_agent(
        tmp_path,
        _calls(
            ("write_file_to", {"path": "/workspace/d.txt", "text": "bye"}, "c1"),
            ("delete_file_at", {"path": "/workspace/d.txt"}, "c2"),
        ),
    )
    records = _run(app, config)["/workspace/d.txt"]

    assert len(records) == 2
    assert blobs.get(records[1]["blob"]) == b"bye"


def test_failed_edit_records_nothing(tmp_path: Path) -> None:
    app, config, _blobs, _ws = _build_agent(
        tmp_path,
        _calls(
            ("write_file_to", {"path": "/workspace/e.txt", "text": "content"}, "c1"),
            ("edit_file_in", {"path": "/workspace/e.txt", "old": "nope", "new": "x"}, "c2"),
        ),
    )
    records = _run(app, config)["/workspace/e.txt"]

    assert len(records) == 1  # 只有 write 那一次，失败的 edit 不留登记


def test_dedupes_identical_versions(tmp_path: Path) -> None:
    """同一内容重复写入时，blob 只占一份盘。"""
    app, config, blobs, _ws = _build_agent(
        tmp_path,
        _calls(
            ("write_file_to", {"path": "/workspace/f.txt", "text": "same"}, "c1"),
            ("write_file_to", {"path": "/workspace/f.txt", "text": "other"}, "c2"),
            ("write_file_to", {"path": "/workspace/f.txt", "text": "same"}, "c3"),
        ),
    )
    records = _run(app, config)["/workspace/f.txt"]

    blobs_used = [r["blob"] for r in records if r["blob"]]
    assert len(blobs_used) == 2  # "same" 出现两次但只一个 id
    assert len(set(blobs_used)) == 2
    files = [p for p in blobs.root.rglob("*") if p.is_file()]
    assert len(files) == 2


# ----------------------------------------------------------------------
# 边界
# ----------------------------------------------------------------------


def test_writing_outside_graph_is_fail_soft(tmp_path: Path) -> None:
    """不在图里执行时，写入照常成功，只是不记录。"""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    backend = FileHistoryBackend(
        FilesystemBackend(root_dir=workspace, virtual_mode=True), BlobStore(tmp_path / "blobs")
    )
    result = backend.write("/a.txt", "hello")

    assert result.error is None
    assert (workspace / "a.txt").read_text(encoding="utf-8") == "hello"


def test_readonly_methods_pass_through(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.txt").write_text("alpha", encoding="utf-8")
    backend = FileHistoryBackend(
        FilesystemBackend(root_dir=workspace, virtual_mode=True), BlobStore(tmp_path / "blobs")
    )

    assert backend.read("/a.txt").error is None
    assert backend.download_files(["/a.txt"])[0].content == b"alpha"


def test_supports_delete_is_detected() -> None:
    """delete 必须显式定义，否则 deepagents 会判定成「不支持删除」。"""
    from deepagents.backends.protocol import BackendProtocol

    assert FileHistoryBackend.delete is not BackendProtocol.delete


# ----------------------------------------------------------------------
# 接线
# ----------------------------------------------------------------------


def test_build_backend_wraps_workspace_route_only_when_store_given(tmp_path: Path) -> None:
    from agent.backends import build_backend

    workspace = tmp_path / "ws"
    workspace.mkdir()
    cfg = HarnessConfig(workspace_root=str(workspace), skills_root=str(tmp_path / "skills"))

    plain = build_backend(cfg)
    assert isinstance(plain.routes["/workspace/"], FilesystemBackend)

    wrapped = build_backend(cfg, blobs=BlobStore(tmp_path / "blobs"))
    assert isinstance(wrapped, CompositeBackend)
    assert isinstance(wrapped.routes["/workspace/"], FileHistoryBackend)
    # 顶层仍是 CompositeBackend、default 仍是 StateBackend：
    # deepagents 内部多处 isinstance / _uses_state_backend 检查依赖这一点，
    # 否则 files channel 会降级成 AgentState。
    assert isinstance(wrapped.default, StateBackend)
    # 包装必须在构造时就进 routes，否则 sorted_routes 会绕过它
    routed, key = wrapped._get_backend_and_key("/workspace/a.txt")
    assert isinstance(routed, FileHistoryBackend)
    assert key == "/a.txt"  # route backend 收到的是剥掉前缀后的路径
    # 其他 route 不受影响
    assert not isinstance(wrapped.routes["/memories/"], FileHistoryBackend)


def test_sandbox_mode_skips_file_history(tmp_path: Path) -> None:
    from agent.backends import build_backend
    from agent.sandbox import DockerSandboxBackend

    workspace = tmp_path / "ws"
    workspace.mkdir()
    cfg = HarnessConfig(
        workspace_root=str(workspace),
        skills_root=str(tmp_path / "skills"),
        sandbox=SandboxConfig(enabled=True),
    )
    backend = build_backend(cfg, blobs=BlobStore(tmp_path / "blobs"))

    assert isinstance(backend.routes["/workspace/"], DockerSandboxBackend)


def test_factory_wires_middleware_and_store(tmp_path: Path) -> None:
    from unittest.mock import patch

    from agent.factory import create_harness_agent

    workspace = tmp_path / "ws"
    workspace.mkdir()
    cfg = HarnessConfig(workspace_root=str(workspace), skills_root=str(tmp_path / "skills"))
    captured: dict = {}
    with patch(
        "agent.factory.create_deep_agent",
        side_effect=lambda *a, **k: captured.update(k) or object(),
    ):
        create_harness_agent(cfg)

    kinds = [type(mw).__name__ for mw in captured["middleware"]]
    assert "FileHistoryMiddleware" in kinds
    assert isinstance(captured["backend"].routes["/workspace/"], FileHistoryBackend)
