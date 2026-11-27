<script setup lang="ts">
/**
 * 个人中心：顶部导航包含「个人信息」与「知识库管理」两个模块。
 * 「知识库管理」仅 admin 角色可见；真正的权限校验在后端 require_admin。
 */
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Database, ShieldCheck, UserRound } from 'lucide-vue-next'
import BrandLogo from '@/components/BrandLogo.vue'
import KnowledgeBasePanel from '@/components/KnowledgeBasePanel.vue'
import { getTokenPayload, isAdmin } from '@/api/auth'

type TabKey = 'profile' | 'kb'

const route = useRoute()
const router = useRouter()
const payload = getTokenPayload()
const admin = isAdmin()
const username = payload?.sub ?? '未登录'
const nickname = admin ? '系统管理员' : '普通用户'

const tabs = computed(() =>
  admin
    ? [
        { key: 'profile' as TabKey, label: '个人信息', icon: UserRound },
        { key: 'kb' as TabKey, label: '知识库管理', icon: Database },
      ]
    : [{ key: 'profile' as TabKey, label: '个人信息', icon: UserRound }],
)

const active = ref<TabKey>(route.query.tab === 'kb' && admin ? 'kb' : 'profile')

function switchTab(key: TabKey) {
  active.value = key
  void router.replace({ query: key === 'kb' ? { tab: 'kb' } : {} })
}
</script>

<template>
  <div class="min-h-screen bg-canvas">
    <!-- 顶部导航 -->
    <header class="sticky top-0 z-30 border-b border-slate-200/80 bg-white/90 backdrop-blur">
      <div class="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <div class="flex items-center gap-3">
          <BrandLogo compact />
          <span class="text-slate-200">/</span>
          <span class="flex items-center gap-1.5 text-sm font-semibold text-ink-800">
            <UserRound class="size-4 text-slate-400" /> 个人中心
          </span>
        </div>
        <div class="flex items-center gap-2">
          <button type="button" class="secondary-button !h-9 !px-3" @click="router.push('/dashboard')">
            <ArrowLeft class="size-4" /> 返回仪表盘
          </button>
          <div class="hidden items-center gap-2 rounded-xl border border-slate-200 px-2.5 py-1.5 sm:flex">
            <span class="flex size-7 items-center justify-center rounded-lg bg-ink-900 font-display text-[10px] font-bold text-white">
              {{ username.slice(0, 2).toUpperCase() }}
            </span>
            <span class="text-xs font-medium text-ink-800">{{ nickname }}</span>
          </div>
        </div>
      </div>
    </header>

    <main class="mx-auto max-w-6xl px-4 py-6 sm:px-6">
      <div>
        <h1 class="font-display text-xl font-bold text-ink-900">个人中心</h1>
        <p class="mt-1 text-xs text-slate-500">管理账号信息与知识库内容</p>
      </div>

      <!-- 顶部模块导航 -->
      <nav class="mt-5 flex gap-1 border-b border-slate-200" aria-label="个人中心模块">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="-mb-px flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition"
          :class="
            active === tab.key
              ? 'border-brand-500 text-brand-700'
              : 'border-transparent text-slate-500 hover:text-ink-800'
          "
          :aria-selected="active === tab.key"
          @click="switchTab(tab.key)"
        >
          <component :is="tab.icon" class="size-4" />
          {{ tab.label }}
          <span
            v-if="tab.key === 'kb'"
            class="rounded-md bg-brand-50 px-1.5 py-0.5 text-[10px] font-semibold text-brand-700"
          >
            ADMIN
          </span>
        </button>
      </nav>

      <div class="mt-5">
        <!-- 个人信息 -->
        <section v-if="active === 'profile'" class="panel-card p-6">
          <div class="flex flex-col gap-5 sm:flex-row sm:items-center">
            <span class="flex size-16 items-center justify-center rounded-2xl bg-gradient-to-br from-ink-900 to-ink-700 font-display text-xl font-bold text-white">
              {{ username.slice(0, 2).toUpperCase() }}
            </span>
            <div>
              <p class="font-display text-lg font-bold text-ink-900">{{ nickname }}</p>
              <p class="mt-1 text-xs text-slate-500">账号 {{ username }}</p>
              <span
                class="mt-2 inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium"
                :class="admin ? 'bg-brand-50 text-brand-700' : 'bg-slate-100 text-slate-600'"
              >
                <ShieldCheck class="size-3" />
                {{ admin ? '管理员' : '普通用户' }}
              </span>
            </div>
          </div>

          <dl class="mt-6 grid gap-3 sm:grid-cols-3">
            <div class="rounded-xl bg-slate-50 px-4 py-3">
              <dt class="text-[11px] text-slate-400">用户名</dt>
              <dd class="mt-1 text-sm font-medium text-ink-800">{{ username }}</dd>
            </div>
            <div class="rounded-xl bg-slate-50 px-4 py-3">
              <dt class="text-[11px] text-slate-400">角色</dt>
              <dd class="mt-1 text-sm font-medium text-ink-800">{{ admin ? 'admin（管理员）' : 'user（普通用户）' }}</dd>
            </div>
            <div class="rounded-xl bg-slate-50 px-4 py-3">
              <dt class="text-[11px] text-slate-400">知识库权限</dt>
              <dd class="mt-1 text-sm font-medium" :class="admin ? 'text-brand-700' : 'text-slate-500'">
                {{ admin ? '可导入与管理' : '无访问权限' }}
              </dd>
            </div>
          </dl>

          <p
            v-if="!admin"
            class="mt-4 rounded-xl bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-500"
          >
            知识库管理仅对管理员开放；如需导入资料，请联系系统管理员。
          </p>
        </section>

        <!-- 知识库管理（仅管理员，路由守卫已拦截非管理员） -->
        <KnowledgeBasePanel v-else-if="admin" />

        <section v-else class="panel-card p-10 text-center">
          <ShieldCheck class="mx-auto size-9 text-slate-300" />
          <p class="mt-3 text-sm text-ink-800">无访问权限</p>
          <p class="mt-1 text-xs text-slate-500">知识库管理仅对管理员开放</p>
        </section>
      </div>
    </main>
  </div>
</template>
