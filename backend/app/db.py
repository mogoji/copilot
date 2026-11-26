"""共享数据库连接池。

把连接池从 rag.py 抽到这里，供 RAG 检索与用户认证等模块共用，
避免每个模块各自维护一份池。池为延迟初始化（lazy），import 时不连库；
应用停止时调用 close() 释放。

注意：保持同步 psycopg + ConnectionPool（不依赖事件循环类型），
在 Windows + uvicorn（默认 ProactorEventLoop）下可正常工作。
"""
import logging

from psycopg_pool import ConnectionPool

from app import config

logger = logging.getLogger("app.db")

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """获取（必要时创建）共享连接池，线程安全，可跨 to_thread 工作线程复用。"""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            config.DB_DSN,
            min_size=config.DB_POOL_MIN,
            max_size=config.DB_POOL_MAX,
        )
        logger.info(
            "DB 连接池已打开 min=%s max=%s", config.DB_POOL_MIN, config.DB_POOL_MAX
        )
    return _pool


def close() -> None:
    """关闭连接池，释放资源（应用停止 / 脚本结束时调用）。"""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
        logger.info("DB 连接池已关闭")
