from enum import StrEnum

from pydantic import BaseModel, Field

from protocol.methods import ApprovalDecision


class ItemType(StrEnum):
    USER_MESSAGE = "user_message"
    AGENT_MESSAGE = "agent_message"
    REASONING = "reasoning"
    COMMAND_EXECUTION = "command_execution"
    FILE_CHANGE = "file_change"
    TOOL_CALL = "tool_call"
    SKILL_USE = "skill_use"


class ItemEvent(BaseModel):
    item_id: str
    type: ItemType
    text: str | None = None
    tool: str | None = None
    path: str | None = None


class ApprovalRequestParams(BaseModel):
    request_id: str
    tool: str
    args: dict = Field(default_factory=dict)
    allowed_decisions: list[ApprovalDecision]
