"""鉴权依赖：从 `Authorization: Bearer <token>` 中解析当前登录用户。

设计要点：
- 统一用 HTTPBearer 取令牌，`auto_error=False` 让缺令牌时由我们自己抛 401
  （FastAPI 默认抛 403，语义上容易与"无权限"混淆）；
- 令牌校验完全复用 security.decode_token，签名/过期异常统一转 401；
- 依赖返回 JWT payload（含 sub/role/uid），需要用户详情时再查库。

用途：任何"会产生上游费用"的接口（如 /chat/stream 会调用 GLM）都必须挂
`Depends(get_current_user)`，否则等于把 API Key 公开给全网。
"""
import logging

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.security import decode_token

logger = logging.getLogger("app.deps")

# auto_error=False：缺少 Authorization 头时不自动抛错，交给下面统一处理
_bearer = HTTPBearer(auto_error=False, description="登录接口返回的 access_token")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """校验 Bearer 令牌并返回 payload；未登录/过期/伪造统一 401。"""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未登录或登录已过期，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None or not credentials.credentials:
        raise unauthorized

    try:
        payload = decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        logger.info("令牌已过期")
        raise unauthorized
    except jwt.PyJWTError as exc:
        # 不把底层异常细节返回给客户端，避免泄露签名校验信息
        logger.warning("令牌校验失败: %s", exc)
        raise unauthorized

    if not payload.get("sub"):
        raise unauthorized
    return payload
