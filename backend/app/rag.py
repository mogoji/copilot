"""RAG 核心：把问题向量化，去 pgvector 检索最相关的切片。"""
import os, httpx, psycopg
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


if __name__ == "__main__":
    for q in ["退款多久到账？", "怎么开发票"]:
        print("问题:", q)
        for i, r in enumerate(retrieve(q), 1):
            print(f"  [{i}] 相似度 {r['similarity']:.3f} | {r['content'][:40]}")
