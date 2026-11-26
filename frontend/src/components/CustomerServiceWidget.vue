<script setup lang="ts">
/**
 * 智能客服悬浮组件
 *
 * - 页面右上角悬浮机器人图标，点击弹出对话窗口；
 * - 对接后端 RAG 流式接口 POST /chat/stream（SSE），解析 sources / token / error 事件；
 * - 支持 Enter 发送、Shift+Enter 换行、生成中可中断、引用资料来源展示。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { CircleAlert, LoaderCircle, Send, Square, X } from 'lucide-vue-next'
import robotUrl from '@/assets/robot.png'
import { AUTH_KEY, TOKEN_KEY } from '@/api/request'

type SourceItem = { index: number; content: string; similarity: number }

type ChatMessage = {
  id: number
  role: 'user' | 'assistant'
  content: string
  sources: SourceItem[]
  streaming?: boolean
  error?: string
}

// 后端流式对话地址：默认本地 8000 端口，可用 VITE_CHAT_URL 覆盖
const CHAT_ENDPOINT =
  (import.meta.env.VITE_CHAT_URL as string | undefined) ||
  'http://localhost:8000/chat/stream'

const QUICK_QUESTIONS = [
  '退款多久到账？',
  '如何申请退款？',
  '我的快递到哪了',
  '如何开具发票？',
]

const open = ref(false)
const input = ref('')
const messages = ref<ChatMessage[]>([])
const loading = ref(false)
const listRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)

let controller: AbortController | null = null
let seq = 0

// 自动贴底开关：仅当用户手动向上翻看历史超过阈值时置为 false，
// 流式阶段默认保持 true（随 token / sources 变化自动贴底）
const SCROLL_THRESHOLD = 80
let autoScrollEnabled = true
let observer: MutationObserver | null = null
let rafId: number | null = null

const hasMessages = computed(() => messages.value.length > 0)

/**
 * 真正的"贴底"实现：
 *   await nextTick() —— 等 Vue 完成 patch
 *   requestAnimationFrame —— 等浏览器 layout 完成（scrollHeight 才准确）
 * 两层保障避免"滚了但滚不到底"的时序问题。
 */
async function scrollToBottom() {
  if (!autoScrollEnabled) return
  await nextTick()
  if (rafId !== null) cancelAnimationFrame(rafId)
  rafId = requestAnimationFrame(() => {
    const el = listRef.value
    if (el) el.scrollTop = el.scrollHeight
    rafId = null
  })
}

/** 用户滚动监听：判断是否向上翻看历史 */
function onUserScroll() {
  const el = listRef.value
  if (!el) return
  const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  autoScrollEnabled = distanceFromBottom <= SCROLL_THRESHOLD
}

/** 监听消息容器的 DOM 变化（子节点新增、文本变化、sources 卡片高度变化） */
function attachObserver() {
  detachObserver()
  const el = listRef.value
  if (!el) return
  observer = new MutationObserver(() => {
    void scrollToBottom()
  })
  observer.observe(el, {
    childList: true,
    subtree: true,
    characterData: true,
  })
}

function detachObserver() {
  if (observer) {
    observer.disconnect()
    observer = null
  }
}

function openDialog() {
  open.value = true
  document.body.style.overflow = 'hidden'
  // 容器由 v-if 刚挂载，需要等 enter 动画初始帧后 ref 才可用
  requestAnimationFrame(async () => {
    await nextTick()
    listRef.value?.addEventListener('scroll', onUserScroll, { passive: true })
    attachObserver()
    autoScrollEnabled = true
    await scrollToBottom()
    inputRef.value?.focus()
  })
}

function abort() {
  controller?.abort()
  controller = null
}

function closeDialog() {
  abort()
  detachObserver()
  listRef.value?.removeEventListener('scroll', onUserScroll)
  open.value = false
  document.body.style.overflow = ''
  autoScrollEnabled = true
}

/** 解析一条 SSE 消息块，把 token / sources / error 合并进回答消息 */
function handleChunk(raw: string, reply: ChatMessage) {
  for (const line of raw.split('\n')) {
    if (!line.startsWith('data:')) continue
    const payload = line.slice(5).trim()
    if (!payload || payload === '[DONE]') continue
    let data: { sources?: SourceItem[]; token?: string; error?: string }
    try {
      data = JSON.parse(payload)
    } catch {
      continue
    }
    if (data.sources?.length) reply.sources = data.sources
    if (data.token) reply.content += data.token
    if (data.error) reply.error = data.error
  }
  // 贴底由 MutationObserver 统一处理，此处不再手动触发
}

