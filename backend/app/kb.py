"""知识库管理：文件上传 → 解析 → 分片 → 向量化 → 入库，含任务进度、历史与审计。

设计要点：
- 权限：所有接口挂 `Depends(require_admin)`，普通用户直接调接口也会 403；
- 耗时流程放后台线程：接口立即返回 job_id，前端轮询 /api/kb/jobs/{id} 拿进度，
  避免一次 embedding 调用把 HTTP 请求卡住几十秒；
- 写入仍走现有 documents / chunks 表，因此 rag.retrieve 无需任何改动，
  导入完成后即可被智能客服检索命中（替代静态 faq.json 的入库方式）；
- 每个分片独立事务写入：个别分片失败不影响其他分片，便于统计成功/失败条数；
- 关键操作（导入、重试、完成/失败）写入 kb_audit_logs，便于事后追溯。
"""
import io
import logging
import re
import threading
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app import config
from app.db import get_pool
from app.deps import require_admin
from app.schemas import ApiResponse

logger = logging.getLogger("app.kb")

router = APIRouter(prefix="/api/kb", tags=["知识库"])

# 允许导入的格式（与前端 accept 保持一致）
ALLOWED_EXT = {"pdf", "docx", "xlsx", "md"}
EMBED_BATCH_SIZE = 32  # 单次 embedding 请求的分片数

_ZIP_MAGIC = b"PK\x03\x04"  # docx / xlsx 本质是 zip 包

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS kb_import_jobs (
    id             SERIAL PRIMARY KEY,
    filename       TEXT NOT NULL,
    stored_path    TEXT NOT NULL,
    file_size      BIGINT NOT NULL DEFAULT 0,
    ext            VARCHAR(16) NOT NULL,
    status         VARCHAR(16) NOT NULL DEFAULT 'pending',
    stage          VARCHAR(16) NOT NULL DEFAULT 'queued',
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
CREATE TABLE IF NOT EXISTS kb_audit_logs (
    id         SERIAL PRIMARY KEY,
    operator   VARCHAR(64) NOT NULL,
    action     VARCHAR(32) NOT NULL,
    target     TEXT NOT NULL DEFAULT '',
    detail     TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

_JOB_COLUMNS = (
    "id, filename, file_size, ext, status, stage, progress, "
    "total_chunks, success_chunks, failed_chunks, error_detail, operator, "
    "created_at, started_at, finished_at"
)


# --------------------------------------------------------------------------
# 建表 / 数据访问
# --------------------------------------------------------------------------
def ensure_tables() -> None:
    """幂等建表（同步函数，由 lifespan 通过 to_thread 调用）。"""
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_TABLES_SQL)
        conn.commit()
    Path(config.KB_STORAGE_DIR).mkdir(parents=True, exist_ok=True)
    logger.info("知识库任务表与审计表已就绪")


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _row_to_job(row, with_path: bool = False) -> dict:
    job = {
        "id": row[0],
        "filename": row[1],
        "file_size": row[2],
        "ext": row[3],
        "status": row[4],
        "stage": row[5],
        "progress": row[6],
        "total_chunks": row[7],
        "success_chunks": row[8],
        "failed_chunks": row[9],
        "error_detail": row[10],
        "operator": row[11],
        "created_at": _iso(row[12]),
        "started_at": _iso(row[13]),
        "finished_at": _iso(row[14]),
    }
    if with_path:
        job["stored_path"] = row[15]
    return job


def get_job(job_id: int, with_path: bool = False) -> dict | None:
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_JOB_COLUMNS}, stored_path FROM kb_import_jobs WHERE id = %s",
                (job_id,),
            )
            row = cur.fetchone()
    return _row_to_job(row, with_path=with_path) if row else None


def _create_job(filename: str, stored_path: str, size: int, ext: str, operator: str) -> int:
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO kb_import_jobs "
                "(filename, stored_path, file_size, ext, operator) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (filename, stored_path, size, ext, operator),
            )
            job_id = cur.fetchone()[0]
        conn.commit()
    return job_id


def _update_job(job_id: int, **fields) -> None:
    """按白名单字段更新任务；调用方只传内部常量键。"""
    if not fields:
        return
    assignments = ", ".join(f"{key} = %s" for key in fields)
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE kb_import_jobs SET {assignments} WHERE id = %s",
                (*fields.values(), job_id),
            )
        conn.commit()


