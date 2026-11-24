"""Agent Web API 的请求与响应模型。"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RequestModel(BaseModel):
    """请求模型统一去掉字符串首尾空格。"""

    # 在 Field 的长度校验前清理首尾空格，避免纯空格被当作有效输入。
    model_config = ConfigDict(str_strip_whitespace=True)


class TokenResponse(BaseModel):
    """密码验证成功后返回的 Bearer Token。"""

    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    """允许页面展示的当前用户信息。"""

    user_id: str
    username: str
    display_name: str
    role: str
    department_id: str


class ThreadResponse(BaseModel):
    """当前用户可以选择的对话 Thread。"""

    thread_id: str
    created_at: datetime


class HistoryMessage(BaseModel):
    """允许前端展示的一条历史消息。"""

    role: Literal["user", "assistant"]
    content: str


class ThreadHistoryResponse(BaseModel):
    """历史消息，以及可能尚未处理的人工确认。"""

    messages: list[HistoryMessage] = Field(default_factory=list)
    needs_confirmation: bool = False
    confirmation: dict[str, Any] | None = None


class ChatRequest(RequestModel):
    """浏览器发送一轮对话时提交的数据。"""

    # message 是本轮新增的用户消息，不需要由浏览器重复提交全部历史。
    message: str = Field(min_length=1, max_length=2000)


class ConfirmRequest(RequestModel):
    """浏览器恢复人工确认时提交的数据。"""

    # True 表示确认执行，False 表示拒绝执行。
    approved: bool


class AgentReply(BaseModel):
    """普通对话和确认接口共用的结构化响应。"""

    # 流程被 interrupt 暂停时还没有最终回答，因此允许为 None。
    answer: str | None = None
    # 前端根据该字段判断应该展示回答，还是展示确认按钮。
    needs_confirmation: bool = False
    # 保存 interrupt 携带的操作名称、参数或提示信息。
    confirmation: dict[str, Any] | None = None
    # 每个响应都创建自己的空列表，避免多个响应共享同一个可变对象。
    trace: list[dict[str, Any]] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str
    agent_ready: bool
    # MySQL 中保存的 Agent Thread 数量，可跨服务重启保留。
    thread_count: int
