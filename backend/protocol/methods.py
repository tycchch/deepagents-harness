from enum import StrEnum

from pydantic import BaseModel, Field

PROTOCOL_VERSION = "0.1.0"


class ClientType(StrEnum):
    CLI = "cli"
    DESKTOP = "desktop"


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"
    RESPOND = "respond"


class InitializeParams(BaseModel):
    protocol_version: str = PROTOCOL_VERSION
    client: ClientType
    cwd: str


class InitializeResult(BaseModel):
    protocol_version: str = PROTOCOL_VERSION
    server_name: str = "harness"


class ThreadStartParams(BaseModel):
    workspace: str
    sandbox: bool = False


class ThreadInfo(BaseModel):
    thread_id: str
    workspace: str
    title: str = ""
    updated_at: str = ""


class ThreadResumeParams(BaseModel):
    thread_id: str


class TurnStartParams(BaseModel):
    thread_id: str
    text: str


class TurnInterruptParams(BaseModel):
    thread_id: str


class ApprovalResolveParams(BaseModel):
    request_id: str
    decision: ApprovalDecision
    edited_args: dict | None = None
    message: str | None = None


class SkillsReadParams(BaseModel):
    path: str


class SkillsWriteParams(BaseModel):
    path: str
    content: str


class ConfigSetParams(BaseModel):
    values: dict = Field(default_factory=dict)
