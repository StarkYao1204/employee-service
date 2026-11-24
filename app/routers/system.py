"""系统健康检查路由。"""

from fastapi import APIRouter
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import AgentThread
from app.schemas import HealthResponse

router = APIRouter()


@router.get("/api/health", response_model=HealthResponse, tags=["Agent API"])
def health() -> HealthResponse:
    with SessionLocal() as db:
        thread_count = db.scalar(select(func.count()).select_from(AgentThread)) or 0
    return HealthResponse(status="ok", agent_ready=True, thread_count=thread_count)
