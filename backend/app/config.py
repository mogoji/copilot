"""集中配置：所有外部地址、模型参数、阈值、数据库连接统一从这里读取。

各模块只应从本文件取配置，不要再各自硬编码 URL / 密钥 / DSN。
必需的环境变量缺失时，本模块在被导入时立即抛错（fail-fast），
避免请求运行时才出现难以定位的 401 / 连接失败。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---- 上游模型服务 ----
GLM_API_KEY = os.getenv("GLM_API_KEY", "")
GLM_URL = os.getenv(
    "GLM_URL", "https://open.bigmodel.cn/api/paas/v4/chat/completions"
)
EMB_URL = os.getenv("EMB_URL", "https://open.bigmodel.cn/api/paas/v4/embeddings")
GLM_MODEL = os.getenv("GLM_MODEL", "glm-5.3-flash")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "embedding-3")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))

# embedding 与 chat 共用的请求头（鉴权 + 内容类型）
HEADERS = {
    "Authorization": f"Bearer {GLM_API_KEY}",
    "Content-Type": "application/json",
}

# ---- RAG 开关 ----
# true（默认）：检索知识库，把达到阈值的证据喂给模型并返回引用来源；
# false：完全跳过检索，直接让模型凭自身知识回答，用于与 RAG 效果做对照。
# 关闭后 /chat/stream 不访问数据库，DB 不可用时也能正常对话（仅 /health 仍会探库）。
ENABLE_RAG = os.getenv("ENABLE_RAG", "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# ---- 检索阈值 ----
# 证据阈值：低于此相似度的检索结果不喂给模型（防幻觉第一道闸）。
EVIDENCE_TH = float(os.getenv("EVIDENCE_TH", "0.60"))
# 客户端可通过 evidence_th 传入阈值，但会被 clamp 到 [MIN, MAX]，
# 防止传 0 绕过拒答防线、喂入低质量证据导致幻觉。
# 如需复现 0.35 基线评测，可临时把 EVIDENCE_TH_MIN 调低（例如 0.3）。
EVIDENCE_TH_MIN = float(os.getenv("EVIDENCE_TH_MIN", "0.40"))
EVIDENCE_TH_MAX = float(os.getenv("EVIDENCE_TH_MAX", "0.85"))

# ---- 超时（秒） ----
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "60"))
EMBED_TIMEOUT = float(os.getenv("EMBED_TIMEOUT", "30"))

# ---- 数据库 ----
# 优先使用完整 DATABASE_URL；未提供时用各分量拼装（host/port/dbname/user
# 给本地默认值，密码必须来自环境变量，不再硬编码进源码）。
DB_DSN = os.getenv("DATABASE_URL") or (
    f"host={os.getenv('DB_HOST', 'localhost')} "
    f"port={os.getenv('DB_PORT', '5432')} "
    f"dbname={os.getenv('DB_NAME', 'copilot')} "
    f"user={os.getenv('DB_USER', 'copilot')} "
    f"password={os.getenv('DB_PASSWORD', '')}"
)

# ---- 数据库连接池 ----
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))

# ---- 知识库导入 ----
# 单文件大小上限（MB），超限直接 413 拦截
KB_MAX_FILE_MB = int(os.getenv("KB_MAX_FILE_MB", "10"))
# 分片长度（字符）与相邻分片重叠长度：按段落聚合，超长段落再按滑动窗口切
KB_CHUNK_SIZE = int(os.getenv("KB_CHUNK_SIZE", "500"))
KB_CHUNK_OVERLAP = int(os.getenv("KB_CHUNK_OVERLAP", "50"))
# 上传文件落盘目录：默认 backend/storage/kb（已 gitignore）
KB_STORAGE_DIR = os.getenv(
    "KB_STORAGE_DIR", str(Path(__file__).resolve().parent.parent / "storage" / "kb")
)

# ---- CORS ----
# 前端 dev server 可能用 localhost 或 127.0.0.1，默认两者都放行；
# 生产环境通过 ALLOWED_ORIGINS 覆盖为真实前端域名。
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]

# ---- JWT ----
# 未配置时使用开发默认密钥并打印告警；生产环境务必通过 .env 覆盖。
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if not JWT_SECRET_KEY:
    import sys

    JWT_SECRET_KEY = "dev-only-insecure-secret-change-me-please"
    print(
        "WARNING: JWT_SECRET_KEY 未设置，正在使用不安全的开发默认密钥，"
        "生产环境务必通过 .env 覆盖！",
        file=sys.stderr,
    )
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))


def clamp_evidence_th(value: float | None) -> float:
    """把阈值限制在 [EVIDENCE_TH_MIN, EVIDENCE_TH_MAX] 安全范围内。"""
    base = EVIDENCE_TH if value is None else float(value)
    return max(EVIDENCE_TH_MIN, min(EVIDENCE_TH_MAX, base))


def validate() -> None:
    """校验必需配置，缺失则立即抛错，避免运行时才暴露问题。"""
    missing = []
    if not GLM_API_KEY:
        missing.append("GLM_API_KEY")
    if not (os.getenv("DATABASE_URL") or os.getenv("DB_PASSWORD")):
        missing.append("DATABASE_URL（或 DB_PASSWORD）")
    if missing:
        raise RuntimeError(
            "缺少必需的环境变量: " + ", ".join(missing) + "。请在 .env 中配置（参考 .env.example）。"
        )


# 导入即校验：任何引用本配置的模块启动时都会 fail-fast。
validate()
