"""共享数据库连接池与数据库探活。

把连接池从 rag.py 抽到这里，供 RAG 检索与用户认证等模块共用，
避免每个模块各自维护一份池。池为延迟初始化（lazy），import 时不连库；
应用停止时调用 close() 释放，健康检查通过 probe() 真正打一次库。

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
            # 每次从池里取连接时校验其仍然可用：数据库重启/网络闪断后，
            # 池里残留的旧连接是坏的，没有这层校验第一个请求会直接报错。
            # 代价是每次取连接多一次空查询往返（本地库 <1ms，低 QPS 可忽略）。
            check=ConnectionPool.check_connection,
            # 显式 open：池在后台线程里建连，不在 import/启动阶段阻塞事件循环
            open=True,
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


def probe(timeout: float = 2.0) -> dict:
    """探一次数据库：能否取到连接 + chunks 表是否存在。

    只做两件极轻的操作（SELECT 1 与 to_regclass 查表是否存在），
    不做 count(*) 之类的全表扫描，保证高频探针不给库增加负担。

    timeout 限制「从池里取连接」的等待时间：库挂掉时探针要快速失败，
    而不是排到池的默认 30s 超时、把健康检查请求一起拖死。
    """
    with get_pool().connection(timeout=timeout) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
            # to_regclass 对不存在的对象返回 NULL 而不是抛错，适合做探针
            cur.execute("SELECT to_regclass('public.chunks') IS NOT NULL")
            has_chunks = bool(cur.fetchone()[0])
    return {"has_chunks": has_chunks}

