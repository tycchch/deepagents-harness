from config.load import load_harness_config
from config.schema import ClientConfig, HarnessConfig, PersistConfig, SandboxConfig


def test_load_deepseek_from_env(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    cfg = load_harness_config(profile="default")
    assert cfg.deepseek_api_key == "sk-test"
    assert cfg.deepseek_base_url == "https://api.deepseek.com"
    assert cfg.deepseek_model == "deepseek-chat"


def test_default_yaml_local_disk(monkeypatch) -> None:
    monkeypatch.delenv("HARNESS_SANDBOX", raising=False)
    monkeypatch.delenv("HARNESS_CONFIG", raising=False)
    cfg = load_harness_config(profile="default")
    assert cfg.hitl is True
    assert cfg.sandbox.enabled is False
    assert cfg.sandbox.workdir == "/workspace"
    assert cfg.persist.checkpointer == "memory"
    assert cfg.persist.store == "memory"
    assert cfg.server_transport == "ws"
    assert isinstance(cfg.client, ClientConfig)


def test_production_overlay_enables_sandbox_and_sqlite(monkeypatch) -> None:
    monkeypatch.delenv("HARNESS_SANDBOX", raising=False)
    monkeypatch.delenv("HARNESS_CONFIG", raising=False)
    cfg = load_harness_config(profile="production")
    assert cfg.sandbox.enabled is True
    assert cfg.sandbox.network == "none"
    assert cfg.persist.checkpointer == "sqlite"
    assert cfg.persist.store == "sqlite"
    assert cfg.persist.checkpointer_path.endswith("checkpoints.sqlite")
    assert cfg.hitl is True
    assert cfg.sandbox.image == "python:3.12-slim"


def test_env_overrides_yaml(monkeypatch) -> None:
    monkeypatch.setenv("HARNESS_WORKSPACE", "E:/ws")
    monkeypatch.setenv("HARNESS_SANDBOX", "true")
    cfg = load_harness_config(profile="default")
    assert cfg.workspace_root == "E:/ws"
    assert cfg.client.workspace == "E:/ws"
    assert cfg.sandbox.enabled is True


def test_yaml_cannot_inject_secrets(tmp_path) -> None:
    leaked = tmp_path / "leak.yaml"
    leaked.write_text("deepseek_api_key: sk-from-yaml\nhitl: false\n", encoding="utf-8")
    cfg = load_harness_config(profile="default", config_path=leaked)
    assert cfg.hitl is False
    assert cfg.deepseek_api_key != "sk-from-yaml"


def test_build_chat_model_uses_openai_compat() -> None:
    from unittest.mock import MagicMock, patch

    from agent.factory import build_chat_model

    cfg = HarnessConfig(
        deepseek_api_key="sk-test",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-chat",
    )
    fake = MagicMock()
    with patch("langchain_openai.ChatOpenAI", return_value=fake) as ctor:
        model = build_chat_model(cfg)
    assert model is fake
    kwargs = ctor.call_args.kwargs
    assert kwargs["model"] == "deepseek-chat"
    assert kwargs["api_key"] == "sk-test"
    assert kwargs["base_url"].rstrip("/").endswith("/v1")


def test_build_chat_model_anthropic() -> None:
    from unittest.mock import MagicMock, patch

    from agent.factory import build_chat_model

    cfg = HarnessConfig(
        provider_protocol="anthropic",
        deepseek_api_key="sk-ant",
        deepseek_base_url="https://api.deepseek.com/anthropic",
        deepseek_model="deepseek-chat",
    )
    fake = MagicMock()
    with patch("langchain_anthropic.ChatAnthropic", return_value=fake) as ctor:
        model = build_chat_model(cfg)
    assert model is fake
    kwargs = ctor.call_args.kwargs
    assert kwargs["model"] == "deepseek-chat"
    assert kwargs["api_key"] == "sk-ant"
    assert kwargs["base_url"] == "https://api.deepseek.com/anthropic"


def test_build_chat_model_without_key_returns_string() -> None:
    from agent.factory import build_chat_model

    model = build_chat_model(HarnessConfig(deepseek_api_key="", model="openai:gpt-4o-mini"))
    assert model == "openai:gpt-4o-mini"


def test_persist_memory_builders() -> None:
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.store.memory import InMemoryStore

    from config.persist import build_checkpointer, build_store

    cfg = HarnessConfig(persist=PersistConfig(checkpointer="memory", store="memory"))
    assert isinstance(build_checkpointer(cfg), MemorySaver)
    assert isinstance(build_store(cfg), InMemoryStore)


def test_persist_sqlite_requires_extra() -> None:
    import pytest

    from config.persist import build_checkpointer

    cfg = HarnessConfig(
        persist=PersistConfig(checkpointer="sqlite", checkpointer_path="~/.harness/x.sqlite"),
    )
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match="langgraph-checkpoint-sqlite"):
            build_checkpointer(cfg)
    else:
        from langgraph.checkpoint.base import BaseCheckpointSaver

        saver = build_checkpointer(cfg)
        assert isinstance(saver, BaseCheckpointSaver)


def test_schema_exports() -> None:
    assert SandboxConfig().enabled is False
    assert ClientConfig().ws_url.startswith("ws://")