/** 发送问题并流式接收回答 */
async function send(text?: string) {
  const question = (text ?? input.value).trim()
  if (!question || loading.value) return

  input.value = ''
  messages.value.push({ id: ++seq, role: 'user', content: question, sources: [] })
  const reply: ChatMessage = {
    id: ++seq,
    role: 'assistant',
    content: '',
    sources: [],
    streaming: true,
  }
  messages.value.push(reply)
  loading.value = true
  // 自动贴底交给 MutationObserver；此处仅重置开关（可能被用户向上滚动关掉）
  autoScrollEnabled = true

  controller = new AbortController()
  const token = localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY)

  try {
    const res = await fetch(CHAT_ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ q: question }),
      signal: controller.signal,
    })

    if (!res.ok || !res.body) {
      const detail = await res.json().catch(() => null)
      // 对话接口需要登录：token 缺失/过期时清理登录态并跳登录页
      // （SSE 走原生 fetch，不经过 axios 的 401 拦截器，需在此单独处理）
      if (res.status === 401) {
        localStorage.removeItem(TOKEN_KEY)
        sessionStorage.removeItem(TOKEN_KEY)
        localStorage.removeItem(AUTH_KEY)
        sessionStorage.removeItem(AUTH_KEY)
        window.location.href = '/login'
        return
      }
      throw new Error(detail?.message || `服务返回异常（${res.status}）`)
    }

    // 逐块读取 SSE：按空行切分事件，兼容半包
    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop() ?? ''
      for (const block of blocks) handleChunk(block, reply)
    }
  } catch (error) {
    // 用户主动中断不算错误
    if ((error as Error).name !== 'AbortError') {
      reply.error = (error as Error).message || '请求失败，请稍后重试'
    }
  } finally {
    reply.streaming = false
    loading.value = false
    controller = null
    if (!reply.content && !reply.error) {
      reply.error = '暂时没有获取到回答，请稍后重试'
    }
    // 结束时刻 sources 卡片可能高度有变化，确保至少贴一次底
    autoScrollEnabled = true
    void scrollToBottom()
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && open.value) closeDialog()
}

onMounted(() => window.addEventListener('keydown', handleKeydown))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  abort()
  detachObserver()
  listRef.value?.removeEventListener('scroll', onUserScroll)
  if (rafId !== null) cancelAnimationFrame(rafId)
  document.body.style.overflow = ''
})
</script>

