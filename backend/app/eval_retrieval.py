"""检索层评测：只测 retrieve，不调 GLM，快且省钱。

运行方式（backend 根目录）：
    python -m app.eval_retrieval
"""
import json
from pathlib import Path

from app import config
from app.rag import retrieve

def load_cases(path=None):
    # 同样用基于脚本位置的绝对路径，避免换目录运行时找不到文件。
    path = path or (Path(__file__).resolve().parent / "data" / "eval.jsonl")
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]

def evaluate(top_k=5, reject_th=None):
    # 拒答阈值默认取 config.EVIDENCE_TH，与线上检索证据阈值保持单一来源；
    # 需要复现历史基线时仍可显式传参覆盖。
    reject_th = config.EVIDENCE_TH if reject_th is None else reject_th
    cases = load_cases()
    # hit_ok 命中数、hit_total 应命中总数
    # rej_ok 拒答数、rej_total 应拒答数
    hit_ok = hit_total = rej_ok = rej_total = 0
    rr_sum = 0.0
    for c in cases:
        hits = retrieve(c["q"], top_k=top_k)
        texts = [h["content"] for h in hits]
        # 获取最高相似度
        top_score = hits[0]["similarity"] if hits else 0.0
        if c["expect"] in ("hit", "boundary"):
            hit_total += 1
            gold = c.get("gold", "")
            # 取第一个命中的名次
            rank = next((i + 1 for i, t in enumerate(texts) if gold in t), None)
            if rank:
                hit_ok += 1
                # 命中得分
                rr_sum += 1.0 / rank
        else:  # reject
            rej_total += 1
            if top_score < reject_th:   # top1 相似度小于拒答阈值，拒答数+1
                rej_ok += 1
    return {
        "n": len(cases),
        "recall@5": round(hit_ok / hit_total, 3) if hit_total else 0, # 召回率
        "mrr": round(rr_sum / hit_total, 3) if hit_total else 0, #  平均命中得分
        "retrievable_reject": round(rej_ok / rej_total, 3) if rej_total else 0, #可拒答率
    }

if __name__ == "__main__":
    from app import rag

    try:
        print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
    finally:
        rag.close()