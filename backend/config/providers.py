from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from config.schema import HarnessConfig

DEFAULT_PATH = Path.home() / ".harness" / "providers.json"
KEEP_KEY = "***"


class ModelItem(BaseModel):
    id: str
    label: str = ""


class ProviderProfile(BaseModel):
    id: str
    name: str
    protocol: str = "openai"
    base_url: str = ""
    api_key: str = ""
    models: list[ModelItem] = Field(default_factory=list)
    mapping: dict[str, str] = Field(default_factory=dict)

    def resolve(self, token: str) -> str:
        key = token.strip()
        if key in self.mapping:
            return self.mapping[key]
        for item in self.models:
            if item.id == key or item.label == key:
                return item.id
        return key

    def try_resolve(self, token: str) -> str | None:
        key = token.strip()
        if key in self.mapping:
            return self.mapping[key]
        for item in self.models:
            if item.id == key or item.label == key:
                return item.id
        return None

    def public(self) -> dict:
        data = self.model_dump(mode="json")
        data["has_key"] = bool(self.api_key)
        data["api_key"] = KEEP_KEY if self.api_key else ""
        return data


class ProviderStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else DEFAULT_PATH
        self.active_provider = ""
        self.active_model = ""
        self.providers: list[ProviderProfile] = []
        self._load()

    def get(self, provider_id: str) -> ProviderProfile | None:
        return next((item for item in self.providers if item.id == provider_id), None)

    def active(self) -> ProviderProfile | None:
        return self.get(self.active_provider) or (self.providers[0] if self.providers else None)

    def public(self) -> dict:
        return {
            "active_provider": self.active_provider,
            "active_model": self.active_model,
            "providers": [item.public() for item in self.providers],
        }

    def seed_from_cfg(self, cfg: HarnessConfig) -> None:
        if self.providers:
            return
        if not (cfg.deepseek_api_key or cfg.deepseek_base_url):
            return
        model = cfg.deepseek_model or cfg.model or "deepseek-chat"
        profile = ProviderProfile(
            id="deepseek",
            name="DeepSeek",
            protocol="openai",
            base_url=cfg.deepseek_base_url or "https://api.deepseek.com",
            api_key=cfg.deepseek_api_key,
            models=[ModelItem(id=model, label=model)],
            mapping={"sonnet": model, "haiku": model, "opus": model},
        )
        self.providers.append(profile)
        self.active_provider = profile.id
        self.active_model = model
        self.save()

    def upsert(self, raw: dict) -> ProviderProfile:
        incoming = dict(raw)
        provider_id = str(incoming.get("id") or "").strip() or _slug(str(incoming.get("name") or "provider"))
        existing = self.get(provider_id)
        if incoming.get("api_key") in {"", KEEP_KEY, None} and existing is not None:
            incoming["api_key"] = existing.api_key
        incoming["id"] = provider_id
        incoming["protocol"] = _protocol(
            str(incoming.get("protocol") or (existing.protocol if existing else "openai"))
        )
        models = _models(incoming.get("models"))
        incoming["models"] = models or ([item.model_dump() for item in existing.models] if existing else [])
        mapping = {
            str(key).strip(): str(value).strip()
            for key, value in dict(incoming.get("mapping") or {}).items()
            if str(key).strip() and str(value).strip()
        }
        incoming["mapping"] = mapping or (existing.mapping if existing else {})
        profile = ProviderProfile.model_validate(incoming)
        self.providers = [item for item in self.providers if item.id != profile.id] + [profile]
        if not self.active_provider:
            self.active_provider = profile.id
            self.active_model = profile.models[0].id if profile.models else self.active_model
        self.save()
        return profile

    def delete(self, provider_id: str) -> bool:
        before = len(self.providers)
        self.providers = [item for item in self.providers if item.id != provider_id]
        if len(self.providers) == before:
            return False
        if self.active_provider == provider_id:
            nxt = self.providers[0] if self.providers else None
            self.active_provider = nxt.id if nxt else ""
            self.active_model = nxt.models[0].id if nxt and nxt.models else ""
        self.save()
        return True

    def select(self, model: str, provider_id: str | None = None) -> tuple[str, str]:
        token = model.strip()
        if not token:
            raise KeyError("model required")
        if provider_id:
            profile = self.get(provider_id)
            if profile is None:
                raise KeyError("Unknown provider")
            resolved = profile.resolve(token)
            self.active_provider = profile.id
            self.active_model = resolved
            self.save()
            return profile.id, resolved
        for profile in self.providers:
            resolved = profile.try_resolve(token)
            if resolved:
                self.active_provider = profile.id
                self.active_model = resolved
                self.save()
                return profile.id, resolved
        current = self.active()
        if current is None:
            raise KeyError("Unknown model")
        resolved = current.resolve(token)
        self.active_model = resolved
        self.save()
        return current.id, resolved

    def apply(self, cfg: HarnessConfig) -> HarnessConfig:
        profile = self.active()
        if profile is None:
            return cfg
        model = self.active_model or (profile.models[0].id if profile.models else cfg.model)
        return cfg.model_copy(
            update={
                "model": model,
                "provider_protocol": profile.protocol,
                "deepseek_model": model,
                "deepseek_api_key": profile.api_key or cfg.deepseek_api_key,
                "deepseek_base_url": profile.base_url or cfg.deepseek_base_url,
            }
        )

    def _load(self) -> None:
        if not self._path.is_file():
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self.active_provider = str(raw.get("active_provider") or "")
        self.active_model = str(raw.get("active_model") or "")
        self.providers = [ProviderProfile.model_validate(item) for item in raw.get("providers") or []]

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "active_provider": self.active_provider,
            "active_model": self.active_model,
            "providers": [item.model_dump(mode="json") for item in self.providers],
        }
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_model_spec(spec: str) -> tuple[str | None, str]:
    text = spec.strip()
    if "/" in text and " " not in text.split("/", 1)[0]:
        left, right = text.split("/", 1)
        return left.strip() or None, right.strip()
    parts = text.split()
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    return None, text


def _slug(name: str) -> str:
    chars = [ch.lower() if ch.isalnum() else "-" for ch in name]
    slug = "".join(chars).strip("-")
    return slug or uuid4().hex[:8]


def _protocol(value: str) -> str:
    key = value.strip().lower()
    if key in {"anthropic", "claude", "native"}:
        return "anthropic"
    return "openai"


def _models(raw: object) -> list[dict]:
    if not raw:
        return []
    if isinstance(raw, str):
        items: list[dict] = []
        for part in raw.replace(";", ",").split(","):
            token = part.strip()
            if not token:
                continue
            if "|" in token:
                mid, label = token.split("|", 1)
                items.append({"id": mid.strip(), "label": label.strip() or mid.strip()})
            else:
                items.append({"id": token, "label": token})
        return items
    out: list[dict] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append({"id": item.strip(), "label": item.strip()})
        elif isinstance(item, dict) and item.get("id"):
            out.append({"id": str(item["id"]), "label": str(item.get("label") or item["id"])})
    return out
