<script setup lang="ts">
/**
 * 知识库管理面板（仅管理员可见）：
 * 上传文件 → 一键入库（后台任务）→ 轮询进度 → 历史记录 / 异常重试 / 审计日志。
 * 权限由后端 require_admin 强制校验，本组件只负责界面层。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  CheckCircle2,
  CircleAlert,
  Clock3,
  Database,
  FileText,
  History,
  Loader2,
  RefreshCw,
  ShieldCheck,
  UploadCloud,
  X,
  XCircle,
} from 'lucide-vue-next'
import {
  KB_ACCEPT,
  KB_ALLOWED_EXT,
  KB_EXT_LABEL,
  KB_MAX_MB,
  getJob,
  getStats,
  importKnowledgeFile,
  listAuditLogs,
  listJobs,
  retryJob,
  type KbAuditLog,
  type KbJob,
  type KbJobStatus,
  type KbStats,
} from '@/api/kb'

const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const dragActive = ref(false)
const forceImport = ref(false)
const errorText = ref('')
const running = ref(false)
const currentJob = ref<KbJob | null>(null)
const uploadPercent = ref(0)

const jobs = ref<KbJob[]>([])
const jobsTotal = ref(0)
const page = ref(1)
const pageSize = 8
const loadingJobs = ref(false)

const auditLogs = ref<KbAuditLog[]>([])
const showAudit = ref(false)
const detailJob = ref<KbJob | null>(null)
const stats = ref<KbStats | null>(null)

let pollTimer: number | null = null
let alive = true

const maxMb = computed(() => stats.value?.max_file_mb ?? KB_MAX_MB)
const totalPages = computed(() => Math.max(1, Math.ceil(jobsTotal.value / pageSize)))

const stageText: Record<string, string> = {
  queued: '排队等待',
  parsing: '解析文件内容',
  chunking: '按语义分片',
  embedding: '向量化处理',
  writing: '写入向量库',
  success: '已完成',
  failed: '处理失败',
  skipped: '内容重复，已跳过',
}

const statusMeta: Record<KbJobStatus, { label: string; cls: string }> = {
  pending: { label: '排队中', cls: 'bg-slate-100 text-slate-600' },
  processing: { label: '处理中', cls: 'bg-amber-50 text-amber-600' },
  success: { label: '成功', cls: 'bg-brand-50 text-brand-700' },
  failed: { label: '失败', cls: 'bg-red-50 text-red-600' },
  duplicate: { label: '重复跳过', cls: 'bg-sky-50 text-sky-600' },
}

const actionText: Record<string, string> = {
  import: '上传导入',
  import_finish: '导入完成',
  import_fail: '导入失败',
  import_replace: '覆盖旧版本',
  import_skip_duplicate: '跳过重复',
  retry: '重试任务',
}

function formatSize(bytes: number) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

function formatTime(iso: string | null) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function validateFile(file: File): string {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  if (!KB_ALLOWED_EXT.includes(ext)) {
    return `不支持的格式 .${ext || '未知'}，仅支持 ${KB_EXT_LABEL}`
  }
  if (file.size === 0) return '文件内容为空'
  if (file.size > maxMb.value * 1024 * 1024) {
    return `文件大小 ${formatSize(file.size)} 超过 ${maxMb.value}MB 上限`
  }
  return ''
}

function pickFile(file: File | null | undefined) {
  if (!file) return
  errorText.value = validateFile(file)
  if (!errorText.value) selectedFile.value = file
}

function onInputChange(event: Event) {
  const target = event.target as HTMLInputElement
  pickFile(target.files?.[0])
}

function onDrop(event: DragEvent) {
  dragActive.value = false
  pickFile(event.dataTransfer?.files?.[0])
}

function clearFile() {
  selectedFile.value = null
  errorText.value = ''
  if (fileInput.value) fileInput.value.value = ''
}

function delay(ms: number) {
  return new Promise<void>((resolve) => {
    pollTimer = window.setTimeout(resolve, ms)
  })
}

async function pollJob(id: number) {
  let failures = 0
  while (alive) {
    await delay(900)
    try {
      const res = await getJob(id)
      currentJob.value = res.data
      failures = 0
      // duplicate 是终态（内容与已入库文件一致，直接跳过，不会有后续阶段）
      if (['success', 'failed', 'duplicate'].includes(res.data.status)) break
    } catch (error) {
      failures += 1
      if (failures >= 3) {
        errorText.value = `进度获取失败：${(error as Error).message}`
        break
      }
    }
  }
}

async function startImport() {
  if (!selectedFile.value || running.value) return
  errorText.value = ''
  running.value = true
  uploadPercent.value = 0
  currentJob.value = null
  const force = forceImport.value
  try {
    const res = await importKnowledgeFile(
      selectedFile.value,
      (percent) => {
        uploadPercent.value = percent
      },
      force,
    )
    currentJob.value = res.data
    // 判重命中时后端直接返回终态，不必再轮询
    if (res.data.status !== 'duplicate') await pollJob(res.data.id)
  } catch (error) {
    errorText.value = (error as Error).message
  } finally {
    running.value = false
    clearFile()
    await refreshAll()
  }
}

async function loadJobs(target = page.value) {
  loadingJobs.value = true
  try {
    const res = await listJobs(target, pageSize)
    jobs.value = res.data.items
    jobsTotal.value = res.data.total
    page.value = res.data.page
  } catch (error) {
    errorText.value = (error as Error).message
  } finally {
    loadingJobs.value = false
  }
}

async function loadStats() {
  try {
    stats.value = (await getStats()).data
  } catch {
    // 统计失败不阻塞主流程
  }
}

async function loadAudit() {
  try {
    auditLogs.value = (await listAuditLogs(30)).data.items
  } catch (error) {
    errorText.value = (error as Error).message
  }
}

async function refreshAll() {
  await Promise.all([loadStats(), loadJobs(1)])
  if (showAudit.value) await loadAudit()
}

async function toggleAudit() {
  showAudit.value = !showAudit.value
  if (showAudit.value) await loadAudit()
}

async function retryFailed(job: KbJob) {
  if (running.value) return
  errorText.value = ''
  running.value = true
  currentJob.value = null
  try {
    const res = await retryJob(job.id)
    currentJob.value = res.data
    await pollJob(res.data.id)
  } catch (error) {
    errorText.value = (error as Error).message
  } finally {
    running.value = false
    await refreshAll()
  }
}

async function retryFromDetail() {
  const job = detailJob.value
  detailJob.value = null
  if (job) await retryFailed(job)
}

function changePage(next: number) {
  if (next < 1 || next > totalPages.value || loadingJobs.value) return
  void loadJobs(next)
}

onMounted(() => {
  void refreshAll()
})

onBeforeUnmount(() => {
  alive = false
  if (pollTimer !== null) window.clearTimeout(pollTimer)
})
</script>

<template>
  <section>
    <!-- 顶部：标题 + 统计 -->
    <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h2 class="font-display text-lg font-bold text-ink-900">知识库管理</h2>
        <p class="mt-1 text-xs leading-5 text-slate-500">
          上传资料后自动完成解析、分片、向量化与入库，智能客服立即可检索；仅管理员可操作。
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2 text-xs">
        <span class="rounded-lg bg-brand-50 px-3 py-1.5 font-medium text-brand-700">
          已入库文档 {{ stats?.documents ?? 0 }}
        </span>
        <span class="rounded-lg bg-slate-100 px-3 py-1.5 font-medium text-ink-700">
          知识分片 {{ stats?.chunks ?? 0 }}
        </span>
        <button type="button" class="secondary-button !h-8 !px-3" @click="refreshAll">
          <RefreshCw class="size-3.5" :class="{ 'animate-spin': loadingJobs }" /> 刷新
        </button>
      </div>
    </div>

    <div class="mt-5 grid gap-4 lg:grid-cols-2">
      <!-- 上传区 -->
      <div class="panel-card p-5">
        <h3 class="flex items-center gap-2 text-sm font-semibold text-ink-800">
          <UploadCloud class="size-4 text-brand-500" /> 文件导入
        </h3>

        <div
          class="mt-4 rounded-xl border-2 border-dashed px-5 py-8 text-center transition"
          :class="dragActive ? 'border-brand-500 bg-brand-50/60' : 'border-slate-200 bg-slate-50/60'"
          @dragover.prevent="dragActive = true"
          @dragleave.prevent="dragActive = false"
          @drop.prevent="onDrop"
        >
          <UploadCloud class="mx-auto size-8 text-brand-500" />
          <p class="mt-3 text-sm text-ink-800">
            拖拽文件到此处，或
            <button
              type="button"
              class="font-semibold text-brand-600 underline-offset-2 hover:underline"
              @click="fileInput?.click()"
            >
              点击选择
            </button>
          </p>
          <p class="mt-2 text-[11px] text-slate-400">
            {{ KB_EXT_LABEL }} · 单文件不超过 {{ maxMb }}MB
          </p>
          <input
            ref="fileInput"
            type="file"
            class="hidden"
            :accept="KB_ACCEPT"
            @change="onInputChange"
          />
        </div>

        <div
          v-if="selectedFile"
          class="mt-3 flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2.5"
        >
          <FileText class="size-4 shrink-0 text-brand-600" />
          <div class="min-w-0 flex-1">
            <p class="truncate text-xs font-medium text-ink-800">{{ selectedFile.name }}</p>
            <p class="mt-0.5 text-[11px] text-slate-400">
              {{ formatSize(selectedFile.size) }} · 待入库
            </p>
          </div>
          <button type="button" class="icon-button !size-7" aria-label="移除文件" @click="clearFile">
            <X class="size-3.5" />
          </button>
        </div>

        <p
          v-if="errorText"
          class="mt-3 flex items-start gap-2 rounded-xl bg-red-50 px-3 py-2 text-xs leading-5 text-red-600"
        >
          <CircleAlert class="mt-0.5 size-3.5 shrink-0" />{{ errorText }}
        </p>

        <button
          type="button"
          class="primary-button mt-4 w-full"
          :disabled="!selectedFile || running"
          @click="startImport"
        >
          <Loader2 v-if="running" class="size-4 animate-spin" />
          <UploadCloud v-else class="size-4" />
          {{ running ? '正在导入入库…' : '导入入库' }}
        </button>
        <label class="mt-3 flex cursor-pointer items-start gap-2 text-[11px] leading-4 text-slate-500">
          <input v-model="forceImport" type="checkbox" class="mt-0.5 size-3.5 accent-brand-600" />
          <span>
            内容未变也强制重导（覆盖同名旧分片）
            <span class="text-slate-400">· 换了分片参数想重跑时勾选</span>
          </span>
        </label>
        <p class="mt-2 text-center text-[11px] text-slate-400">
          点击后自动完成 解析 → 分片 → 向量化 → 入库，请保持页面打开
        </p>
      </div>

      <!-- 进度 / 结果 -->
      <div class="panel-card p-5">
        <h3 class="flex items-center gap-2 text-sm font-semibold text-ink-800">
          <Clock3 class="size-4 text-brand-500" /> 处理进度
        </h3>

        <template v-if="currentJob">
          <div class="mt-4 flex items-center justify-between text-xs">
            <span class="font-medium text-ink-800">
              任务 #{{ currentJob.id }} · {{ stageText[currentJob.stage] || currentJob.stage }}
            </span>
            <span class="font-display font-bold text-brand-600">{{ currentJob.progress }}%</span>
          </div>
          <div class="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
            <div
              class="h-full rounded-full transition-all duration-500"
              :class="
                currentJob.status === 'failed'
                  ? 'bg-red-500'
                  : currentJob.status === 'duplicate'
                    ? 'bg-sky-400'
                    : 'bg-brand-500'
              "
              :style="{ width: `${currentJob.progress}%` }"
            />
          </div>

          <dl class="mt-4 grid grid-cols-3 gap-2 text-center">
            <div class="rounded-xl bg-slate-50 px-2 py-3">
              <dt class="text-[11px] text-slate-400">总片数</dt>
              <dd class="mt-1 font-display text-lg font-bold text-ink-900">{{ currentJob.total_chunks }}</dd>
            </div>
            <div class="rounded-xl bg-brand-50 px-2 py-3">
              <dt class="text-[11px] text-brand-600/80">成功</dt>
              <dd class="mt-1 font-display text-lg font-bold text-brand-700">{{ currentJob.success_chunks }}</dd>
            </div>
            <div class="rounded-xl bg-red-50 px-2 py-3">
              <dt class="text-[11px] text-red-500/80">失败</dt>
              <dd class="mt-1 font-display text-lg font-bold text-red-600">{{ currentJob.failed_chunks }}</dd>
            </div>
          </dl>

          <div
            v-if="currentJob.status === 'success'"
            class="mt-4 flex items-center gap-2 rounded-xl bg-brand-50 px-3 py-2.5 text-xs text-brand-700"
          >
            <CheckCircle2 class="size-4 shrink-0" /> 入库完成，知识内容已可被智能客服检索
          </div>
          <div
            v-else-if="currentJob.status === 'duplicate'"
            class="mt-4 flex items-start gap-2 rounded-xl bg-sky-50 px-3 py-2.5 text-xs leading-5 text-sky-700"
          >
            <ShieldCheck class="mt-0.5 size-4 shrink-0" />
            <span>
              该文件内容与已入库的任务 #{{ currentJob.duplicate_of }} 完全一致，已跳过重复入库（库里仍只有一份）。
              如确实需要重跑，请勾选「强制重导」后再上传。
            </span>
          </div>
          <div
            v-else-if="currentJob.status === 'failed'"
            class="mt-4 flex items-start gap-2 rounded-xl bg-red-50 px-3 py-2.5 text-xs leading-5 text-red-600"
          >
            <XCircle class="mt-0.5 size-4 shrink-0" /> 导入失败，可在下方历史记录中查看详情并重试
          </div>
          <pre
            v-if="currentJob.error_detail"
            class="mt-3 max-h-32 overflow-auto rounded-xl bg-ink-950/95 px-3 py-2 text-[11px] leading-5 text-red-300"
          >{{ currentJob.error_detail }}</pre>
        </template>

        <template v-else-if="running">
          <div class="mt-4 flex items-center justify-between text-xs">
            <span class="font-medium text-ink-800">上传文件</span>
            <span class="font-display font-bold text-brand-600">{{ uploadPercent }}%</span>
          </div>
          <div class="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
            <div class="h-full rounded-full bg-brand-500 transition-all" :style="{ width: `${uploadPercent}%` }" />
          </div>
          <p class="mt-4 flex items-center gap-2 text-xs text-slate-500">
            <Loader2 class="size-3.5 animate-spin" /> 正在上传，完成后自动开始解析…
          </p>
        </template>

        <div v-else class="mt-8 flex flex-col items-center justify-center py-8 text-center">
          <ShieldCheck class="size-9 text-slate-300" />
          <p class="mt-3 text-xs leading-5 text-slate-400">
            导入后内容将写入向量库<br />问答时按相似度自动检索命中
          </p>
        </div>
      </div>
    </div>

    <!-- 导入历史 -->
    <div class="panel-card mt-4 p-5">
      <div class="flex items-center justify-between">
        <h3 class="flex items-center gap-2 text-sm font-semibold text-ink-800">
          <History class="size-4 text-brand-500" /> 导入历史
        </h3>
        <span class="text-[11px] text-slate-400">共 {{ jobsTotal }} 条</span>
      </div>

      <div class="mt-3 overflow-x-auto">
        <table class="w-full min-w-[720px] text-left text-xs">
          <thead>
            <tr class="border-b border-slate-100 text-[11px] text-slate-400">
              <th class="pb-2 font-medium">时间</th>
              <th class="pb-2 font-medium">文件名</th>
              <th class="pb-2 font-medium">操作人</th>
              <th class="pb-2 font-medium">状态</th>
              <th class="pb-2 font-medium">结果</th>
              <th class="pb-2 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!jobs.length">
              <td colspan="6" class="py-10 text-center text-slate-400">暂无导入记录</td>
            </tr>
            <tr v-for="job in jobs" :key="job.id" class="border-b border-slate-50 last:border-0">
              <td class="py-3 whitespace-nowrap text-slate-500">{{ formatTime(job.created_at) }}</td>
              <td class="max-w-[220px] py-3">
                <p class="truncate font-medium text-ink-800">{{ job.filename }}</p>
                <p class="mt-0.5 text-[11px] text-slate-400">
                  {{ job.ext.toUpperCase() }} · {{ formatSize(job.file_size) }}
                </p>
              </td>
              <td class="py-3 text-slate-600">{{ job.operator }}</td>
              <td class="py-3">
                <span class="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium" :class="statusMeta[job.status].cls">
                  <Loader2 v-if="job.status === 'processing'" class="size-3 animate-spin" />
                  {{ statusMeta[job.status].label }}
                </span>
              </td>
              <td class="py-3 text-slate-600">
                <span class="text-brand-700">{{ job.success_chunks }}</span>
                <span class="text-slate-300"> / </span>
                <span :class="job.failed_chunks ? 'text-red-600' : 'text-slate-400'">{{ job.failed_chunks }}</span>
              </td>
              <td class="py-3 text-right whitespace-nowrap">
                <button type="button" class="text-[11px] font-medium text-brand-600 hover:underline" @click="detailJob = job">
                  详情
                </button>
                <button
                  v-if="job.status === 'failed'"
                  type="button"
                  class="ml-3 text-[11px] font-medium text-ink-700 hover:underline disabled:opacity-50"
                  :disabled="running"
                  @click="retryFailed(job)"
                >
                  重试
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="mt-4 flex items-center justify-between text-[11px] text-slate-400">
        <span>第 {{ page }} / {{ totalPages }} 页</span>
        <div class="flex gap-2">
          <button type="button" class="secondary-button !h-7 !px-2.5 !text-[11px]" :disabled="page <= 1" @click="changePage(page - 1)">
            上一页
          </button>
          <button type="button" class="secondary-button !h-7 !px-2.5 !text-[11px]" :disabled="page >= totalPages" @click="changePage(page + 1)">
            下一页
          </button>
        </div>
      </div>
    </div>

    <!-- 审计日志 -->
    <div class="panel-card mt-4 p-5">
      <button type="button" class="flex w-full items-center justify-between" @click="toggleAudit">
        <h3 class="flex items-center gap-2 text-sm font-semibold text-ink-800">
          <Database class="size-4 text-brand-500" /> 操作审计日志
        </h3>
        <span class="text-[11px] text-slate-400">{{ showAudit ? '收起' : '展开' }}</span>
      </button>
      <ul v-if="showAudit" class="mt-4 space-y-2">
        <li v-if="!auditLogs.length" class="py-6 text-center text-xs text-slate-400">暂无日志</li>
        <li
          v-for="log in auditLogs"
          :key="log.id"
          class="flex flex-col gap-1 rounded-xl bg-slate-50/80 px-3 py-2.5 text-[11px] sm:flex-row sm:items-center sm:justify-between"
        >
          <div class="flex items-center gap-2">
            <span class="rounded-md bg-white px-1.5 py-0.5 font-medium text-ink-700">{{ actionText[log.action] || log.action }}</span>
            <span class="text-slate-600">{{ log.operator }}</span>
            <span class="truncate text-slate-500">{{ log.target }}</span>
            <span v-if="log.detail" class="truncate text-slate-400">{{ log.detail }}</span>
          </div>
          <span class="shrink-0 text-slate-400">{{ formatTime(log.created_at) }}</span>
        </li>
      </ul>
    </div>

    <!-- 详情弹窗 -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="detailJob" class="fixed inset-0 z-50 flex items-center justify-center bg-ink-950/40 p-4" @click.self="detailJob = null">
          <div class="w-full max-w-lg rounded-2xl bg-white p-5 shadow-2xl">
            <div class="flex items-start justify-between">
              <div>
                <h4 class="font-display text-sm font-bold text-ink-900">任务 #{{ detailJob.id }} 详情</h4>
                <p class="mt-1 text-[11px] text-slate-400">{{ detailJob.filename }}</p>
              </div>
              <button type="button" class="icon-button !size-8" aria-label="关闭" @click="detailJob = null">
                <X class="size-4" />
              </button>
            </div>
            <dl class="mt-4 grid grid-cols-2 gap-3 text-xs">
              <div class="rounded-xl bg-slate-50 px-3 py-2">
                <dt class="text-[11px] text-slate-400">状态</dt>
                <dd class="mt-1 font-medium text-ink-800">{{ statusMeta[detailJob.status].label }}</dd>
              </div>
              <div class="rounded-xl bg-slate-50 px-3 py-2">
                <dt class="text-[11px] text-slate-400">操作人</dt>
                <dd class="mt-1 font-medium text-ink-800">{{ detailJob.operator }}</dd>
              </div>
              <div class="rounded-xl bg-slate-50 px-3 py-2">
                <dt class="text-[11px] text-slate-400">文件大小</dt>
                <dd class="mt-1 font-medium text-ink-800">{{ formatSize(detailJob.file_size) }}</dd>
              </div>
              <div class="rounded-xl bg-slate-50 px-3 py-2">
                <dt class="text-[11px] text-slate-400">分片结果</dt>
                <dd class="mt-1 font-medium text-ink-800">
                  共 {{ detailJob.total_chunks }}，成功 {{ detailJob.success_chunks }}，失败 {{ detailJob.failed_chunks }}
                </dd>
              </div>
              <div class="col-span-2 rounded-xl bg-slate-50 px-3 py-2">
                <dt class="text-[11px] text-slate-400">时间</dt>
                <dd class="mt-1 font-medium text-ink-800">
                  {{ formatTime(detailJob.created_at) }} → {{ formatTime(detailJob.finished_at) }}
                </dd>
              </div>
              <div class="col-span-2 rounded-xl bg-slate-50 px-3 py-2">
                <dt class="text-[11px] text-slate-400">内容指纹（SHA-256，判重依据）</dt>
                <dd class="mt-1 break-all font-mono text-[11px] text-ink-700">
                  {{ detailJob.content_hash || '—（历史任务未记录）' }}
                </dd>
                <p v-if="detailJob.duplicate_of" class="mt-1 text-[11px] text-sky-600">
                  该次上传与任务 #{{ detailJob.duplicate_of }} 内容一致，已跳过
                </p>
              </div>
            </dl>
            <div v-if="detailJob.error_detail" class="mt-3">
              <p class="text-[11px] font-medium text-slate-500">异常日志</p>
              <pre class="mt-1 max-h-40 overflow-auto rounded-xl bg-ink-950 px-3 py-2 text-[11px] leading-5 text-red-300">{{ detailJob.error_detail }}</pre>
            </div>
            <div class="mt-4 flex justify-end gap-2">
              <button type="button" class="secondary-button !h-9" @click="detailJob = null">关闭</button>
              <button
                v-if="detailJob.status === 'failed'"
                type="button"
                class="primary-button !h-9"
                :disabled="running"
                @click="retryFromDetail"
              >
                重试导入
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </section>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.18s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
