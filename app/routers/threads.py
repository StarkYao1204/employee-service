"""会话（Thread）列表、创建与历史路由。"""

from uuid import uuid4

from fastapi import APIRouter, Request, status
from sqlalchemy import select

from app.database import SessionLocal
from app.models import AgentThread
from app.schemas import (
    HistoryMessage,
    ThreadHistoryResponse,
    ThreadResponse,
)
from app.security.dependencies import CurrentUserDep, RuntimeSessionDep

router = APIRouter()


@router.get("/api/threads", response_model=list[ThreadResponse], tags=["Threads"])
def list_threads(current_user: CurrentUserDep) -> list[ThreadResponse]:
    statement = (
        select(AgentThread)
        .where(AgentThread.user_id == current_user.user_id)
        .order_by(AgentThread.created_at.desc())
    )

    with SessionLocal() as db:
        records = db.scalars(statement).all()

        return [
            ThreadResponse(thread_id=record.thread_id, created_at=record.created_at)
            for record in records
        ]


@router.post(
    "/api/threads",
    response_model=ThreadResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Threads"],
)
def create_thread(current_user: CurrentUserDep) -> ThreadResponse:
    with SessionLocal.begin() as db:
        record = AgentThread(thread_id=str(uuid4()), user_id=current_user.user_id)

        db.add(record)
    response = ThreadResponse(thread_id=record.thread_id, created_at=record.created_at)

    return response


@router.get(
    "/api/thread/{thread_id}/messages",
    response_model=ThreadHistoryResponse,
    tags=["Threads"],
)
async def list_thread_messages(
    request: Request, session: RuntimeSessionDep
) -> ThreadHistoryResponse:
    messages, confirmation = await request.app.state.agent.get_thread_history(session)

    return ThreadHistoryResponse(
        messages=[HistoryMessage(**item) for item in messages],
        needs_confirmation=confirmation is not None,
        confirmation=confirmation,
    )
