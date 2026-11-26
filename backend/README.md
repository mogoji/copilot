# 售后客服助手 · 后端

基于 FastAPI + pgvector 的 RAG（检索增强生成）后端：把 FAQ 向量化灌进 PostgreSQL，用户提问时先检索证据，再交给 GLM 流式回答。

## 技术栈

| 层 | 技术 |
|---|---|
| 服务 | FastAPI（ASGI）+ uvicorn |
| 上游模型 | 智谱 GLM（embedding-3 向量化 + glm-5.3-flash 生成）|
| 数据库 | PostgreSQL + pgvector（hnsw 余弦相似度索引）|
| 语言 / 包管理 | Python 3.12 / uv |
| 连接池 | psycopg-pool（同步 ConnectionPool + asyncio.to_thread）|

## 目录结构

```
backend/
├── app/
│   ├── main.py            # FastAPI 入口（/health、/chat/stream SSE）
│   ├── rag.py             # RAG 核心：向量化 + pgvector 检索 + 混合检索（待启用）
│   ├── ingest.py          # 灌库脚本（切片 + embedding + 入库，可重复执行）
│   ├── eval_retrieval.py  # 检索层评测（只测 retrieve，快且省钱）
│   ├── eval_e2e.py        # 端到端评测（走真实 /chat/stream）
│   ├── config.py          # 集中配置（所有 URL/模型/阈值/DSN 从这里读）
│   ├── __init__.py        # 包标记 + 运行约定
│   └── data/
│       ├── faq.json       # 原始 FAQ 数据（每条含 q/a 字段）
│       └── eval.jsonl     # 评测集（每行 JSON：q、expect、gold 等）
├── schema.sql             # 数据库初始化脚本（extension + 建表 + 索引）
├── pyproject.toml
├── uv.lock
├── .env.example           # 环境变量模板（GLM_API_KEY / DB_*）
└── README.md
```

## 快速开始

### 1. 安装依赖（首次）

```bash
cd backend
uv sync
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 然后编辑 .env，填入：
#   GLM_API_KEY=你的智谱 API Key
#   DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD
# 或直接用完整连接串：
#   DATABASE_URL=postgresql://user:pass@localhost:5432/copilot
```

必需项：`GLM_API_KEY` + 数据库连接配置（两种方式二选一）。启动时 `app.config` 会校验，缺失立即报错（fail-fast）。

### 3. 初始化数据库

```bash
# 先创建空库（如果还没有）
createdb copilot

# 执行 schema.sql（启用 pgvector、建表、建 HNSW 索引）
psql -d copilot -f schema.sql
```

### 4. 灌库（把 FAQ 切片向量化入库）

```bash
python -m app.ingest
# 输出示例：
#   共 20 条切片，开始向量化...
#     embedding batch 1 (20 条) 完成
#   灌库完成: 20 条
```

灌库是 TRUNCATE + 全量 INSERT，可重复执行（更新 FAQ 后直接再跑一次）。数据量大时会自动按 32 条一批请求 embedding。

### 5. 启动服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
# 或用 uv run：
uv run uvicorn app.main:app --port 8000
```

### 6. 测试

```bash
# 健康检查
curl http://localhost:8000/health        # {"ok": true}

# 流式对话（SSE，客户端可传 evidence_th）
curl -N -X POST http://localhost:8000/chat/stream \
     -H "Content-Type: application/json" \
     -d '{"q": "退款多久到账？"}'
# 返回：data: {...} 事件流（sources → token → token → ... → [DONE]）
```

## 用户认证（登录接口）

`POST /api/auth/login`，基于 JWT 的无状态登录。

- **请求**：JSON `{ "username": "admin", "password": "admin123" }`
- **成功（200）**：`{ "code": 0, "message": "success", "data": { "access_token": "<jwt>", "token_type": "bearer", "user": {...} } }`
- **失败（401）**：`{ "code": 401, "message": "用户名或密码错误", "data": null }`（账号不存在与密码错误提示相同，避免用户名枚举）
- **缺参（422）**：Pydantic 校验，返回字段级提示，如 `password Field required`
- 密码用 bcrypt 哈希存库（`users` 表），JWT 用 HS256 签发，密钥与有效期见 `.env`（`JWT_SECRET_KEY` / `ACCESS_TOKEN_EXPIRE_MINUTES`）。
- 应用启动时 `auth.ensure_admin_seed()` 自动建表并写入演示账号 `admin / admin123`（幂等）。
- CORS 默认放行 `http://localhost:5173` 与 `http://127.0.0.1:5173`，可通过 `ALLOWED_ORIGINS` 覆盖。

```bash
# 登录示例
curl -s -X POST http://localhost:8000/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username":"admin","password":"admin123"}'
```

## 运行评测

### 检索层（推荐先跑，快且省钱）

```bash
python -m app.eval_retrieval
```

### 端到端（走真实 /chat/stream，可指定阈值对比）

```bash
python -m app.eval_e2e 0.60       # 用当前默认阈值
python -m app.eval_e2e 0.35       # 复现基线对比
```

## 配置说明

所有配置集中在 `app/config.py`，通过环境变量覆盖。主要项：

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `GLM_API_KEY` | （必填） | 智谱 API Key |
| `DATABASE_URL` | （无） | 完整连接串，优先级高于 DB_* 分量 |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | localhost/5432/copilot/copilot/（必填） | 分量形式 |
| `EMBEDDING_MODEL` | embedding-3 | 向量化模型 |
| `EMBEDDING_DIMENSIONS` | 1024 | 向量维度（需与模型 + schema.sql 保持一致） |
| `GLM_MODEL` | glm-5.3-flash | 生成模型 |
| `EVIDENCE_TH` | 0.60 | 服务端证据阈值（低于此相似度的检索结果不喂给模型）|
| `EVIDENCE_TH_MIN` / `EVIDENCE_TH_MAX` | 0.40 / 0.85 | 客户端传入 evidence_th 会被 clamp 到这个范围 |
| `HTTP_TIMEOUT` / `EMBED_TIMEOUT` | 60 / 30 | 上游调用超时秒数 |
| `DB_POOL_MIN` / `DB_POOL_MAX` | 1 / 10 | 数据库连接池大小 |
| `ALLOWED_ORIGINS` | http://localhost:5173 | CORS 白名单，逗号分隔 |

## 架构要点

- **检索不阻塞事件循环**：`rag.retrieve` 用同步 psycopg + 线程安全连接池，FastAPI 路由里通过 `asyncio.to_thread` 放到工作线程执行。
- **连接复用**：GLM HTTP 客户端在 lifespan 里创建一次，全程复用；DB 连接用 psycopg-pool.ConnectionPool 跨请求复用。
- **启动校验**：必需环境变量缺失时，`config.validate()` 在 import 阶段抛错，不会等到请求进来才暴露。
- **阈值安全**：客户端可传 `evidence_th`，但会被 clamp 到 `[EVIDENCE_TH_MIN, EVIDENCE_TH_MAX]`，防止传 0 绕过拒答防线。
- **优雅异常**：检索 / 上游 GLM 调用失败时返回 SSE error 事件，不中断连接也不让请求崩溃。
