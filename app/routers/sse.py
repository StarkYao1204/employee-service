"""SSE 文本块编码工具。"""

import json
from typing import Any


def sse_event(event: str, data: dict[str, Any]) -> str:
    """把事件名称和字典编码成一个完整的 SSE 文本块。"""

    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
