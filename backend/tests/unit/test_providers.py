from config.providers import ProviderStore, parse_model_spec
from config.schema import HarnessConfig


def test_parse_model_spec() -> None:
    assert parse_model_spec("sonnet") == (None, "sonnet")
    assert parse_model_spec("deepseek/sonnet") == ("deepseek", "sonnet")
    assert parse_model_spec("deepseek deepseek-chat") == ("deepseek", "deepseek-chat")


def test_store_seed_select_and_redact(tmp_path) -> None:
    store = ProviderStore(tmp_path / "providers.json")
    store.seed_from_cfg(
        HarnessConfig(
            deepseek_api_key="sk-secret",
            deepseek_base_url="https://api.deepseek.com",
            deepseek_model="deepseek-chat",
        )
    )
    assert store.active_provider == "deepseek"
    assert store.active_model == "deepseek-chat"
    public = store.public()
    assert public["providers"][0]["api_key"] == "***"
    assert public["providers"][0]["has_key"] is True

    provider_id, model = store.select("sonnet")
    assert provider_id == "deepseek"
    assert model == "deepseek-chat"

    applied = store.apply(HarnessConfig())
    assert applied.deepseek_api_key == "sk-secret"
    assert applied.provider_protocol == "openai"
    assert ProviderStore(tmp_path / "providers.json").active_model == "deepseek-chat"


def test_upsert_keeps_key_and_maps_pipe_models(tmp_path) -> None:
    store = ProviderStore(tmp_path / "p.json")
    store.upsert(
        {
            "name": "Claude",
            "protocol": "anthropic",
            "base_url": "https://api.anthropic.com",
            "api_key": "sk-ant",
            "models": "claude-sonnet-4-5|Sonnet, claude-opus-4-6",
            "mapping": {"sonnet": "claude-sonnet-4-5", "opus": "claude-opus-4-6"},
        }
    )
    profile = store.providers[0]
    assert profile.protocol == "anthropic"
    assert profile.models[0].label == "Sonnet"
    store.upsert({"id": profile.id, "name": "Claude", "api_key": "***", "models": "claude-sonnet-4-5"})
    assert store.get(profile.id).api_key == "sk-ant"
    assert store.select("opus", profile.id)[1] == "claude-opus-4-6"


def test_delete_provider_switches_active(tmp_path) -> None:
    store = ProviderStore(tmp_path / "p.json")
    store.upsert({"name": "A", "api_key": "1", "models": "a1"})
    store.upsert({"name": "B", "api_key": "2", "models": "b1"})
    store.select("a1", "a")
    assert store.delete("a") is True
    assert store.active_provider == "b"
    assert store.delete("missing") is False
