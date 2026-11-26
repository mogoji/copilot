"""售后客服助手后端：提供健康检查与流式对话接口。"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app import auth
from app import config
from app import db
from app import rag

# 日志：仅在根 logger 尚无 handler 时初始化，避免覆盖 uvicorn 的日志配置
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
logger = logging.getLogger("app.main")


class ChatRequest(BaseModel):
    q: str = Field(..., description="用户问题")
    evidence_th: float | None = Field(
        None, description="可选：证据相似度阈值，将被限制在服务端允许范围内"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：创建上游 GLM 流式调用的共享 HTTP 客户端（连接池复用，避免每请求新建）
    app.state.glm_client = httpx.AsyncClient(timeout=config.HTTP_TIMEOUT)
    # 初始化 users 表与种子管理员账号：同步 DB 操作放工作线程，不阻塞事件循环
    await asyncio.to_thread(auth.ensure_admin_seed)
    logger.info("应用启动，GLM 客户端已就绪")
    try:
        yield
    finally:
        # 停止：释放 HTTP 客户端与共享 DB 连接池
        await app.state.glm_client.aclose()
        db.close()
        logger.info("应用停止，资源已释放")


app = FastAPI(lifespan=lifespan)
# 注册 CORS 中间件：允许配置的前端源跨域访问。
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载认证路由（/api/auth/login 等）
app.include_router(auth.router)


# ---- 统一异常处理：HTTP 错误与参数校验错误都包成 { code, message, data } ----
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": str(exc.detail), "data": None},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    msg = "请求参数校验失败"
    errors = exc.errors()
    if errors:
        first = errors[0]
        # loc 形如 ("body", "username")，去掉外层定位符，只保留字段路径
        loc = ".".join(
            str(x) for x in first.get("loc", []) if x not in ("body", "query")
        )
        tip = first.get("msg", "")
        msg = f"{loc} {tip}".strip() if loc else tip
    return JSONResponse(
        status_code=422, content={"code": 422, "message": msg, "data": None}
    )


def _sse(data: dict) -> str:
    """把一个 dict 编码成一条 SSE 事件。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _resolve_threshold(client_th: float | None) -> float:
    """取阈值并 clamp 到服务端安全范围，防止客户端传 0 绕过拒答防线。"""
    clamped = config.clamp_evidence_th(client_th)
    if client_th is not None and clamped != float(client_th):
        logger.warning(
            "evidence_th=%s 超出允许范围 [%s, %s]，已 clamp 为 %s",
            client_th, config.EVIDENCE_TH_MIN, config.EVIDENCE_TH_MAX, clamped,
        )
    return clamped


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/chat/stream")
async def chat(req: ChatRequest):
    question = req.q.strip()
    th = _resolve_threshold(req.evidence_th)

    # ① 检索证据：同步函数放到工作线程执行，不阻塞事件循环；DB 走连接池复用
    try:
        hits = await asyncio.to_thread(rag.retrieve, question, top_k=5)
    except Exception:
        logger.exception("检索失败 question=%r", question)

        async def gen_err():
            yield _sse({"error": "检索服务暂不可用，请稍后重试"})
            yield "data: [DONE]\n\n"

        return StreamingResponse(gen_err(), media_type="text/event-stream")

    good = [h for h in hits if h["similarity"] >= th]
    # 拼成带编号的资料块
    evidence = "\n".join(f"[{i}] {h['content']}" for i, h in enumerate(good, 1))
    sources = [
        {"index": i, "content": h["content"], "similarity": h["similarity"]}
        for i, h in enumerate(good, 1)
    ]

    # ② 拼 prompt：明确要求"只根据资料回答 + 标引用编号 + 无资料就说不知道"
    system = (
        "你是售后客服助手。只能根据下面的资料回答问题，回答时标注引用编号如[1]。"
        "如果资料里没有相关信息，直接说『抱歉，资料中没有相关信息，建议联系人工客服』，不要编造。\n\n"
        f"资料：\n{evidence if evidence else '（无相关资料）'}"
    )

    glm_client: httpx.AsyncClient = app.state.glm_client

    async def gen():
        if sources:
            # 先发引用来源事件，让前端能显示出处
            yield _sse({"sources": sources})
        payload = {
            "model": config.GLM_MODEL,
            "stream": True,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": question},
            ],
        }
        try:
            async with glm_client.stream(
                "POST", config.GLM_URL, headers=config.HEADERS, json=payload
            ) as r:
                if r.status_code >= 400:
                    body = (await r.aread())[:500]
                    logger.error("上游 GLM 返回 %s: %s", r.status_code, body)
                    yield _sse({"error": f"上游模型服务异常（{r.status_code}）"})
                    yield "data: [DONE]\n\n"
                    return
                async for line in r.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    chunk = line[6:]
                    if chunk.strip() == "[DONE]":
                        break
                    try:
                        d = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
                    choices = d.get("choices") or []
                    if not choices:
                        continue
                    token = (choices[0].get("delta") or {}).get("content") or ""
                    if token:
                        yield _sse({"token": token})
        except Exception:
            logger.exception("调用上游 GLM 失败")
            yield _sse({"error": "模型服务调用失败，请稍后重试"})
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