def _audit(operator: str, action: str, target: str, detail: str = "") -> None:
    """写审计日志；失败只记日志，不影响主流程。"""
    try:
        with get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO kb_audit_logs (operator, action, target, detail) "
                    "VALUES (%s, %s, %s, %s)",
                    (operator, action, target, detail[:2000]),
                )
            conn.commit()
    except Exception:
        logger.exception("写审计日志失败 action=%s target=%s", action, target)


# --------------------------------------------------------------------------
# 文件校验
# --------------------------------------------------------------------------
def _validate_ext(filename: str) -> tuple[str, str]:
    """返回 (安全文件名, 扩展名)；扩展名不在白名单直接 400。"""
    safe_name = Path(filename or "").name.strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    ext = Path(safe_name).suffix.lower().lstrip(".")
    if ext not in ALLOWED_EXT:
        allowed = "、".join(sorted(e.upper() for e in ALLOWED_EXT))
        raise HTTPException(
            status_code=400, detail=f"不支持的文件格式，仅允许：{allowed}"
        )
    return safe_name, ext


def _sniff_content(ext: str, data: bytes) -> None:
    """魔数校验：防止把可执行文件改个后缀就传上来。"""
    if ext == "pdf" and not data.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="文件内容不是有效的 PDF")
    if ext in ("docx", "xlsx") and not data.startswith(_ZIP_MAGIC):
        raise HTTPException(
            status_code=400, detail="文件内容不是有效的 Office 文档（可能已损坏或后缀被篡改）"
        )
    if ext == "md" and b"\x00" in data[:2048]:
        raise HTTPException(status_code=400, detail="Markdown 文件包含二进制内容，已拒绝")


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------
def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise RuntimeError("无法识别文本编码（请另存为 UTF-8 后重试）")


def _parse_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return "\n\n".join(p for p in pages if p)


