"""业务数据、会话索引和 Agent 状态均可跨重启恢复。"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agents.multi_agent import MultiAgentApplication
from app.config import BASE_DIR
from app.database import engine
from app.rag.knowledge_base import INDEX_MANIFEST_PATH
from app.routers.agent import router as agent_router
from app.routers.auth import router as auth_router
from app.routers.system import router as system_router
from app.routers.threads import router as threads_router

STATIC_DIR = BASE_DIR / "static"


def checkpoint_path() -> Path:
    """把 CHECKPOINT_DB 解析为不依赖启动目录的绝对路径。"""

    configured = (os.getenv("CHECKPOINT_DB") or "runtime/checkpoints.sqlite3").strip()
    path = Path(configured)
    if not path.is_absolute():
        path = BASE_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时打开共享 Checkpointer，关闭时释放数据库资源。"""

    if not INDEX_MANIFEST_PATH.exists():
        raise RuntimeError("尚未构建向量库，请先运行：python -m app.build_index")

    async with AsyncSqliteSaver.from_conn_string(
        str(checkpoint_path())
    ) as checkpointer:
        app.state.agent = MultiAgentApplication(checkpointer=checkpointer)
        # 只保护当前单进程内同一 Thread 的并发执行。
        app.state.active_threads = set()
        yield
        app.state.active_threads.clear()
    engine.dispose()


app = FastAPI(
    title="持久化多 Agent SSE API",
    description="持久化多 Agent SSE API：登录认证、多会话历史与可恢复状态",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.include_router(system_router)
app.include_router(auth_router)
app.include_router(threads_router)
app.include_router(agent_router)
