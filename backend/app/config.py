"""集中配置：所有外部地址、模型参数、阈值、数据库连接统一从这里读取。

各模块只应从本文件取配置，不要再各自硬编码 URL / 密钥 / DSN。
必需的环境变量缺失时，本模块在被导入时立即抛错（fail-fast），
避免请求运行时才出现难以定位的 401 / 连接失败。
"""
import os

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

# ---- 检索阈值 ----
# 证据阈值：低于此相似度的检索结果不喂给模型（防幻觉第一道闸）。
EVIDENCE_TH = float(os.getenv("EVIDENCE_TH", "0.60"))

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

# ---- CORS ----
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]


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
