"""RAG 核心：把问题向量化，去 pgvector 检索最相关的切片。"""
import os, httpx, psycopg
from collections import defaultdict
from dotenv import load_dotenv
load_dotenv()

EMB_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
HEADERS = {"Authorization": f"Bearer {os.getenv('GLM_API_KEY')}", "Content-Type": "application/json"}
DB_DSN = "host=localhost port=5432 dbname=copilot user=copilot password=copilot123"


def embed_one(text):
    """把单条文本向量化为 1024 维向量。"""
    r = httpx.post(EMB_URL, headers=HEADERS,
                   json={"model": "embedding-3", "input": text, "dimensions": 1024}, timeout=30)
    return r.json()["data"][0]["embedding"]


def retrieve(question, top_k=5):
    """返回与 question 最相关的 top_k 条切片，每条含 content 和相似度。"""
    vec = embed_one(question)
    vec_str = "[" + ",".join(str(x) for x in vec) + "]"
    with psycopg.connect(DB_DSN) as conn:
        with conn.cursor() as cur:
            # <=> 是 pgvector 的余弦距离算子；1 - 距离 = 相似度（越接近 1 越相关）。
            cur.execute(
                "SELECT content, 1 - (embedding <=> %s::vector) AS similarity "
                "FROM chunks ORDER BY embedding <=> %s::vector LIMIT %s",
                (vec_str, vec_str, top_k))
            rows = cur.fetchall()
    return [{"content": c, "similarity": round(float(s), 4)} for c, s in rows]


# ===== 混合检索：关键词通道 + RRF 融合 =====
# 说明：当前线上 main.py 仍用纯向量 retrieve（见其顶部导入）。
# 下面两个函数是"待启用"的第二路检索，已写好并验证；要接进线上时，
# 在 main.py 把 `from app.rag import retrieve` 换成 `from app.rag import retrieve_hybrid as retrieve` 即可。

def retrieve_keyword(question, top_k=10):
    """关键词通道：按中文字符二元组（bigram）重叠度打分，无需额外依赖。"""
    def bigrams(s):
        s = "".join(c for c in s if c.strip())
        return {s[i:i + 2] for i in range(len(s) - 1)}

    qg = bigrams(question)
    with psycopg.connect(DB_DSN) as conn:
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
    for q in ["退款多久到账？", "怎么开发票"]:
        print("问题:", q)
        for i, r in enumerate(retrieve(q), 1):
            print(f"  [{i}] 相似度 {r['similarity']:.3f} | {r['content'][:40]}")
    # 【待启用】想看混合检索效果时，取消下面注释（或把上面的 retrieve 临时换成 retrieve_hybrid）：
    # print("\n--- 混合检索 RRF 结果 ---")
    # for i, r in enumerate(retrieve_hybrid("退款多久到账？"), 1):
    #     print(f"  [{i}] rrf={r['rrf']} sim={r['similarity']} | {r['content'][:40]}")