<template>
  <!-- 悬浮客服入口（页面右上方） -->
  <div class="fixed right-4 top-[84px] z-[60] sm:right-6 sm:top-[88px]">
    <button
      type="button"
      class="group relative flex size-14 items-center justify-center overflow-visible rounded-2xl border border-slate-200 bg-white shadow-lg shadow-ink-950/10 transition duration-200 hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-xl hover:shadow-brand-600/15 active:translate-y-0 sm:size-16"
      aria-label="打开智能客服"
      :aria-expanded="open"
      @click="openDialog"
    >
      <img :src="robotUrl" alt="智能客服" class="size-full rounded-2xl object-cover" />
      <!-- 在线状态脉冲点 -->
      <span class="absolute -right-1 -top-1 flex size-3.5 items-center justify-center">
        <span class="absolute inline-flex size-3.5 animate-ping rounded-full bg-brand-400/70"></span>
        <span class="relative inline-flex size-2.5 rounded-full bg-brand-500 ring-2 ring-white"></span>
      </span>
      <!-- 悬停提示 -->
      <span class="pointer-events-none absolute right-full mr-2 hidden whitespace-nowrap rounded-lg bg-ink-950 px-2.5 py-1.5 text-[11px] font-medium text-white opacity-0 shadow-lg transition group-hover:opacity-100 lg:block">
        智能客服
      </span>
    </button>
  </div>

  <!-- 遮罩 -->
  <Transition name="fade">
    <div
      v-if="open"
      class="fixed inset-0 z-[90] bg-ink-950/50 backdrop-blur-sm"
      @click="closeDialog"
    ></div>
  </Transition>

  <!-- 对话窗口 -->
  <Transition name="chat-panel">
    <section
      v-if="open"
      class="fixed inset-x-3 bottom-4 top-20 z-[95] flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-ink-950/25 sm:inset-auto sm:left-1/2 sm:top-1/2 sm:h-[620px] sm:w-[560px] sm:-translate-x-1/2 sm:-translate-y-1/2"
      role="dialog"
      aria-modal="true"
      aria-label="智能客服对话窗口"
    >
      <!-- 头部 -->
      <header class="flex shrink-0 items-center gap-3 bg-ink-950 px-4 py-3.5 text-white">
        <span class="size-10 shrink-0 overflow-hidden rounded-xl bg-white ring-1 ring-white/20">
          <img :src="robotUrl" alt="" class="size-full object-cover" />
        </span>
        <div class="min-w-0 flex-1">
          <p class="text-sm font-semibold">智能客服</p>
          <p class="mt-0.5 flex items-center gap-1.5 text-[11px] text-slate-400">
            <span class="size-1.5 rounded-full bg-brand-400"></span>
            在线 · 售后知识库驱动
          </p>
        </div>
        <button
          type="button"
          class="inline-flex size-9 shrink-0 items-center justify-center rounded-xl text-slate-400 transition hover:bg-white/10 hover:text-white"
          aria-label="关闭会话"
          @click="closeDialog"
        >
          <X class="size-4" />
        </button>
      </header>

      <!-- 消息区 -->
      <div ref="listRef" class="flex-1 space-y-4 overflow-y-auto bg-canvas p-4">
        <!-- 空状态 -->
        <div v-if="!hasMessages" class="flex h-full flex-col items-center justify-center px-2 text-center">
          <img
            :src="robotUrl"
            alt=""
            class="size-20 rounded-2xl object-cover ring-1 ring-slate-200"
          />
          <p class="mt-4 text-sm font-semibold text-ink-900">你好，我是智能客服助手</p>
          <p class="mt-1.5 max-w-[280px] text-xs leading-5 text-slate-400">
            基于售后知识库为你解答退款、物流、发票等常见问题
          </p>
          <div class="mt-5 flex flex-wrap justify-center gap-2">
            <button
              v-for="q in QUICK_QUESTIONS"
              :key="q"
              type="button"
              class="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[11px] text-ink-700 transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700"
              @click="send(q)"
            >
              {{ q }}
            </button>
          </div>
        </div>

        <!-- 消息列表 -->
        <template v-for="msg in messages" :key="msg.id">
          <div v-if="msg.role === 'user'" class="flex justify-end">
            <p class="max-w-[82%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-brand-600 px-3.5 py-2.5 text-xs leading-5 text-white">
              {{ msg.content }}
            </p>
          </div>

          <div v-else class="flex gap-2.5">
            <img
              :src="robotUrl"
              alt=""
              class="mt-0.5 size-7 shrink-0 rounded-lg object-cover ring-1 ring-slate-200"
            />
            <div class="min-w-0 max-w-[84%]">
              <div class="rounded-2xl rounded-bl-md border border-slate-200 bg-white px-3.5 py-2.5 text-xs leading-5 text-ink-800">
                <p v-if="msg.content" class="whitespace-pre-wrap break-words">{{ msg.content }}</p>
                <!-- 思考中动画 -->
                <span v-else-if="msg.streaming" class="inline-flex items-center gap-1 py-1">
                  <i class="chat-dot"></i><i class="chat-dot"></i><i class="chat-dot"></i>
                </span>
                <p v-if="msg.error" class="mt-1 flex items-start gap-1.5 text-[11px] leading-4 text-red-600">
                  <CircleAlert class="mt-0.5 size-3.5 shrink-0" />{{ msg.error }}
                </p>
              </div>

              <!-- 引用资料来源 -->
              <div v-if="msg.sources.length" class="mt-2 space-y-1.5">
                <p class="text-[10px] font-medium tracking-wide text-slate-400">引用资料</p>
                <div
                  v-for="source in msg.sources"
                  :key="source.index"
                  class="rounded-lg border border-slate-200/80 bg-white/80 px-2.5 py-2"
                >
                  <p class="flex items-center justify-between text-[10px] text-slate-400">
                    <span class="font-medium text-brand-600">#{{ source.index }}</span>
                    <span>相似度 {{ Math.round(source.similarity * 100) }}%</span>
                  </p>
                  <p class="mt-1 line-clamp-2 text-[11px] leading-4 text-slate-500">{{ source.content }}</p>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- 输入区 -->
      <div class="shrink-0 border-t border-slate-200 bg-white p-3">
        <div class="flex items-end gap-2">
          <textarea
            ref="inputRef"
            v-model="input"
            rows="1"
            placeholder="输入你的问题，Enter 发送"
            class="max-h-24 min-h-[42px] flex-1 resize-none rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs leading-5 text-ink-800 outline-none transition placeholder:text-slate-400 focus:border-brand-400 focus:bg-white focus:ring-4 focus:ring-brand-500/10"
            @keydown.enter.exact.prevent="send()"
          ></textarea>

          <button
            v-if="loading"
            type="button"
            class="inline-flex size-[42px] shrink-0 items-center justify-center rounded-xl bg-slate-800 text-white transition hover:bg-ink-950"
            aria-label="停止回答"
            @click="abort"
          >
            <Square class="size-3.5" />
          </button>
          <button
            v-else
            type="button"
            class="inline-flex size-[42px] shrink-0 items-center justify-center rounded-xl bg-brand-600 text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-40"
            :disabled="!input.trim()"
            aria-label="发送"
            @click="send()"
          >
            <Send class="size-4" />
          </button>
        </div>
        <p class="mt-2 flex items-center justify-center gap-1.5 text-[10px] text-slate-400">
          <LoaderCircle v-if="loading" class="size-3 animate-spin" />
          回答基于售后知识库生成，仅供参考
        </p>
      </div>
    </section>
  </Transition>
</template>

<style scoped>
.chat-panel-enter-active,
.chat-panel-leave-active {
  transition: opacity 200ms ease, transform 200ms cubic-bezier(0.22, 1, 0.36, 1);
}

.chat-panel-enter-from,
.chat-panel-leave-to {
  opacity: 0;
  transform: translateY(14px) scale(0.98);
}

.chat-dot {
  width: 5px;
  height: 5px;
  border-radius: 999px;
  background: #94a3b8;
  animation: chat-dot-bounce 1.2s infinite ease-in-out;
}

.chat-dot:nth-child(2) {
  animation-delay: 0.15s;
}

.chat-dot:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes chat-dot-bounce {
  0%,
  80%,
  100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  40% {
    transform: translateY(-3px);
    opacity: 1;
  }
}
</style>
