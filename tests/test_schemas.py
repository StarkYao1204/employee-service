import pytest
from pydantic import ValidationError

from app.schemas import ChatRequest


def test_chat_request_strips_whitespace() -> None:
    """首尾空格应被清理，纯空格应被长度校验拒绝。"""

    assert ChatRequest(message="  你好  ").message == "你好"
    with pytest.raises(ValidationError):
        ChatRequest(message="   ")


def test_chat_request_rejects_overlong_message() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(message="长" * 2001)
