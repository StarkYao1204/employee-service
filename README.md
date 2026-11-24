# employee-agent-service

持久化多 Agent SSE API：密码登录（JWT）、多会话历史、Thread 归属校验、
角色过滤的 RAG 知识库、工具调用人工确认（interrupt）与 SSE 流式输出，
业务数据、会话索引和 Agent 状态均可跨服务重启恢复。

## 功能特性

- **可信身份**：JWT 登录，角色（employee / hr）；Agent 只信任服务端注入的 Runtime Context，不信任消息中的角色自述
- **多 Agent 编排**：Supervisor 把任务委派给三个专业 Agent（知识 / 员工服务 / HR 审批），Agent-as-Tool；普通员工的 Supervisor 根本拿不到 HR 工具
- **RAG**：本地 Chroma 向量库 + Qwen `text-embedding-v4`（DashScope OpenAI 兼容接口），检索阶段按角色过滤，越权文档不进候选集
- **人工确认**：设备申请与审批在写库前 `interrupt()` 暂停，前端确认后 `Command(resume=...)` 恢复
- **流式输出**：SSE 逐字输出 Supervisor 回答 + 工具调用状态事件
- **跨重启恢复**：MySQL 保存业务数据与会话索引，SQLite Checkpointer 保存对话消息、图状态与中断
- **审计日志**：登录、申请、审批的成败均记录最小化审计事件（`app/security/audit.py`）

## 项目结构

```text
├─ app/                       FastAPI 后端
│  ├─ main.py                 应用工厂：lifespan、CORS、静态挂载、路由注册
│  ├─ config.py               BASE_DIR 与 .env 加载（全项目路径锚点）
│  ├─ database.py             SQLAlchemy 引擎 / Base / SessionLocal
│  ├─ models.py               ORM 模型（5 张表，只映射不建表）
│  ├─ schemas.py              Pydantic 请求/响应模型
│  ├─ security/               认证（auth）、请求依赖（dependencies）、审计（audit）
│  ├─ agents/                 多 Agent 编排（multi_agent）、业务工具（business_tools）
│  ├─ rag/                    知识解析、向量化与角色过滤检索（knowledge_base）
│  ├─ routers/                路由：system / auth / threads / agent / sse
│  └─ build_index.py          构建向量库 CLI
├─ packages/release_guard/    版本清单校验库（uv workspace 成员）
├─ prompts/supervisor.md      Supervisor 提示词（版本清单引用其摘要）
├─ release/agent_versions.json  Agent 版本清单（Prompt/模型/工具/知识库/索引）
├─ scripts/validate_version_manifest.py  清单校验脚本（本地门禁之一）
├─ tests/                     pytest：test_sse、test_schemas（单元）、test_health（integration，需数据库）
├─ knowledge/                 知识库语料 + knowledge_manifest.json 清单
├─ static/                    前端页面（原生 HTML/CSS/JS）
├─ runtime/                   LangGraph checkpoint（生成物，不入库）
├─ vector_store/              Chroma 索引（生成物，不入库）
├─ pyproject.toml / uv.lock   依赖声明与锁定结果
└─ .env / .env.example        真实配置 / 配置模板
```

## 环境要求

- Python 3.14、[uv](https://docs.astral.sh/uv/)
- MySQL（5 张表：`departments`、`users`、`devices`、`device_requests`、`agent_threads`，结构见 `app/models.py`，需自建；演示账号 `zhang_wei` / `wang_fang`，密码 `123456`）
- DashScope API Key（Qwen 向量）+ 一个支持 Tool Calling 的聊天模型 API

## 快速开始

```bash
uv sync --locked --all-groups        # 按锁文件恢复环境（含 lint/test/security 工具组）
cp .env.example .env                 # 填写下列环境变量
uv run python -m app.build_index     # 构建向量库（走 DashScope，需网络）
uv run uvicorn app.main:app --reload # 启动服务
```

- 前端页面：<http://127.0.0.1:8000/>
- 接口文档：<http://127.0.0.1:8000/docs>

> 服务启动本身不依赖 MySQL（引擎惰性连接），但登录、会话、`/api/health` 需要数据库在线。

## 环境变量

| 组 | 变量 | 说明 |
| --- | --- | --- |
| 聊天模型 | `MODEL_PROVIDER` / `MODEL_NAME` / `API_KEY` / `BASE_URL` | 必须支持 Tool Calling（OpenAI 兼容接口） |
| Qwen 向量 | `DASHSCOPE_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` / `EMBEDDING_DIMENSIONS` | 建索引与检索共用同一模型与维度 |
| MySQL | `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` / `DB_NAME` | 密码用原文，不需要 URL 编码 |
| Checkpoint | `CHECKPOINT_DB` | LangGraph 消息/状态/中断存储，相对路径以项目根为基准 |
| JWT | `JWT_SECRET_KEY` / `JWT_ALGORITHM` / `ACCESS_TOKEN_EXPIRE_MINUTES` | 密钥至少 32 字节随机值（`openssl rand -hex 32`） |

## 接口一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/token` | 表单登录，签发 Bearer Token |
| GET | `/api/auth/me` | 当前用户信息 |
| GET / POST | `/api/threads` | 我的会话列表 / 新建会话 |
| GET | `/api/thread/{id}/messages` | 历史消息 + 待确认操作 |
| POST | `/api/thread/{id}/chat/stream` | SSE 流式对话 |
| POST | `/api/thread/{id}/confirm` | 人工确认后从中断点恢复 |
| GET | `/api/health` | 健康检查（含会话计数） |

## 本地质量门禁

```bash
uv lock --check                                                # 声明与锁文件一致
uv run --locked ruff check .                                   # lint
uv run --locked ruff format --check .                          # 格式
uv run --locked mypy app                                       # 类型检查
uv run --locked pytest --cov                                   # 测试（test_health 需数据库在线）
uv run --locked python scripts/validate_version_manifest.py    # Agent 版本清单校验
git ls-files -z | xargs -0 uv run --locked detect-secrets-hook --baseline .secrets.baseline
uv build --all-packages --out-dir dist                         # 构建候选产物
```

规则：前一步失败就停止，修复后从失败项重跑，最终从头完整跑一遍。

## 版本清单维护

`release/agent_versions.json` 记录 Prompt、聊天模型、工具、Harness、Embedding、知识库快照与索引的版本及 SHA-256 摘要。改动任何被记录的组件后，按「人工审查影响 → 更新组件版本号 → 重算摘要 → 重跑门禁」的顺序更新，不要直接重算摘要消化未审改动。

## 其他说明

- `runtime/`、`vector_store/`、`dist/`、`.coverage` 为生成物，已在 `.gitignore` 忽略；`.env` 绝不入库，`.secrets.baseline` 应入库
- CORS 允许 `http://127.0.0.1:5500` / `http://localhost:5500`（用 Live Server 调试前端时使用）
- 依赖与工具配置集中在 `pyproject.toml`；workspace 含根应用与 `release_guard` 两个包，`uv sync --all-packages` 同步全部成员
