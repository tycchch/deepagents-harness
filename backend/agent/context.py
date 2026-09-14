from __future__ import annotations

from typing import Any

from deepagents.middleware.summarization import SummarizationMiddleware


def should_compact(tokens: int, limit: int) -> bool:
    return tokens >= limit


def summarization_settings(limit: int) -> dict[str, Any]:
    keep = max(1, limit // 10)
    return {
        "trigger": ("tokens", limit),
        "keep": ("tokens", keep),
        "truncate_args_settings": {
            "trigger": ("tokens", max(1, int(limit * 0.85))),
            "keep": ("tokens", keep),
        },
    }


def model_profile(limit: int) -> dict[str, int]:
    return {"max_input_tokens": limit}


def build_summarization_middleware(model, backend, *, limit: int) -> SummarizationMiddleware:
    return SummarizationMiddleware(model=model, backend=backend, **summarization_settings(limit))
