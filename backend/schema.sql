-- =====================================================================
-- 售后客服助手 数据库初始化脚本
-- 用法（新建空库后执行）：
--   psql -d copilot -f backend/schema.sql
-- 或在 Python 里：
--   psycopg.connect(DSN).execute(open("schema.sql").read())
-- =====================================================================

-- 1. 启用 pgvector 扩展（用于向量相似度检索）
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. 文档表：一个 FAQ / 知识条目对应一行
DROP TABLE IF EXISTS chunks CASCADE;   -- 先删子表（有外键）
DROP TABLE IF EXISTS documents;

CREATE TABLE documents (
    id          SERIAL PRIMARY KEY,
    title       TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'synthetic-faq',   -- 数据来源标记
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. 切片表：一个文档可以有多个切片（chunk_index 区分）；
--    本项目 FAQ 场景一条文档对应一个切片（chunk_index=0）
CREATE TABLE chunks (
    id           SERIAL PRIMARY KEY,
    doc_id       INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index  INTEGER NOT NULL,
    content      TEXT NOT NULL,
    -- 维度需与 embedding 模型一致（embedding-3 默认 1024）
    embedding    vector(1024) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 4. HNSW 向量索引（加速余弦相似度检索）
--    vector_cosine_ops 对应 pgvector 的 <=> 距离算子
CREATE INDEX chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops);

-- 如需按 doc_id 快速查某文档所有切片（常规列表/清理场景），加 btree 索引：
CREATE INDEX IF NOT EXISTS chunks_doc_id_idx ON chunks (doc_id);

-- 5. 用户表：后台登录账号（密码存 bcrypt 哈希，不存明文）
--    应用启动时 auth.ensure_admin_seed() 会自动 CREATE TABLE IF NOT EXISTS
--    并写入演示管理员 admin / admin123；这里保留建表语句供全新部署参考。
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(64) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    nickname      VARCHAR(64) NOT NULL DEFAULT '',
    role          VARCHAR(32) NOT NULL DEFAULT 'user',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS users_username_idx ON users (username);

-- =====================================================================
-- 6. 知识库导入任务表：一次上传对应一条任务，记录进度与结果
--    应用启动时 kb.ensure_tables() 也会幂等建表，这里保留供全新部署参考。
-- =====================================================================
CREATE TABLE IF NOT EXISTS kb_import_jobs (
    id             SERIAL PRIMARY KEY,
    filename       TEXT NOT NULL,
    stored_path    TEXT NOT NULL,
    file_size      BIGINT NOT NULL DEFAULT 0,
    ext            VARCHAR(16) NOT NULL,
    status         VARCHAR(16) NOT NULL DEFAULT 'pending',  -- pending/processing/success/failed
    stage          VARCHAR(16) NOT NULL DEFAULT 'queued',   -- queued/parsing/chunking/embedding/writing
    progress       INTEGER NOT NULL DEFAULT 0,
    total_chunks   INTEGER NOT NULL DEFAULT 0,
    success_chunks INTEGER NOT NULL DEFAULT 0,
    failed_chunks  INTEGER NOT NULL DEFAULT 0,
    error_detail   TEXT NOT NULL DEFAULT '',
    operator       VARCHAR(64) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at     TIMESTAMPTZ,
    finished_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS kb_import_jobs_created_idx
    ON kb_import_jobs (created_at DESC);

-- 7. 知识库审计日志：导入 / 重试 / 完成 / 失败等关键操作留痕
CREATE TABLE IF NOT EXISTS kb_audit_logs (
    id         SERIAL PRIMARY KEY,
    operator   VARCHAR(64) NOT NULL,
    action     VARCHAR(32) NOT NULL,
    target     TEXT NOT NULL DEFAULT '',
    detail     TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS kb_audit_logs_created_idx
    ON kb_audit_logs (created_at DESC);
