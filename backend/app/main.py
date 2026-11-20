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

# 上游 GLM 对话接口地址。
GLM_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
# 要请求的 GLM 模型名称。
GLM_MODEL = "glm-5.3-flash"

# 注册 POST /chat/stream 接口，将前端请求转发给上游模型并流式返回结果。
@app.post("/chat/stream")
async def chat(body: dict):
    # 定义异步生成器；StreamingResponse 消费它时，会逐段发送生成的数据。
    async def gen():
        # 设置上游接口所需的认证信息和 JSON 请求类型。
        headers = {
            # 从环境变量 GLM_API_KEY 读取密钥，并作为 Bearer Token 发送。
            "Authorization": f"Bearer {os.getenv('GLM_API_KEY')}",
            "Content-Type": "application/json",
        }
        # 构造上游请求：启用流式响应，并把请求体中的 q 作为用户消息。
        # 若请求体没有 q，则使用空字符串。
        payload = {
            "model": GLM_MODEL,
            "stream": True,
            "messages": [{"role": "user", "content": body.get("q", "")}],
        }
        try:
            # 创建异步 HTTP 客户端，单次请求超时时间为 60 秒。
            async with httpx.AsyncClient(timeout=60) as client:
                # 向上游发送 POST 请求；stream() 允许边接收响应边处理内容。
                async with client.stream("POST", GLM_URL, headers=headers, json=payload) as r:
                    # 按行读取上游响应，避免等待完整响应体下载完成。
                    async for line in r.aiter_lines():
                        # 忽略非 SSE 数据行，只处理以 data: 开头的事件内容。
                        if not line.startswith("data: "):
                            continue
                        # 去掉 SSE 的 data: 前缀，取得事件的数据部分。
                        chunk = line[6:]
                        # 上游用 [DONE] 表示生成结束；收到后停止读取响应。
                        if chunk.strip() == "[DONE]":
                            break
                        try:
                            # 将事件数据从 JSON 字符串解析为 Python 对象。
                            d = json.loads(chunk)
                        except json.JSONDecodeError:
                            # 忽略格式错误的事件数据，继续处理后续事件。
                            continue
                        # 读取候选回答列表；字段缺失或为空时按空列表处理。
                        choices = d.get("choices") or []
                        if not choices:
                            continue
                        # 从第一个候选项的增量内容中取得本次新生成的文本片段。
                        token = (choices[0].get("delta") or {}).get("content") or ""
                        if token:
                            # 将文本片段包装为前端约定的 JSON SSE 事件后立即发送。
                            # ensure_ascii=False 保留中文等非 ASCII 字符。
                            yield f'data: {json.dumps({"token": token}, ensure_ascii=False)}\n\n'
        except Exception as e:
            # 将请求或流处理期间发生的异常作为 SSE 错误事件发给前端。
            yield f'data: {json.dumps({"error": str(e)}, ensure_ascii=False)}\n\n'
        # 正常结束或异常被处理后，发送统一的流结束标记。
        yield "data: [DONE]\n\n"
    # 返回 SSE 流式响应，浏览器可逐段接收生成内容。
    return StreamingResponse(gen(), media_type="text/event-stream")