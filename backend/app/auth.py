"""认证模块：用户表维护 + 登录接口。

- users 表与现有 documents/chunks 表共用同一个 Postgres 库与连接池；
- 应用启动时 ensure_admin_seed() 幂等建表并写入演示管理员账号
  （admin / admin123），与前端登录页展示的演示账号保持一致；
- 登录成功签发 JWT；失败抛 HTTPException(401)，由 main.py 的全局
  异常处理器统一包装成 { code, message, data } 响应壳。
"""
import logging

from fastapi import APIRouter, HTTPException

from app.db import get_pool
from app.schemas import ApiResponse, LoginRequest, LoginResult, UserInfo
from app.security import create_access_token, hash_password, verify_password

logger = logging.getLogger("app.auth")

router = APIRouter(prefix="/api/auth", tags=["认证"])

# 演示种子账号（与前端登录页"演示账号"文案一致，单一真源）
SEED_ADMIN_USERNAME = "admin"
SEED_ADMIN_PASSWORD = "admin123"
SEED_ADMIN_NICKNAME = "系统管理员"
SEED_ADMIN_ROLE = "admin"

_CREATE_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(64) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    nickname      VARCHAR(64) NOT NULL DEFAULT '',
    role          VARCHAR(32) NOT NULL DEFAULT 'user',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _row_to_user(row) -> UserInfo:
    """把数据库行映射为 UserInfo（丢弃 password_hash）。
    行顺序：id, username, password_hash, nickname, role。"""
    return UserInfo(id=row[0], username=row[1], nickname=row[3], role=row[4])


def get_user_with_password(username: str) -> tuple[UserInfo, str] | None:
    """按用户名查用户，返回 (UserInfo, password_hash)；不存在返回 None。"""
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, password_hash, nickname, role "
                "FROM users WHERE username = %s",
                (username,),
            )
            row = cur.fetchone()
    if not row:
        return None
    return _row_to_user(row), row[2]


def ensure_admin_seed() -> None:
    """确保 users 表存在且至少有一个可登录管理员（幂等）。

    同步函数：由 main.py 在 lifespan 中通过 asyncio.to_thread 调用，
    避免阻塞事件循环。
    """
    pwd_hash = hash_password(SEED_ADMIN_PASSWORD)
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_USERS_TABLE_SQL)
            cur.execute(
                "INSERT INTO users (username, password_hash, nickname, role) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (username) DO NOTHING",
                (
                    SEED_ADMIN_USERNAME,
                    pwd_hash,
                    SEED_ADMIN_NICKNAME,
                    SEED_ADMIN_ROLE,
                ),
            )
        conn.commit()
    logger.info("users 表与种子管理员账号已就绪（%s）", SEED_ADMIN_USERNAME)


@router.post("/login", response_model=ApiResponse[LoginResult])
def login(req: LoginRequest) -> ApiResponse[LoginResult]:
    """登录：校验账号密码，成功返回 JWT。"""
    username = req.username.strip()
    found = get_user_with_password(username)
    if not found or not verify_password(req.password, found[1]):
        # 账号不存在与密码错误返回相同提示，避免用户名枚举
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    user = found[0]
    token = create_access_token(
        subject=user.username, role=user.role, extra={"uid": user.id}
    )
    return ApiResponse(
        data=LoginResult(access_token=token, token_type="bearer", user=user)
    )
