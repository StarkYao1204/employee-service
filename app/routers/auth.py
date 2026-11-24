"""登录认证路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.database import SessionLocal
from app.schemas import CurrentUserResponse, TokenResponse
from app.security.audit import audit_event
from app.security.auth import authenticate_user, create_access_token
from app.security.dependencies import CurrentUserDep

router = APIRouter()


@router.post("/api/auth/token", response_model=TokenResponse, tags=["Authentication"])
def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenResponse:
    """验证用户名和密码，只签发 Token，不创建 Thread。"""

    with SessionLocal() as db:
        user = authenticate_user(db, form_data.username, form_data.password)
        if user is None:
            audit_event(
                "login",
                "failure",
                user_id=form_data.username,
                resource="/api/auth/token",
                reason="用户名或密码错误",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = user.user_id
    audit_event("login", "success", user_id=user_id, resource="/api/auth/token")
    return TokenResponse(access_token=create_access_token(user_id))


@router.get("/api/auth/me", response_model=CurrentUserResponse, tags=["Authentication"])
def read_current_user(current_user: CurrentUserDep) -> CurrentUserResponse:

    return CurrentUserResponse(
        user_id=current_user.user_id,
        username=current_user.username,
        display_name=current_user.display_name,
        role=current_user.role,
        department_id=current_user.department_id,
    )
