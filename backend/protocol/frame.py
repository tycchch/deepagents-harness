from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class RpcError(BaseModel):
    code: int
    message: str
    data: Any | None = None


class RpcRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class RpcNotification(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class RpcResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str
    result: Any | None = None
    error: RpcError | None = None

    @model_validator(mode="after")
    def _result_or_error(self) -> RpcResponse:
        if self.result is None and self.error is None:
            raise ValueError("RpcResponse needs result or error")
        return self


RpcMessage = RpcRequest | RpcNotification | RpcResponse


def dumps_message(message: RpcMessage) -> str:
    return message.model_dump_json(exclude_none=True)


def parse_message(raw: str) -> RpcMessage:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid json") from exc
    if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
        raise ValueError("missing or invalid jsonrpc")
    if "method" in data:
        if "id" in data:
            return RpcRequest.model_validate(data)
        return RpcNotification.model_validate(data)
    if "id" in data:
        return RpcResponse.model_validate(data)
    raise ValueError("unrecognized rpc message")
