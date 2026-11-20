"""验证 GLM embedding-3 接口能否返回 1024 维向量。"""
import os, httpx
from dotenv import load_dotenv
load_dotenv()

url = "https://open.bigmodel.cn/api/paas/v4/embeddings"
headers = {
    "Authorization": f"Bearer {os.getenv('GLM_API_KEY')}",
    "Content-Type": "application/json",
}
payload = {"model": "embedding-3", "input": "how to request a refund", "dimensions": 1024}
r = httpx.post(url, headers=headers, json=payload, timeout=30)
d = r.json()
if "data" not in d:
    print("ERROR:", d)
else:
    vec = d["data"][0]["embedding"]
    print("维度:", len(vec), "| 前3个:", [round(x, 4) for x in vec[:3]])