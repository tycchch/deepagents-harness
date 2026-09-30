"""端到端：真实 `create_harness_agent` + deepagents 自带的 FilesystemMiddleware。

单元测试里是直接调 backend 方法；这里验证真实链路——模型的 write_file 工具调用经
FilesystemMiddleware 路由到被包装的 /workspace/ route，备份登记确实落到 graph state。
"""

from pathlib import Path
from unittest.mock import patch

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent.file_history import FILE_HISTORY_CHANNEL
from config.schema import HarnessConfig


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


def _write(path: str, text: str, call_id: str) -> AIMessage:
    args = {"file_path": path, "content": text}
    return AIMessage(content="", tool_calls=[{"name": "write_file", "args": args, "id": call_id}])


def test_file_history_records_through_real_filesystem_middleware(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    cfg = HarnessConfig(
        workspace_root=str(workspace),
        skills_root=str(tmp_path / "skills"),
        memories_root=str(tmp_path / "memories"),
        deepseek_api_key="sk-test",
    )
    script = [
        _write("/workspace/e2e.txt", "v1", "c1"),
        _write("/workspace/e2e.txt", "v2", "c2"),
        AIMessage(content="done"),
    ]

    with patch("agent.factory.build_chat_model", return_value=ScriptedChatModel(script=script)):
        from agent.factory import create_harness_agent

        agent = create_harness_agent(cfg)

    config = {"configurable": {"thread_id": "e2e-thread"}}
    agent.invoke({"messages": [{"role": "user", "content": "go"}]}, config)
    values = agent.get_state(config).values

    # 对话本身没被破坏
    assert values["messages"]
    # 工作区文件确实被写了
    assert (workspace / "e2e.txt").read_text(encoding="utf-8") == "v2"

    records = values[FILE_HISTORY_CHANNEL]["/workspace/e2e.txt"]
    assert [r["seq"] for r in records] == [1, 2]
    assert records[0]["blob"] is None  # 首次写入前该文件不存在
    assert records[1]["blob"] is not None

    # blob 里存的是「写入之前」的内容
    blob = tmp_path / "file_history" / records[1]["blob"][:2] / records[1]["blob"]
    assert blob.read_bytes() == b"v1"


def test_file_history_accumulates_across_turns(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    cfg = HarnessConfig(
        workspace_root=str(workspace),
        skills_root=str(tmp_path / "skills"),
        memories_root=str(tmp_path / "memories"),
        deepseek_api_key="sk-test",
    )
    # 一份合并剧本：模型游标跨轮次推进，第一轮消耗前两条，第二轮消耗后两条。
    script = [
        _write("/workspace/t.txt", "one", "c1"),
        AIMessage(content="done"),
        _write("/workspace/t.txt", "two", "c2"),
        AIMessage(content="done"),
    ]

    with patch("agent.factory.build_chat_model", return_value=ScriptedChatModel(script=script)):
        from agent.factory import create_harness_agent

        agent = create_harness_agent(cfg)

    config = {"configurable": {"thread_id": "multi-turn"}}
    agent.invoke({"messages": [{"role": "user", "content": "go"}]}, config)
    agent.invoke({"messages": [{"role": "user", "content": "again"}]}, config)

    records = agent.get_state(config).values[FILE_HISTORY_CHANNEL]["/workspace/t.txt"]
    assert [r["seq"] for r in records] == [1, 2]
    assert records[0]["blob"] is None
    # 第二轮写入前的内容是第一轮写下的 "one"
    blob = tmp_path / "file_history" / records[1]["blob"][:2] / records[1]["blob"]
    assert blob.read_bytes() == b"one"
