"""把 faq.json 切片、向量化，灌进 pgvector。可重复执行（先清空再入库）。

运行方式（backend 根目录）：
    python -m app.ingest
"""
import json
from pathlib import Path

import httpx
import psycopg

from app import config

EMBED_BATCH_SIZE = 32  # 单请求安全上限约 64，留余量；数据量大时自动分批


def _vec_str(vec) -> str:
    """把浮点向量转成 pgvector 接受的字符串格式 [0.1,0.2,...]。"""
    return "[" + ",".join(str(x) for x in vec) + "]"


def embed(texts):
    """调 embedding 接口批量向量化，返回与输入等长的向量列表。

    超过 EMBED_BATCH_SIZE 时自动分批请求，结果按输入顺序拼接。
    """
    all_vecs: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i:i + EMBED_BATCH_SIZE]
        r = httpx.post(
            config.EMB_URL,
            headers=config.HEADERS,
            json={
                "model": config.EMBEDDING_MODEL,
                "input": batch,
                "dimensions": config.EMBEDDING_DIMENSIONS,
            },
            timeout=config.HTTP_TIMEOUT,
        )
        d = r.json()
        if "data" not in d:
            raise RuntimeError(f"embedding 失败 (batch {i // EMBED_BATCH_SIZE}): {d}")
        ordered = sorted(d["data"], key=lambda x: x["index"])
        all_vecs.extend(item["embedding"] for item in ordered)
        print(f"  embedding batch {i // EMBED_BATCH_SIZE + 1} "
              f"({len(batch)} 条) 完成")
    return all_vecs


def main():
    # 数据文件路径：基于脚本位置，无论从哪个 cwd 运行都能找到
    faq_path = Path(__file__).resolve().parent / "data" / "faq.json"
    faqs = json.load(open(faq_path, encoding="utf-8"))

    # 每条 FAQ 拼成一个切片（Q + A 一起向量化，检索时更容易命中问题）
    texts = [f"问：{f['q']}\n答：{f['a']}" for f in faqs]
    print(f"共 {len(texts)} 条切片，开始向量化...")
    vectors = embed(texts)

    # 整个 TRUNCATE + INSERT 流程包在一个事务里，中途失败自动回滚
    with psycopg.connect(config.DB_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE chunks, documents RESTART IDENTITY CASCADE")
            for f, text, vec in zip(faqs, texts, vectors):
                cur.execute(
                    "INSERT INTO documents(title, source) VALUES (%s, %s) RETURNING id",
                    (f["q"], "synthetic-faq"),
                )
                doc_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO chunks(doc_id, chunk_index, content, embedding) "
                    "VALUES (%s, %s, %s, %s::vector)",
                    (doc_id, 0, text, _vec_str(vec)),
                )
    print("灌库完成:", len(texts), "条")


if __name__ == "__main__":
    main()