from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select

from app.agents.business_tools import RunContext
from app.agents.multi_agent import UserSession
from app.database import SessionLocal
from app.models import AgentThread, User
from app.security.auth import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token")


@dataclass(frozen=True)
class CurrentUser:
    """从 Token 和数据库恢复出的请求级可信身份"""

    user_id: str
    username: str
    display_name: str
    role: str
    department_id: str


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证登录凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> CurrentUser:
    try:
        user_id = decode_access_token(token)
    except jwt.InvalidTokenError as e:
        raise _credentials_exception() from e

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.user_id == user_id))

        if (
            user is None
            or not user.login_enabled
            or user.account_status != "active"
            or user.username is None
            or user.role not in {"employee", "hr"}
        ):
            raise _credentials_exception()

    return CurrentUser(
        user_id=user.user_id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        department_id=user.department_id,
    )


def get_owned_runtime_session(
    request: Request,
    thread_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> UserSession:
    statement = select(AgentThread).where(
        AgentThread.user_id == current_user.user_id, AgentThread.thread_id == thread_id
    )
    with SessionLocal() as db:
        agent_thread = db.scalar(statement)

        if agent_thread is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在"
            )

        restored_thread_id = agent_thread.thread_id

    context = RunContext(
        user_id=current_user.user_id,
        username=current_user.username,
        display_name=current_user.display_name,
        role=current_user.role,
        department_id=current_user.department_id,
    )

    return request.app.state.agent.build_runtime_session(context, restored_thread_id)


# 路由签名复用的 Annotated 别名，集中定义避免各路由文件重复声明。
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
RuntimeSessionDep = Annotated[UserSession, Depends(get_owned_runtime_session)]
