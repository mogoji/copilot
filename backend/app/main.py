# asyncio 是异步编程工具（当前代理实现未直接调用）；json 用于编码和解析 JSON 数据。
import asyncio
import json

# FastAPI 提供 Web 应用与路由；StreamingResponse 用于逐段返回响应内容。
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
# 跨域中间件允许浏览器前端从不同源访问本服务。
from fastapi.middleware.cors import CORSMiddleware

# 集中配置（在创建应用 / 注册中间件前导入，CORS 等需要读取配置）
from app import config

# 创建 FastAPI 应用实例，后续路由和中间件都注册到该实例上。
app = FastAPI()
# 注册 CORS 中间件：允许本地前端开发服务器跨域访问。
app.add_middleware(
    CORSMiddleware,
    # 仅允许来自该前端地址的跨域请求。
    allow_origins=config.ALLOWED_ORIGINS,
    # 允许所有 HTTP 方法和请求头。
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 GET /health 健康检查接口，用于确认服务能够正常响应。
@app.get("/health")
def health():
    # 返回 JSON 对象，表示服务状态正常。
    return {"ok": True}

# httpx 用于异步请求上游模型服务；json 用于处理流数据。
import httpx
# 导入 RAG 检索函数：提问先从 pgvector 知识库找证据，再交给 GLM 回答。
from app.rag import retrieve

# 上游地址 / 模型 / 证据阈值均由 app.config 集中管理，可通过环境变量覆盖。
# 证据阈值 EVIDENCE_TH 默认 0.60 的标定依据见 config.py；调参用 eval_retrieval.py 反复校准。

# 注册 POST /chat/stream 接口，将前端请求转发给上游模型并流式返回结果。
@app.post("/chat/stream")
async def chat(body: dict):
    question = body.get("q", "")
    # ① 检索证据
    hits = retrieve(question, top_k=5)
   
    th = float(body.get("evidence_th", config.EVIDENCE_TH))
    good = [h for h in hits if h["similarity"] >= th]
    # 拼成带编号的资料块
    evidence = "\n".join(
        f"[{i}] {h['content']}" for i, h in enumerate(good, 1)
    )
    sources = [{"index": i, "content": h["content"], "similarity": h["similarity"]}
               for i, h in enumerate(good, 1)]

    # ② 拼 prompt：明确要求"只根据资料回答 + 标引用编号 + 无资料就说不知道"
    system = (
        "你是售后客服助手。只能根据下面的资料回答问题，回答时标注引用编号如[1]。"
        "如果资料里没有相关信息，直接说『抱歉，资料中没有相关信息，建议联系人工客服』，不要编造。\n\n"
        f"资料：\n{evidence if evidence else '（无相关资料）'}"
    )

    async def gen():
        if sources:
            # 先发引用来源事件，让前端能显示出处
            yield f'data: {json.dumps({"sources": sources}, ensure_ascii=False)}\n\n'
        headers = {
            "Authorization": f"Bearer {config.GLM_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": config.GLM_MODEL,
            "stream": True,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": question},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("POST", config.GLM_URL, headers=headers, json=payload) as r:
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
                            yield f'data: {json.dumps({"token": token}, ensure_ascii=False)}\n\n'
        except Exception as e:
            yield f'data: {json.dumps({"error": str(e)}, ensure_ascii=False)}\n\n'
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")