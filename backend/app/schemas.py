"""请求 / 响应数据模型。

统一响应壳 ApiResponse：{ code, message, data }
- 成功：code=0，message="success"，data 为业务数据；
- 失败：code=HTTP 状态码，message 为错误描述，data=null。
前端据此做单一的成功/失败判定，避免字段歧义。
"""
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class LoginRequest(BaseModel):
    """登录请求体：用户名与密码均必填，Pydantic 自动校验缺失/空值（422）。"""

    username: str = Field(..., min_length=1, description="用户名")
    password: str = Field(..., min_length=1, description="密码")


class UserInfo(BaseModel):
    """返回给前端的用户信息（不含密码哈希）。"""

    id: int
    username: str
    nickname: str
    role: str


class LoginResult(BaseModel):
    """登录成功返回的业务数据：JWT 令牌 + 用户信息。"""

    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class ApiResponse(BaseModel, Generic[T]):
    """全接口统一响应壳。"""

    code: int = 0
    message: str = "success"
    data: T | None = None
