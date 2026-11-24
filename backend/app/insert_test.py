# 1、读取文件
# 2、切片
# 3、存入数据库

# 文本向量化
import json

import httpx,os
from dotenv import load_dotenv
import psycopg
load_dotenv()

DB = "host=localhost port=5432 dbname=copilot user=copilot password=copilot123"
def embed(text):
    url = "https://open.bigmodel.cn/api/paas/v4/embeddings"
    ployad = {
        "model": "embedding-3",
        "input": text,
        "dimensions": 1024
    }
    headers = {
        "Authorization": f"Bearer {os.getenv('GLM_API_KEY')}",
        "Content-Type": "application/json"
    }
    r =httpx.post(url,headers=headers,json=ployad,timeout=60)
    d = r.json()
    if "data" not in d:
        raise RuntimeError(f"embedding 失败: {d}")
    return [ item['embedding'] for item in sorted(d["data"],key = lambda x:x["index"]) ]

def main():
    faqs = json.load(open("./data/faq.json", encoding="utf-8"))
    texts = [ f"问：{faq["q"]}\n答：{faq["a"]}" for faq in faqs]
    # print(texts,len(texts))
    vectors = embed(texts)
    
    with psycopg.connect(DB) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE chunks, documents RESTART IDENTITY CASCADE")
            for f,text,vec in zip(faqs,texts,vectors):
                cur.execute("INSERT INTO documents(title, source) VALUES (%s, %s) RETURNING id",
                                                (f["q"], "synthetic-faq"))
                doc_id = cur.fetchone()[0]
                vec_str = "[" + ",".join(str(x) for x in vec) + "]"
                cur.execute(
                    "INSERT INTO chunks(doc_id, chunk_index, content, embedding) "
                    "VALUES (%s, %s, %s, %s::vector)",
                    (doc_id, 0, text, vec_str))
        conn.commit()
    
if __name__ == "__main__":
    main()