from pydantic import BaseModel, Field


class ClientConfig(BaseModel):
    workspace: str = ""
    ws_url: str = "ws://127.0.0.1:8765"


class SandboxConfig(BaseModel):
    enabled: bool = False
    image: str = "python:3.12-slim"
    network: str = "none"
    workdir: str = "/workspace"
    timeout_s: int = 60
    docker_host: str = ""


class PersistConfig(BaseModel):
    checkpointer: str = "memory"
    store: str = "memory"
    checkpointer_path: str = ""
    store_path: str = ""


class HarnessConfig(BaseModel):
    model: str = "deepseek-chat"
    provider_protocol: str = "openai"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    workspace_root: str = ""
    skills_root: str = ""
    memories_root: str = ""
    memory_enabled: bool = True
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    persist: PersistConfig = Field(default_factory=PersistConfig)
    client: ClientConfig = Field(default_factory=ClientConfig)
    server_transport: str = "ws"
    ws_bind: str = "127.0.0.1"
    ws_port: int = 8765
    hitl: bool = True
