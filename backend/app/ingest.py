"""把 faq.json 切片、向量化，灌进 pgvector。可重复执行（先清空再入库）。"""
import os, json, httpx, psycopg
from dotenv import load_dotenv
load_dotenv()

EMB_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
HEADERS = {"Authorization": f"Bearer {os.getenv('GLM_API_KEY')}", "Content-Type": "application/json"}
DB_DSN = "host=localhost port=5432 dbname=copilot user=copilot password=copilot123"

def embed(texts):
    """调 embedding-3 批量向量化，返回向量列表。"""
    r = httpx.post(EMB_URL, headers=HEADERS,
                   json={"model": "embedding-3", "input": texts, "dimensions": 1024}, timeout=60)
    d = r.json()
    if "data" not in d:
        raise RuntimeError(f"embedding 失败: {d}")
    return [item["embedding"] for item in sorted(d["data"], key=lambda x: x["index"])]

def main():
    faqs = json.load(open("app/data/faq.json", encoding="utf-8"))
    # 每条 FAQ 拼成一个切片（Q + A 一起向量化，检索时更容易命中问题）
    texts = [f"问：{f['q']}\n答：{f['a']}" for f in faqs]
    print(f"共 {len(texts)} 条切片，开始向量化...")
    vectors = embed(texts)  # 20 条一次请求够用；量大时要分批（单请求上限约64条）

    with psycopg.connect(DB_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE chunks, documents RESTART IDENTITY CASCADE")
            for f, text, vec in zip(faqs, texts, vectors):
                cur.execute("INSERT INTO documents(title, source) VALUES (%s, %s) RETURNING id",
                            (f["q"], "synthetic-faq"))
                doc_id = cur.fetchone()[0]
                # 向量转成 pgvector 接受的字符串格式 [0.1,0.2,...]
                vec_str = "[" + ",".join(str(x) for x in vec) + "]"
                cur.execute(
                    "INSERT INTO chunks(doc_id, chunk_index, content, embedding) "
                    "VALUES (%s, %s, %s, %s::vector)",
                    (doc_id, 0, text, vec_str))
        conn.commit()
    print("灌库完成:", len(texts), "条")

if __name__ == "__main__":
    main()