import json

from app.routers.sse import sse_event


def test_sse_event_encodes_event_and_data() -> None:
    """SSE 文本块必须带事件名、JSON 数据和空行分隔。"""

    block = sse_event("text_delta", {"text": "你好"})

    assert "event: text_delta" in block
    assert json.loads(block.split("data: ", 1)[1]) == {"text": "你好"}
    assert block.endswith("\n\n")
