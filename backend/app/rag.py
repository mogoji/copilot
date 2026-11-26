"""RAG 核心：把问题向量化，去 pgvector 检索最相关的切片。

实现说明：
- 数据库访问用 psycopg（同步）+ psycopg_pool.ConnectionPool（线程安全连接池），
  复用连接、避免每次请求新建连接；
- 检索函数本身是同步的，FastAPI 路由里通过 asyncio.to_thread 调用，
  因此不会阻塞事件循环；同时同步 psycopg 不依赖事件循环类型，
  在 Windows + uvicorn（默认 ProactorEventLoop）下可正常工作；
- 连接池为延迟初始化（lazy），import 时不连库，便于测试与脚本；
- 应用停止时调用 close() 释放连接池。
"""
import logging
from collections import defaultdict

import httpx
import psycopg

from app import config
from app.db import close, get_pool

logger = logging.getLogger("app.rag")

# 连接池统一在 app.db 中维护（get_pool / close），RAG 与认证模块共用。


def _vec_to_pg(vec) -> str:
    """把浮点向量转成 pgvector 接受的字符串 [0.1,0.2,...]。"""
    return "[" + ",".join(str(x) for x in vec) + "]"


def embed_one(text):
    """把单条文本向量化为指定维度向量。"""
    r = httpx.post(
        config.EMB_URL,
        headers=config.HEADERS,
        json={
            "model": config.EMBEDDING_MODEL,
            "input": text,
            "dimensions": config.EMBEDDING_DIMENSIONS,
        },
        timeout=config.EMBED_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["data"][0]["embedding"]


def retrieve(question, top_k=5):
    """返回与 question 最相关的 top_k 条切片，每条含 content 和相似度。"""
    vec = embed_one(question)
    vec_str = _vec_to_pg(vec)
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            # <=> 是 pgvector 的余弦距离算子；1 - 距离 = 相似度（越接近 1 越相关）。
            cur.execute(
                "SELECT content, 1 - (embedding <=> %s::vector) AS similarity "
                "FROM chunks ORDER BY embedding <=> %s::vector LIMIT %s",
                (vec_str, vec_str, top_k),
            )
            rows = cur.fetchall()
    return [{"content": c, "similarity": round(float(s), 4)} for c, s in rows]


# ===== 混合检索：关键词通道 + RRF 融合 =====
# 说明：当前线上 main.py 仍用纯向量 retrieve（见其调用）。
# 下面两个函数是"待启用"的第二路检索；要接进线上时，在 main.py 把
# rag.retrieve 换成 rag.retrieve_hybrid 即可（同样用 to_thread 调用）。

def retrieve_keyword(question, top_k=10):
    """关键词通道：按中文字符二元组（bigram）重叠度打分，无需额外依赖。"""
    def bigrams(s):
        s = "".join(c for c in s if c.strip())
        return {s[i:i + 2] for i in range(len(s) - 1)}

    qg = bigrams(question)
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT doc_id, content FROM chunks")
            rows = cur.fetchall()
    scored = []
    for doc_id, content in rows:
        cg = bigrams(content[:80])            # 取前 80 字（大致覆盖问句+答案开头）
        overlap = len(qg & cg) / max(1, len(qg | cg))
        scored.append({"content": content, "kw": round(overlap, 4)})
    return sorted(scored, key=lambda x: -x["kw"])[:top_k]


def retrieve_hybrid(question, top_k=5, rrf_k=60):
    """RRF 融合向量通道与关键词通道：只按两路排名融合，无需归一化分数。"""
    vec = retrieve(question, top_k=10)
    kw = retrieve_keyword(question, top_k=10)
    scores, sim_of = defaultdict(float), {}
    for rank, h in enumerate(vec, 1):
        scores[h["content"]] += 1 / (rrf_k + rank)
        sim_of[h["content"]] = h["similarity"]
    for rank, h in enumerate(kw, 1):
        scores[h["content"]] += 1 / (rrf_k + rank)
    merged = sorted(scores.items(), key=lambda x: -x[1])[:top_k]
    return [{"content": t, "similarity": round(sim_of.get(t, 0), 4),
             "rrf": round(s, 5)} for t, s in merged]


if __name__ == "__main__":
    try:
        for q in ["退款多久到账？", "怎么开发票"]:
            print("问题:", q)
            for i, r in enumerate(retrieve(q), 1):
                print(f"  [{i}] 相似度 {r['similarity']:.3f} | {r['content'][:40]}")
    finally:
        close()
