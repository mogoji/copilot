"""密码哈希与 JWT 令牌工具。

- 密码使用 bcrypt 哈希（自带随机盐），不直接存明文；
- 访问令牌使用 JWT（HS256），payload 含 sub/role/iat/exp；
- 密钥与过期时间来自 app.config，生产环境务必通过 .env 覆盖 JWT_SECRET_KEY。
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app import config


def hash_password(plain: str) -> str:
    """对明文密码做 bcrypt 哈希，返回可存库的字符串。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码是否匹配已存哈希；哈希非法时返回 False 而非抛错。"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject: str, role: str = "user", extra: dict | None = None
) -> str:
    """签发 JWT access token。subject 通常是用户名。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """解析并校验 JWT；过期或非法会抛 jwt.PyJWTError，由调用方处理。"""
    return jwt.decode(
        token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM]
    )
