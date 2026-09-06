from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from config.schema import HarnessConfig

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_DIR = Path(__file__).resolve().parent
_SECRET_KEYS = frozenset({"deepseek_api_key", "api_key", "openai_api_key"})


def load_dotenv_files() -> None:
    load_dotenv(_BACKEND_ROOT / ".env", override=False)
    load_dotenv(override=False)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"config not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"config must be a mapping: {path}")
    return _strip_secrets(raw)


def _strip_secrets(data: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        if key in _SECRET_KEYS:
            continue
        if isinstance(value, dict):
            cleaned[key] = _strip_secrets(value)
        else:
            cleaned[key] = value
    return cleaned


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _apply_env(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    sandbox = dict(out.get("sandbox") or {})
    persist = dict(out.get("persist") or {})
    client = dict(out.get("client") or {})

    if "HARNESS_MODEL" in os.environ:
        out["model"] = os.environ["HARNESS_MODEL"]
    elif "DEEPSEEK_MODEL" in os.environ:
        out["model"] = os.environ["DEEPSEEK_MODEL"]
    if "DEEPSEEK_MODEL" in os.environ:
        out["deepseek_model"] = os.environ["DEEPSEEK_MODEL"]
    if "DEEPSEEK_API_KEY" in os.environ:
        out["deepseek_api_key"] = os.environ["DEEPSEEK_API_KEY"]
    if "DEEPSEEK_BASE_URL" in os.environ:
        out["deepseek_base_url"] = os.environ["DEEPSEEK_BASE_URL"]
    if "HARNESS_WORKSPACE" in os.environ:
        out["workspace_root"] = os.environ["HARNESS_WORKSPACE"]
        client["workspace"] = os.environ["HARNESS_WORKSPACE"]
    if "HARNESS_WS_HOST" in os.environ:
        out["ws_bind"] = os.environ["HARNESS_WS_HOST"]
    if "HARNESS_WS_PORT" in os.environ:
        out["ws_port"] = int(os.environ["HARNESS_WS_PORT"])
    if "HARNESS_SANDBOX" in os.environ:
        sandbox["enabled"] = os.environ["HARNESS_SANDBOX"].lower() in {"1", "true", "yes"}
    if "HARNESS_DOCKER_HOST" in os.environ:
        sandbox["docker_host"] = os.environ["HARNESS_DOCKER_HOST"]
    if "HARNESS_CHECKPOINT_PATH" in os.environ:
        persist["checkpointer_path"] = os.environ["HARNESS_CHECKPOINT_PATH"]
    if "HARNESS_STORE_DSN" in os.environ:
        persist["store_path"] = os.environ["HARNESS_STORE_DSN"]

    out["sandbox"] = sandbox
    out["persist"] = persist
    out["client"] = client
    return out


def config_dir() -> Path:
    return _CONFIG_DIR


def load_harness_config(*, profile: str | None = None, config_path: str | Path | None = None, **overrides) -> HarnessConfig:
    load_dotenv_files()
    name = profile or os.environ.get("HARNESS_ENV") or "default"
    data = _read_yaml(_CONFIG_DIR / "default.yaml")
    if name != "default":
        overlay = _CONFIG_DIR / f"{name}.yaml"
        if overlay.is_file():
            data = _deep_merge(data, _read_yaml(overlay))
    extra = config_path or os.environ.get("HARNESS_CONFIG")
    if extra:
        data = _deep_merge(data, _read_yaml(Path(extra)))
    data = _apply_env(data)
    data = _deep_merge(data, overrides)
    return HarnessConfig.model_validate(data)
