"""SQLAlchemy Engine、ORM 基类和 Session 工厂。"""

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app import config  # noqa: F401 —— 导入即加载项目根目录下的 .env

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

if not all((DB_USER, DB_PASSWORD, DB_NAME)):
    raise RuntimeError("请在 .env 中配置 DB_USER、DB_PASSWORD、DB_NAME")

# 密码保持原文；URL.create() 直接构造 URL 对象，不解析连接地址字符串，
# 因此 @、:、/ 等特殊字符不需要做 URL 编码。
DATABASE_URL = URL.create(
    "mysql+pymysql",
    username=DB_USER,
    password=DB_PASSWORD,
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "3306")),
    database=DB_NAME,
    query={"charset": "utf8mb4"},
)


class Base(DeclarativeBase):
    """所有 ORM 模型共同继承的声明式基类。"""


# Engine 管理数据库方言和连接池；pool_pre_ping 会在复用连接前检查连接是否可用。
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# SessionLocal 是 Session 工厂。autoflush=False 避免查询前自动 flush；
# expire_on_commit=False 让提交后的对象属性仍可直接读取。
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)
