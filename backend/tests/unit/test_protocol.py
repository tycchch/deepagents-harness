import json

import pytest

from protocol.events import ApprovalRequestParams, ItemType, ItemEvent
from protocol.frame import (
    RpcError,
    RpcNotification,
    RpcRequest,
    RpcResponse,
    dumps_message,
    parse_message,
)
from protocol.methods import (
    ApprovalDecision,
    ClientType,
    InitializeParams,
    InitializeResult,
    ThreadStartParams,
    TurnStartParams,
)


def test_parse_initialize_request() -> None:
    raw = dumps_message(
        RpcRequest(
            id=1,
            method="initialize",
            params=InitializeParams(
                protocol_version="0.1.0",
                client=ClientType.CLI,
                cwd="E:/work",
            ).model_dump(mode="json"),
        )
    )
    msg = parse_message(raw)
    assert isinstance(msg, RpcRequest)
    assert msg.id == 1
    assert msg.method == "initialize"
    params = InitializeParams.model_validate(msg.params)
    assert params.client is ClientType.CLI
    assert params.cwd == "E:/work"


def test_dumps_is_single_line() -> None:
    raw = dumps_message(RpcResponse(id=1, result=InitializeResult().model_dump(mode="json")))
    assert "\n" not in raw
    body = json.loads(raw)
    assert body["jsonrpc"] == "2.0"
    assert body["result"]["server_name"] == "harness"


def test_parse_item_delta_notification() -> None:
    raw = dumps_message(
        RpcNotification(
            method="item/delta",
            params=ItemEvent(
                item_id="i1",
                type=ItemType.AGENT_MESSAGE,
                text="hello",
            ).model_dump(mode="json"),
        )
    )
    msg = parse_message(raw)
    assert isinstance(msg, RpcNotification)
    assert msg.method == "item/delta"
    event = ItemEvent.model_validate(msg.params)
    assert event.text == "hello"
    assert event.type is ItemType.AGENT_MESSAGE


def test_approval_is_server_request() -> None:
    raw = dumps_message(
        RpcRequest(
            id="apr-1",
            method="approval/request",
            params=ApprovalRequestParams(
                request_id="apr-1",
                tool="execute",
                args={"command": "ls"},
                allowed_decisions=[ApprovalDecision.APPROVE, ApprovalDecision.REJECT],
            ).model_dump(mode="json"),
        )
    )
    msg = parse_message(raw)
    assert isinstance(msg, RpcRequest)
    assert msg.method == "approval/request"
    params = ApprovalRequestParams.model_validate(msg.params)
    assert params.tool == "execute"
    assert ApprovalDecision.APPROVE in params.allowed_decisions


def test_thread_and_turn_params() -> None:
    thread = ThreadStartParams(workspace="E:/repo", sandbox=False)
    turn = TurnStartParams(thread_id="t1", text="fix the bug")
    assert thread.workspace == "E:/repo"
    assert turn.text == "fix the bug"


def test_error_response() -> None:
    raw = dumps_message(RpcResponse(id=2, error=RpcError(code=-32001, message="Server overloaded; retry later.")))
    msg = parse_message(raw)
    assert isinstance(msg, RpcResponse)
    assert msg.error is not None
    assert msg.error.code == -32001


def test_parse_rejects_invalid_json() -> None:
    with pytest.raises(ValueError):
        parse_message("not-json")


def test_parse_rejects_missing_jsonrpc() -> None:
    with pytest.raises(ValueError):
        parse_message('{"id":1,"method":"initialize"}')
