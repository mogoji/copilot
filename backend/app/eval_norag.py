"""no-RAG 对照组：不检索、不给证据，直接让通用模型回答同一套 70 条用例。

用途：用差值证明 RAG 的真实增益，而不是"RAG 看起来更高级"。

对照组怎么设才公平——三个必须对齐、一个必须不同：
  对齐：同一套 70 条用例、同一个模型（glm-5.3-flash）、同一个命中判定器；
  不同：system prompt 里**不能**保留"只根据资料回答、没有就说不知道"，
        否则它只是"检索为空的 RAG"，仍然会拒答，测不出任何增益。
        这里给的是通用客服人设 + 允许结合行业常识作答，
        这才是"一个没有知识库的客服机器人"真实的样子。

本脚本不走 /chat/stream——那条链路必然先检索，无法关掉检索。
它直接调上游 GLM，其余口径（模型、判定、用例）与 eval_e2e 保持一致，
因此两边数字可以并排比较。

运行（backend 根目录）：
    uv run python -m app.eval_norag
"""
import json
import os
import sys
from pathlib import Path

import httpx

from app import config
from app.eval_e2e import is_hit

CASES = Path(__file__).resolve().parent / "data" / "eval.jsonl"

# 对照组人设：普通电商客服，允许用常识补细节——不喂资料、也不要求它承认不知道
SYSTEM = (
    "你是一名电商售后客服，负责解答用户关于订单、退款、物流、发票、会员、"
    "支付等售后问题。请直接、简洁地回答，可以结合行业通用做法补充细节。"
)


def ask(q: str) -> str:
    """直接问上游模型，不带任何检索证据。"""
    payload = {
        "model": config.GLM_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": q},
        ],
    }
    r = httpx.post(config.GLM_URL, headers=config.HEADERS, json=payload, timeout=90)
    r.raise_for_status()
    choices = r.json().get("choices") or []
    if not choices:
        return ""
    return (choices[0].get("message") or {}).get("content") or ""


def evaluate() -> dict:
    cases = [json.loads(l) for l in open(CASES, encoding="utf-8") if l.strip()]
    hit_ok = hit_total = rej_ok = rej_total = 0
    failures = []
    for i, c in enumerate(cases, 1):
        ans = ask(c["q"])
        # 进度打到 stderr，避免污染 stdout 的 JSON（本组约 17 分钟，需要看得见进展）
        if i % 10 == 0 or i == len(cases):
            print(f"  [{i}/{len(cases)}] {c['q'][:20]}", file=sys.stderr)
        if c["expect"] in ("hit", "boundary"):
            hit_total += 1
            gold = c.get("gold", "")
            if is_hit(gold, ans):
                hit_ok += 1
            else:
                failures.append(
                    {"q": c["q"], "type": "未命中", "gold": gold, "ans": ans[:80]}
                )
        else:
            rej_total += 1
            # 与 eval_e2e 同一口径：说了"没有相关信息"或让用户找人工，才算拒答
            if "没有相关信息" in ans or "联系人工客服" in ans:
                rej_ok += 1
            else:
                failures.append(
                    {"q": c["q"], "type": "该拒未拒（编造）", "ans": ans[:120]}
                )
    return {
        "mode": "no-rag（无检索、无拒答约束）",
        "n": len(cases),
        "answer_hit_rate": round(hit_ok / hit_total, 3) if hit_total else 0,
        # 对照组不存在引用机制与 sources，这两项照实为 0，比较时应视为 N/A
        "citation_rate": 0.0,
        "reject_rate": round(rej_ok / rej_total, 3) if rej_total else 0,
        "reject_avg_sources": 0.0,
        "failures": failures,
    }


if __name__ == "__main__":
    result = evaluate()
    # 可选：把完整结果（含失败明细）落盘，便于与 RAG 组对齐比较、事后回溯。
    # 用环境变量而不是 argv——argv 已经被 eval_e2e 的阈值约定占用过。
    out = os.getenv("EVAL_OUT")
    if out:
        Path(out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"结果已写入 {out}", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
