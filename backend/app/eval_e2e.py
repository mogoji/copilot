"""端到端评测：走 /chat/stream，检查命中/引用/拒答，并统计拒答时的 sources 数。

【鉴权说明】/chat/stream 需要登录（Authorization: Bearer <token>）。
本脚本先用演示账号登录换取 token，再逐条评测。
账号可用环境变量覆盖：EVAL_USERNAME / EVAL_PASSWORD。
"""
import json
import os
import sys

import httpx

BASE = "http://localhost:8000"
URL = f"{BASE}/chat/stream"
LOGIN_URL = f"{BASE}/api/auth/login"

# 演示账号：与 backend/app/auth.py 的种子账号保持一致，可用环境变量覆盖
USERNAME = os.getenv("EVAL_USERNAME", "admin")
PASSWORD = os.getenv("EVAL_PASSWORD", "admin123")

# 【Day3 步骤6】阈值可从命令行传入，便于对比 0.35（基线）vs 0.60（优化）：
#   uv run python app/eval_e2e.py 0.35
#   uv run python app/eval_e2e.py 0.60
TH = float(sys.argv[1]) if len(sys.argv) > 1 else None


def login() -> str:
    """登录换取 JWT；失败直接抛错，避免后续 55 条全部静默拿 401。"""
    r = httpx.post(
        LOGIN_URL, json={"username": USERNAME, "password": PASSWORD}, timeout=15
    )
    if r.status_code != 200:
        raise RuntimeError(f"登录失败（{r.status_code}）：{r.text[:200]}")
    return r.json()["data"]["access_token"]


def ask(q, token, th=None):
    answer, sources = "", []
    payload = {"q": q}
    if th is not None:
        payload["evidence_th"] = th
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.stream(
        "POST", URL, json=payload, headers=headers, timeout=90
    ) as r:
        if r.status_code != 200:
            r.read()
            raise RuntimeError(f"接口返回 {r.status_code}：{r.text[:200]}")
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                d = json.loads(data)
            except json.JSONDecodeError:
                continue
            if "sources" in d:
                sources = d["sources"]
            elif "token" in d:
                answer += d["token"]
    return answer, sources


def evaluate(th=None, token=None):
    from pathlib import Path
    path = Path(__file__).resolve().parent / "data" / "eval.jsonl"
    cases = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    if token is None:
        token = login()
    hit_ok = hit_total = cit_ok = rej_ok = rej_total = 0
    rej_sources_sum = 0          # 【Day3 步骤6】拒答类携带的 sources 总数（伪证据计数）
    for c in cases:
        ans, src = ask(c["q"], token, th=th)
        if c["expect"] in ("hit", "boundary"):
            hit_total += 1
            gold = c.get("gold", "")
            if gold in ans:                      # 回答内容对不对
                hit_ok += 1
            if "[1]" in ans or "[2]" in ans:     # 有没有标引用
                cit_ok += 1
        else:
            rej_total += 1
            rej_sources_sum += len(src)          # 记录拒答时塞了多少条伪证据
            if "没有相关信息" in ans or "联系人工客服" in ans:
                rej_ok += 1
    return {
        "evidence_th": th if th is not None else "default(0.60)",
        "n": len(cases),
        "answer_hit_rate": round(hit_ok / hit_total, 3) if hit_total else 0,
        "citation_rate": round(cit_ok / hit_total, 3) if hit_total else 0,
        "reject_rate": round(rej_ok / rej_total, 3) if rej_total else 0,
        "reject_avg_sources": round(rej_sources_sum / rej_total, 2) if rej_total else 0,
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(TH), ensure_ascii=False, indent=2))
