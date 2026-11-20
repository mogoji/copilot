# asyncio 是异步编程工具（当前代理实现未直接调用）；json 用于编码和解析 JSON 数据。
import asyncio
import json

# FastAPI 提供 Web 应用与路由；StreamingResponse 用于逐段返回响应内容。
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
# 跨域中间件允许浏览器前端从不同源访问本服务。
from fastapi.middleware.cors import CORSMiddleware

# 创建 FastAPI 应用实例，后续路由和中间件都注册到该实例上。
app = FastAPI()
# 注册 CORS 中间件：允许本地前端开发服务器跨域访问。
app.add_middleware(
    CORSMiddleware,
    # 仅允许来自该前端地址的跨域请求。
    allow_origins=["http://localhost:5173"],
    # 允许所有 HTTP 方法和请求头。
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 GET /health 健康检查接口，用于确认服务能够正常响应。
@app.get("/health")
def health():
    # 返回 JSON 对象，表示服务状态正常。
    return {"ok": True}

# os 用于读取环境变量；httpx 用于异步请求上游模型服务；json 用于处理流数据。
import os, json, httpx
# 将项目 .env 文件中的配置加载到进程环境变量，供后续读取 API 密钥。
from dotenv import load_dotenv
load_dotenv()
# 导入 RAG 检索函数：提问先从 pgvector 知识库找证据，再交给 GLM 回答。
from app.rag import retrieve

# 上游 GLM 对话接口地址。
GLM_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
# 要请求的 GLM 模型名称。
GLM_MODEL = "glm-5.3-flash"

# 注册 POST /chat/stream 接口，将前端请求转发给上游模型并流式返回结果。
@app.post("/chat/stream")
async def chat(body: dict):
    question = body.get("q", "")

    # ① 检索证据
    hits = retrieve(question, top_k=5)
    # 只保留相似度达标的证据（简单阈值，过滤明显不相关的）
    good = [h for h in hits if h["similarity"] >= 0.35]
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
            "Authorization": f"Bearer {os.getenv('GLM_API_KEY')}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": GLM_MODEL,
            "stream": True,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": question},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("POST", GLM_URL, headers=headers, json=payload) as r:
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