def _parse_docx(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    # 表格内容按行拼成 "a | b | c"，否则合同/价目表类文档会丢关键信息
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return "\n\n".join(parts)


def _parse_xlsx(data: bytes) -> str:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts: list[str] = []
    try:
        for sheet in workbook.worksheets:
            parts.append(f"# 工作表：{sheet.title}")
            for row in sheet.iter_rows(values_only=True):
                cells = [str(v).strip() for v in row if v is not None and str(v).strip()]
                if cells:
                    parts.append(" | ".join(cells))
    finally:
        workbook.close()
    return "\n\n".join(parts)


def parse_file(ext: str, data: bytes) -> str:
    if ext == "pdf":
        return _parse_pdf(data)
    if ext == "docx":
        return _parse_docx(data)
    if ext == "xlsx":
        return _parse_xlsx(data)
    return _decode_text(data)


# --------------------------------------------------------------------------
# 分片
# --------------------------------------------------------------------------
def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """按语义段落聚合分片；超长段落用滑动窗口切，保留 overlap 字符上下文。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buffer = ""

    for paragraph in paragraphs:
        if len(paragraph) > size:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            step = max(1, size - overlap)
            for start in range(0, len(paragraph), step):
                piece = paragraph[start:start + size]
                if piece.strip():
                    chunks.append(piece)
        elif len(buffer) + len(paragraph) + 2 <= size:
            buffer = f"{buffer}\n\n{paragraph}" if buffer else paragraph
        else:
            chunks.append(buffer)
            buffer = paragraph

    if buffer:
        chunks.append(buffer)
    # 过短碎片（如单个标题）不足以独立检索，直接丢弃
    return [c.strip() for c in chunks if len(c.strip()) >= 10]


# --------------------------------------------------------------------------
# 向量化 + 落库
# --------------------------------------------------------------------------
def _vec_str(vector: list[float]) -> str:
    return "[" + ",".join(str(x) for x in vector) + "]"


def embed_texts(texts: list[str], on_batch_done=None) -> list[list[float]]:
    """同步批量向量化；每批完成回调 on_batch_done(done, total) 用于更新进度。"""
    vectors: list[list[float]] = []
    for offset in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[offset:offset + EMBED_BATCH_SIZE]
        response = httpx.post(
            config.EMB_URL,
            headers=config.HEADERS,
            json={
                "model": config.EMBEDDING_MODEL,
                "input": batch,
                "dimensions": config.EMBEDDING_DIMENSIONS,
            },
            timeout=config.EMBED_TIMEOUT,
        )
        payload = response.json()
        if "data" not in payload:
            raise RuntimeError(f"向量化失败：{str(payload)[:300]}")
        ordered = sorted(payload["data"], key=lambda item: item["index"])
        vectors.extend(item["embedding"] for item in ordered)
        if on_batch_done:
            on_batch_done(min(offset + len(batch), len(texts)), len(texts))
    return vectors


def _persist(job_id: int, filename: str, chunks: list[str], vectors: list[list[float]]):
    """逐片独立事务写入 documents / chunks，返回 (成功数, 失败数, 错误明细)。"""
    success = 0
    failed = 0
    errors: list[str] = []
    source = f"upload:{filename}"[:200]

    for index, (content, vector) in enumerate(zip(chunks, vectors)):
        try:
            with get_pool().connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO documents (title, source) VALUES (%s, %s) "
                        "RETURNING id",
                        (f"{filename} · 片段 {index + 1}", source),
                    )
                    doc_id = cur.fetchone()[0]
                    cur.execute(
                        "INSERT INTO chunks (doc_id, chunk_index, content, embedding) "
                        "VALUES (%s, %s, %s, %s::vector)",
                        (doc_id, 0, content, _vec_str(vector)),
                    )
                conn.commit()
            success += 1
        except Exception as exc:  # 单片失败不影响其余分片
            failed += 1
            errors.append(f"片段 {index + 1}: {type(exc).__name__}: {exc}")

        if (index + 1) % 5 == 0 or index + 1 == len(chunks):
            _update_job(
                job_id,
                progress=min(99, 82 + int(17 * (index + 1) / len(chunks))),
                success_chunks=success,
                failed_chunks=failed,
            )
    return success, failed, errors


# --------------------------------------------------------------------------
# 后台任务
# --------------------------------------------------------------------------
def _run_job(job_id: int) -> None:
    job = get_job(job_id, with_path=True)
    if not job:
        return
    operator = job["operator"]
    filename = job["filename"]

    try:
        # started_at 必须在开跑时落库：否则任务详情里永远显示 null，
        # 无法按 created_at → started_at → finished_at 三段排查排队与处理耗时
        _set_started_now(job_id)
        _update_job(job_id, status="processing", stage="parsing", progress=2)
        raw = Path(job["stored_path"]).read_bytes()
        text = parse_file(job["ext"], raw)
        if not text.strip():
            raise RuntimeError("未能从文件中解析出任何文本内容")

        _update_job(job_id, stage="chunking", progress=10)
        chunks = chunk_text(text, config.KB_CHUNK_SIZE, config.KB_CHUNK_OVERLAP)
        if not chunks:
            raise RuntimeError("分片后没有有效内容，请检查文件正文")
        _update_job(job_id, total_chunks=len(chunks), progress=15)

        _update_job(job_id, stage="embedding")
        vectors = embed_texts(
            chunks,
            on_batch_done=lambda done, total: _update_job(
                job_id, progress=min(80, 15 + int(65 * done / total))
            ),
        )

        _update_job(job_id, stage="writing", progress=82)
        success, failed, errors = _persist(job_id, filename, chunks, vectors)

        status = "success" if success > 0 else "failed"
        detail = "\n".join(errors)[:4000]
        if not detail and failed:
            detail = "存在写入失败的分片"
        _update_job(
            job_id,
            status=status,
            stage=status,
            progress=100,
            success_chunks=success,
            failed_chunks=failed,
            error_detail=detail,
        )
        # finished_at 需要 SQL 的 now()，不能当普通字符串参数传
        _set_finished_now(job_id)
        _audit(
            operator,
            "import_finish",
            filename,
            f"成功 {success} 条，失败 {failed} 条",
        )
    except Exception as exc:
        logger.exception("知识库导入失败 job=%s file=%s", job_id, filename)
        _update_job(
            job_id,
            status="failed",
            stage="failed",
            progress=100,
            error_detail=f"{type(exc).__name__}: {exc}"[:4000],
        )
        _set_finished_now(job_id)
        _audit(operator, "import_fail", filename, f"{type(exc).__name__}: {exc}")


def _set_started_now(job_id: int) -> None:
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE kb_import_jobs SET started_at = now() WHERE id = %s",
                (job_id,),
            )
        conn.commit()


def _set_finished_now(job_id: int) -> None:
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE kb_import_jobs SET finished_at = now() WHERE id = %s",
                (job_id,),
            )
        conn.commit()


def _start_job_thread(job_id: int) -> None:
    threading.Thread(
        target=_run_job, args=(job_id,), name=f"kb-job-{job_id}", daemon=True
    ).start()


# --------------------------------------------------------------------------
# 接口
# --------------------------------------------------------------------------
@router.post("/import", response_model=ApiResponse[dict], summary="上传并一键入库")
async def import_knowledge(
    file: UploadFile = File(...), user: dict = Depends(require_admin)
) -> ApiResponse[dict]:
    filename, ext = _validate_ext(file.filename or "")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件内容为空")

    limit_bytes = config.KB_MAX_FILE_MB * 1024 * 1024
    if len(data) > limit_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"文件超过大小上限（{config.KB_MAX_FILE_MB}MB）",
        )
    _sniff_content(ext, data)

    storage = Path(config.KB_STORAGE_DIR)
    storage.mkdir(parents=True, exist_ok=True)
    stored_path = storage / f"{uuid.uuid4().hex}.{ext}"
    stored_path.write_bytes(data)

    operator = user.get("sub", "unknown")
    job_id = _create_job(filename, str(stored_path), len(data), ext, operator)
    _audit(operator, "import", filename, f"{ext.upper()} · {len(data)} 字节")
    _start_job_thread(job_id)

    job = get_job(job_id)
    return ApiResponse(data=job or {})


@router.get("/jobs", response_model=ApiResponse[dict], summary="导入历史")
def list_jobs(page: int = 1, page_size: int = 10, user: dict = Depends(require_admin)):
    page = max(1, page)
    page_size = max(1, min(50, page_size))
    offset = (page - 1) * page_size

    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM kb_import_jobs")
            total = cur.fetchone()[0]
            cur.execute(
                f"SELECT {_JOB_COLUMNS} FROM kb_import_jobs "
                "ORDER BY id DESC LIMIT %s OFFSET %s",
                (page_size, offset),
            )
            rows = cur.fetchall()

    return ApiResponse(
        data={
            "items": [_row_to_job(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/jobs/{job_id}", response_model=ApiResponse[dict], summary="任务进度")
def job_detail(job_id: int, user: dict = Depends(require_admin)):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiResponse(data=job)


@router.post("/jobs/{job_id}/retry", response_model=ApiResponse[dict], summary="重试失败任务")
def retry_job(job_id: int, user: dict = Depends(require_admin)):
    job = get_job(job_id, with_path=True)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job["status"] != "failed":
        raise HTTPException(status_code=400, detail="只有失败的任务可以重试")
    if not Path(job["stored_path"]).exists():
        raise HTTPException(status_code=400, detail="原始文件已不存在，请重新上传")

    _update_job(
        job_id,
        status="pending",
        stage="queued",
        progress=0,
        total_chunks=0,
        success_chunks=0,
        failed_chunks=0,
        error_detail="",
    )
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE kb_import_jobs SET started_at = NULL, finished_at = NULL "
                "WHERE id = %s",
                (job_id,),
            )
        conn.commit()

    _audit(user.get("sub", "unknown"), "retry", job["filename"], f"job #{job_id}")
    _start_job_thread(job_id)
    return ApiResponse(data=get_job(job_id) or {})


@router.get("/audit-logs", response_model=ApiResponse[dict], summary="审计日志")
def list_audit_logs(limit: int = 50, user: dict = Depends(require_admin)):
    limit = max(1, min(200, limit))
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, operator, action, target, detail, created_at "
                "FROM kb_audit_logs ORDER BY id DESC LIMIT %s",
                (limit,),
            )
            rows = cur.fetchall()
    items = [
        {
            "id": r[0],
            "operator": r[1],
            "action": r[2],
            "target": r[3],
            "detail": r[4],
            "created_at": _iso(r[5]),
        }
        for r in rows
    ]
    return ApiResponse(data={"items": items})


@router.get("/stats", response_model=ApiResponse[dict], summary="已入库统计")
def kb_stats(user: dict = Depends(require_admin)):
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            # documents 表是「一片一行」（_persist 每片插一条），
            # 直接 count(*) 会把 1 个文件数成 7 个文档；按 source 去重才是文件数
            cur.execute(
                "SELECT count(DISTINCT source) FROM documents WHERE source LIKE 'upload:%%'"
            )
            documents = cur.fetchone()[0]
            cur.execute(
                "SELECT count(*) FROM chunks c JOIN documents d ON d.id = c.doc_id "
                "WHERE d.source LIKE 'upload:%%'"
            )
            chunks = cur.fetchone()[0]
    return ApiResponse(
        data={"documents": documents, "chunks": chunks, "max_file_mb": config.KB_MAX_FILE_MB}
    )
