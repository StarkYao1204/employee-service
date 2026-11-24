import os
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config  # noqa: F401 —— 导入即加载项目根目录下的 .env
from app.models import User

password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummy-password")


def verify_password(plain_password: str, stored_hash: str) -> bool:
    """验证明文密码是否匹配数据库摘要。"""
    return password_hash.verify(plain_password, stored_hash)


def authenticate_user(
    db: Session,
    username: str,
    password: str,
) -> User | None:
    """验证账号状态和密码，失败时统一返回 None。"""
    user = db.scalar(select(User).where(User.username == username.strip()))

    if user is None or user.password_hash is None:
        verify_password(password, DUMMY_HASH)
        return None

    password_matches = verify_password(password, user.password_hash)

    if (
        not password_matches
        or not user.login_enabled
        or user.account_status != "active"
        or user.role not in {"employee", "hr"}
    ):
        return None
    return user


def _jwt_settings() -> tuple[str, str, int]:
    """读取并检查 JWT 配置。"""

    secret = (os.getenv("JWT_SECRET_KEY") or "").strip()
    if not secret or len(secret) < 32 or secret.startswith("<"):
        raise RuntimeError("JWT_SECRET_KEY 必须设置为至少 32 字节的随机值")

    algorithm = (os.getenv("JWT_ALGORITHM") or "HS256").strip()
    if algorithm != "HS256":
        raise RuntimeError("本课只演示 HS256，请将 JWT_ALGORITHM 设置为 HS256")

    try:
        expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES") or "30")
    except ValueError as e:
        raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES 必须是整数") from e

    if expire_minutes <= 0:
        raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES 必须大于 0")

    return secret, algorithm, expire_minutes


def create_access_token(user_id: str) -> str:
    """把稳定用户编号写入 sub，并签发短期 Access Token。"""

    secret, algorithm, expire_minutes = _jwt_settings()
    now = datetime.now(UTC)

    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
    }

    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(token: str) -> str:
    """验证签名和过期时间，并返回 Token 中的用户编号。"""

    secret, algorithm, _expire_minutes = _jwt_settings()

    payload = jwt.decode(
        token, secret, algorithms=[algorithm], options={"require": ["sub", "exp"]}
    )

    user_id = payload["sub"]
    if not isinstance(user_id, str) or not user_id:
        raise jwt.InvalidTokenError("JWT sub 必须是非空字符串")
    return user_id
