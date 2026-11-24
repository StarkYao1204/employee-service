"""Agent 流式对话与人工确认路由。"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage

from app.agents.multi_agent import UserSession, message_text, outer_trace
from app.routers.sse import sse_event
from app.schemas import AgentReply, ChatRequest, ConfirmRequest
from app.security.dependencies import RuntimeSessionDep

router = APIRouter()

STREAM_TIMEOUT_SECONDS = 90


async def has_pending_confirmation(session: UserSession) -> bool:
    """从持久化 Checkpointer 查询当前 Thread 是否仍有 Interrupt。"""

    snapshot = await session.supervisor.aget_state(
        {"configurable": {"thread_id": session.thread_id}}
    )
    return bool(snapshot.interrupts)


def format_agent_result(result: dict[str, Any]) -> AgentReply:
    """把恢复执行后的 LangGraph 结果转换为普通 HTTP 响应。"""

    interrupts = result.get("__interrupt__", ())
    if interrupts:
        value = interrupts[0].value
        confirmation = value if isinstance(value, dict) else {"message": str(value)}
        return AgentReply(
            answer=None,
            needs_confirmation=True,
            confirmation=confirmation,
            trace=outer_trace(result),
        )
    answers = [
        message_text(message)
        for message in result.get("messages", [])
        if isinstance(message, AIMessage) and not message.tool_calls
    ]
    return AgentReply(
        answer=answers[-1] if answers else "Agent 没有返回可展示的回答",
        needs_confirmation=False,
        confirmation=None,
        trace=outer_trace(result),
    )


async def stream_agent_events(
    request: Request,
    session: UserSession,
    payload: ChatRequest,
) -> AsyncIterator[str]:
    """把 Agent 事件转换为 SSE，并保证结束时释放 Thread 占用标记。"""

    yield sse_event("status", {"message": "Agent 已开始处理"})
    try:
        async with asyncio.timeout(STREAM_TIMEOUT_SECONDS):
            async for event in request.app.state.agent.stream_chat(
                session, payload.message
            ):
                if await request.is_disconnected():
                    return
                yield sse_event(event["event"], event["data"])
        waiting = await has_pending_confirmation(session)
        yield sse_event(
            "done",
            {"status": "waiting_confirmation" if waiting else "completed"},
        )
    except TimeoutError:
        yield sse_event("error", {"message": "Agent 处理超时，请稍后重试"})
    except asyncio.CancelledError:
        raise
    except Exception:
        yield sse_event("error", {"message": "Agent 调用失败，请稍后重试"})
    finally:
        request.app.state.active_threads.discard(session.thread_id)


@router.post(
    "/api/thread/{thread_id}/chat/stream",
    response_class=StreamingResponse,
    tags=["Agent"],
)
async def stream_chat(
    payload: ChatRequest, request: Request, session: RuntimeSessionDep
) -> StreamingResponse:

    active_threads: set[str] = request.app.state.active_threads
    if session.thread_id in active_threads:
        raise HTTPException(status_code=409, detail="当前会话正在处理上一条请求")

    # set 的检查与添加之间没有 await，可在本进程事件循环内完成占用声明。
    active_threads.add(session.thread_id)
    try:
        if await has_pending_confirmation(session):
            raise HTTPException(status_code=409, detail="请先处理当前待确认操作")
    except Exception:
        active_threads.discard(session.thread_id)
        raise

    return StreamingResponse(
        stream_agent_events(request, session, payload),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.post(
    "/api/thread/{thread_id}/confirm", response_model=AgentReply, tags=["Agent"]
)
async def confirm_action(
    payload: ConfirmRequest, request: Request, session: RuntimeSessionDep
) -> AgentReply:
    active_threads: set[str] = request.app.state.active_threads
    if session.thread_id in active_threads:
        raise HTTPException(status_code=409, detail="当前会话正在处理上一条请求")

    active_threads.add(session.thread_id)
    try:
        if not await has_pending_confirmation(session):
            raise HTTPException(status_code=409, detail="当前会话没有等待确认的操作")
        result = await request.app.state.agent.resume(
            session, approved=payload.approved
        )
        return format_agent_result(result)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Agent 调用失败，请稍后重试"
        ) from exc
    finally:
        active_threads.discard(session.thread_id)
