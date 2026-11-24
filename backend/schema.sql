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
