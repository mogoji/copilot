/** 知识库管理接口：上传导入、任务进度、历史、审计、统计 */
import { http } from './request'
import type { ApiResult } from './request'

export type KbJobStatus = 'pending' | 'processing' | 'success' | 'failed' | 'duplicate'

export interface KbJob {
  id: number
  filename: string
  file_size: number
  ext: string
  status: KbJobStatus
  stage: string
  progress: number
  total_chunks: number
  success_chunks: number
  failed_chunks: number
  error_detail: string
  operator: string
  created_at: string
  started_at: string | null
  finished_at: string | null
  /** 文件内容的 SHA-256，用于判重 */
  content_hash: string
  /** 本次上传被判为重复时，指向已入库的原任务 id */
  duplicate_of: number | null
}

export interface KbJobPage {
  items: KbJob[]
  total: number
  page: number
  page_size: number
}

export interface KbAuditLog {
  id: number
  operator: string
  action: string
  target: string
  detail: string
  created_at: string
}

export interface KbStats {
  documents: number
  chunks: number
  max_file_mb: number
}

/** 允许的扩展名（与后端 ALLOWED_EXT 一致） */
export const KB_ALLOWED_EXT = ['pdf', 'docx', 'xlsx', 'md']
export const KB_ACCEPT = '.pdf,.docx,.xlsx,.md'
export const KB_MAX_MB = 10
export const KB_EXT_LABEL = 'PDF / Word(.docx) / Excel(.xlsx) / Markdown(.md)'

/** 上传并一键入库：后端立即返回任务，后续通过 getJob 轮询进度。
 * `force=true` 时即使内容与已入库文件一致也重新导入（覆盖旧版本）。 */
export function importKnowledgeFile(
  file: File,
  onUploadProgress?: (percent: number) => void,
  force = false,
) {
  const form = new FormData()
  form.append('file', file)
  form.append('force', force ? 'true' : 'false')
  return http.post<ApiResult<KbJob>>('/kb/import', form, {
    timeout: 120000,
    onUploadProgress: (event) => {
      if (onUploadProgress && event.total) {
        onUploadProgress(Math.round((event.loaded / event.total) * 100))
      }
    },
  })
}

export function listJobs(page = 1, pageSize = 8) {
  return http.get<ApiResult<KbJobPage>>('/kb/jobs', {
    params: { page, page_size: pageSize },
  })
}

export function getJob(id: number) {
  return http.get<ApiResult<KbJob>>(`/kb/jobs/${id}`)
}

export function retryJob(id: number) {
  return http.post<ApiResult<KbJob>>(`/kb/jobs/${id}/retry`)
}

export function listAuditLogs(limit = 30) {
  return http.get<ApiResult<{ items: KbAuditLog[] }>>('/kb/audit-logs', {
    params: { limit },
  })
}

export function getStats() {
  return http.get<ApiResult<KbStats>>('/kb/stats')
}
