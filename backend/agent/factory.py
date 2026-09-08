from deepagents import create_deep_agent

from agent.backends import build_backend
from agent.permissions import build_interrupt_on, build_permissions
from agent.prompts import build_system_prompt
from agent.tools import build_tools
from config.persist import build_checkpointer, build_store
from config.schema import HarnessConfig


def build_chat_model(cfg: HarnessConfig):
    key = cfg.deepseek_api_key
    model = cfg.deepseek_model or cfg.model
    if not key:
        return cfg.model
    protocol = (cfg.provider_protocol or "openai").lower()
    if protocol == "anthropic":
        from langchain_anthropic import ChatAnthropic

        kwargs: dict = {"model": model, "api_key": key}
        base = (cfg.deepseek_base_url or "").rstrip("/")
        if base:
            kwargs["base_url"] = base
        return ChatAnthropic(**kwargs)

    from langchain_openai import ChatOpenAI

    base = (cfg.deepseek_base_url or "https://api.openai.com").rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return ChatOpenAI(model=model, api_key=key, base_url=base)


def create_harness_agent(
    cfg: HarnessConfig,
    *,
    store=None,
    checkpointer=None,
    context=None,
):
    store = store or build_store(cfg)
    checkpointer = checkpointer or build_checkpointer(cfg)
    return create_deep_agent(
        model=build_chat_model(cfg),
        system_prompt=build_system_prompt(cfg.workspace_root),
        backend=build_backend(cfg, context=context),
        store=store,
        skills=["/skills/shared/", "/skills/personal/"],
        memory=["/memories/AGENTS.md"] if cfg.memory_enabled else None,
        permissions=build_permissions(cfg),
        tools=build_tools(cfg),
        interrupt_on=build_interrupt_on(cfg),
        checkpointer=checkpointer,
        name="harness",
    )
