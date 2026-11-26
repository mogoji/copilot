<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowRight,
  Check,
  CircleCheck,
  Eye,
  EyeOff,
  Headphones,
  Info,
  LoaderCircle,
  LockKeyhole,
  PackageCheck,
  ShieldCheck,
  TrendingUp,
  UserRound,
} from 'lucide-vue-next'
import BrandLogo from '@/components/BrandLogo.vue'
import { AUTH_KEY } from '@/router'

const REMEMBER_KEY = 'self-operated-remembered-user'
const route = useRoute()
const router = useRouter()

const rememberedUser = localStorage.getItem(REMEMBER_KEY) ?? ''
const form = reactive({
  username: rememberedUser,
  password: '',
  remember: Boolean(rememberedUser),
})
const errors = reactive({ username: '', password: '', form: '' })
const showPassword = ref(false)
const loading = ref(false)
const capsLockOn = ref(false)
const notice = ref('')

const redirectPath = computed(() =>
  typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/')
    ? route.query.redirect
    : '/dashboard',
)

function validate() {
  errors.username = form.username.trim() ? '' : '请输入用户名'
  errors.password = form.password ? '' : '请输入密码'
  if (form.password && form.password.length < 6) {
    errors.password = '密码长度不能少于 6 位'
  }
  return !errors.username && !errors.password
}

function fillDemoAccount() {
  form.username = 'admin'
  form.password = 'admin123'
  errors.username = ''
  errors.password = ''
  errors.form = ''
  notice.value = ''
}

async function handleSubmit() {
  errors.form = ''
  notice.value = ''
  if (!validate() || loading.value) return

  loading.value = true
  // 演示登录：实际接入后端时，将此处替换为真实认证接口请求。
  await new Promise((resolve) => window.setTimeout(resolve, 650))

  if (form.username.trim() !== 'admin' || form.password !== 'admin123') {
    errors.form = '用户名或密码不正确，请使用下方演示账号体验'
    loading.value = false
    return
  }

  const storage = form.remember ? localStorage : sessionStorage
  const otherStorage = form.remember ? sessionStorage : localStorage
  otherStorage.removeItem(AUTH_KEY)
  storage.setItem(AUTH_KEY, '1')

  if (form.remember) {
    localStorage.setItem(REMEMBER_KEY, form.username.trim())
  } else {
    localStorage.removeItem(REMEMBER_KEY)
  }

  await router.replace(redirectPath.value)
}
</script>

<template>
  <main class="flex min-h-screen bg-white">
    <!-- 品牌展示区：与首页共用深墨蓝 + 青绿色视觉语言 -->
    <section class="relative hidden min-h-screen overflow-hidden bg-ink-950 lg:flex lg:w-[54%] lg:flex-col xl:w-[58%]">
      <div class="login-grid pointer-events-none absolute inset-0"></div>
      <div class="pointer-events-none absolute -right-24 -top-28 size-[420px] rounded-full bg-brand-500/10 blur-3xl"></div>
      <div class="pointer-events-none absolute -bottom-40 -left-20 size-[420px] rounded-full bg-[#31577a]/20 blur-3xl"></div>

      <header class="relative z-10 flex items-center justify-between px-12 pt-10 xl:px-16">
        <BrandLogo inverse />
        <span class="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs tracking-wide text-slate-300">
          企业运营中枢
        </span>
      </header>

      <div class="relative z-10 flex flex-1 flex-col justify-center px-12 py-12 xl:px-16">
        <div class="stagger-in" style="animation-delay: 60ms">
          <div class="mb-5 flex items-center gap-3">
            <span class="h-px w-8 bg-brand-400"></span>
            <span class="font-display text-xs font-bold uppercase tracking-[0.24em] text-brand-400">
              Clarity in every operation
            </span>
          </div>
          <h1 class="max-w-xl text-[42px] font-semibold leading-[1.28] tracking-tight text-white xl:text-[48px]">
            把每一次经营决策，<br />建立在<span class="text-brand-400">清晰</span>之上。
          </h1>
          <p class="mt-6 max-w-md text-[15px] leading-8 text-slate-400">
            聚合商品、订单、库存与售后服务，让团队在同一个工作台中高效协作，实时掌握业务脉络。
          </p>
        </div>

        <!-- 抽象业务简报，不做成真实图片，保证页面完全独立可运行 -->
        <div
          class="stagger-in mt-10 max-w-[540px] rounded-2xl border border-white/10 bg-white/[0.055] p-5 shadow-2xl shadow-black/10 backdrop-blur-md"
          style="animation-delay: 160ms"
        >
          <div class="flex items-center justify-between border-b border-white/10 pb-4">
            <div>
              <p class="text-sm font-medium text-white">今日经营简报</p>
              <p class="mt-1 text-[11px] text-slate-500">数据每 5 分钟自动同步</p>
            </div>
            <span class="flex items-center gap-1.5 text-[11px] text-brand-400">
              <span class="size-1.5 animate-pulse rounded-full bg-brand-400"></span>
              实时更新
            </span>
          </div>

          <div class="grid grid-cols-3 gap-3 py-5">
            <div>
              <p class="text-[11px] text-slate-500">今日成交额</p>
              <p class="mt-2 font-display text-xl font-bold text-white">¥128,430</p>
              <p class="mt-1.5 flex items-center gap-1 text-[11px] text-brand-400">
                <TrendingUp class="size-3" /> 12.5%
              </p>
            </div>
            <div class="border-l border-white/10 pl-4">
              <p class="text-[11px] text-slate-500">支付订单</p>
              <p class="mt-2 font-display text-xl font-bold text-white">1,286</p>
              <p class="mt-1.5 flex items-center gap-1 text-[11px] text-brand-400">
                <TrendingUp class="size-3" /> 8.2%
              </p>
            </div>
            <div class="border-l border-white/10 pl-4">
              <p class="text-[11px] text-slate-500">售后完结率</p>
              <p class="mt-2 font-display text-xl font-bold text-white">96.8%</p>
              <p class="mt-1.5 text-[11px] text-slate-500">稳定运行</p>
            </div>
          </div>

          <div class="flex h-16 items-end gap-2" aria-hidden="true">
            <span
              v-for="(height, index) in [30, 46, 38, 60, 52, 74, 64, 86, 72, 94, 82, 100]"
              :key="index"
              class="flex-1 rounded-t-sm bg-gradient-to-t from-brand-500/20 to-brand-400/80"
              :style="{ height: `${height}%` }"
            ></span>
          </div>
        </div>

        <div class="stagger-in mt-7 flex flex-wrap gap-x-6 gap-y-3 text-xs text-slate-400" style="animation-delay: 240ms">
          <span class="flex items-center gap-2"><PackageCheck class="size-4 text-brand-400" />全链路业务协同</span>
          <span class="flex items-center gap-2"><CircleCheck class="size-4 text-brand-400" />精细化权限管理</span>
          <span class="flex items-center gap-2"><Headphones class="size-4 text-brand-400" />全天候服务保障</span>
        </div>
      </div>

      <footer class="relative z-10 flex items-center gap-2 px-12 pb-8 text-[11px] text-slate-500 xl:px-16">
        <ShieldCheck class="size-3.5" />
        企业级数据加密与访问控制，守护每一项业务数据
      </footer>
    </section>

    <!-- 登录表单区 -->
    <section class="relative flex min-h-screen flex-1 flex-col bg-white">
      <div class="flex items-center justify-between px-6 pt-6 sm:px-10 lg:justify-end lg:px-12">
        <BrandLogo class="lg:hidden" />
        <button
          type="button"
          class="text-xs text-slate-500 transition hover:text-brand-600"
          @click="notice = '如需开通账号或重置密码，请联系企业系统管理员。'"
        >
          需要帮助？
        </button>
      </div>

      <div class="flex flex-1 items-center justify-center px-6 py-12 sm:px-10">
        <div class="stagger-in w-full max-w-[400px]">
          <div class="mb-9">
            <div class="mb-6 hidden size-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 lg:flex">
              <LockKeyhole class="size-5" />
            </div>
            <p class="mb-2 text-xs font-medium tracking-[0.18em] text-brand-600">WELCOME BACK</p>
            <h2 class="text-[30px] font-semibold tracking-tight text-ink-950">欢迎回来</h2>
            <p class="mt-3 text-sm leading-6 text-slate-500">登录您的账号，继续管理今日业务。</p>
          </div>

          <form novalidate @submit.prevent="handleSubmit">
            <div>
              <label for="username" class="mb-2 block text-sm font-medium text-ink-800">用户名</label>
              <div class="relative">
                <UserRound class="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                <input
                  id="username"
                  v-model="form.username"
                  type="text"
                  autocomplete="username"
                  placeholder="请输入用户名"
                  class="form-input"
                  :class="{ '!border-red-400 !ring-red-500/10': errors.username }"
                  :aria-invalid="Boolean(errors.username)"
                  aria-describedby="username-error"
                  @input="errors.username = ''; errors.form = ''"
                />
              </div>
              <p v-if="errors.username" id="username-error" class="mt-2 text-xs text-red-500">{{ errors.username }}</p>
            </div>

            <div class="mt-5">
              <label for="password" class="mb-2 block text-sm font-medium text-ink-800">密码</label>
              <div class="relative">
                <LockKeyhole class="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                <input
                  id="password"
                  v-model="form.password"
                  :type="showPassword ? 'text' : 'password'"
                  autocomplete="current-password"
                  placeholder="请输入密码"
                  class="form-input pr-12"
                  :class="{ '!border-red-400 !ring-red-500/10': errors.password }"
                  :aria-invalid="Boolean(errors.password)"
                  aria-describedby="password-error"
                  @input="errors.password = ''; errors.form = ''"
                  @keyup="capsLockOn = $event.getModifierState('CapsLock')"
                  @blur="capsLockOn = false"
                />
                <button
                  type="button"
                  class="absolute right-2 top-1/2 flex size-9 -translate-y-1/2 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-50 hover:text-ink-700"
                  :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                  @click="showPassword = !showPassword"
                >
                  <EyeOff v-if="showPassword" class="size-4" />
                  <Eye v-else class="size-4" />
                </button>
              </div>
              <p v-if="errors.password" id="password-error" class="mt-2 text-xs text-red-500">{{ errors.password }}</p>
              <p v-else-if="capsLockOn" class="mt-2 text-xs text-amber-600">大写锁定已开启，请注意密码大小写。</p>
            </div>

            <div class="mt-5 flex items-center justify-between">
              <label class="group flex cursor-pointer items-center gap-2.5 text-sm text-slate-600">
                <input v-model="form.remember" type="checkbox" class="peer sr-only" />
                <span class="flex size-[18px] items-center justify-center rounded border border-slate-300 bg-white transition peer-checked:border-brand-600 peer-checked:bg-brand-600 peer-focus-visible:ring-4 peer-focus-visible:ring-brand-500/10">
                  <Check v-if="form.remember" class="size-3 text-white" :stroke-width="3" />
                </span>
                记住我
              </label>
              <button
                type="button"
                class="text-sm text-brand-600 transition hover:text-brand-700"
                @click="notice = '请联系企业系统管理员重置密码。'"
              >
                忘记密码？
              </button>
            </div>

            <Transition name="fade">
              <div v-if="errors.form" class="mt-5 flex items-start gap-2 rounded-xl bg-red-50 px-3.5 py-3 text-xs leading-5 text-red-600" role="alert">
                <Info class="mt-0.5 size-4 shrink-0" />{{ errors.form }}
              </div>
              <div v-else-if="notice" class="mt-5 flex items-start gap-2 rounded-xl bg-brand-50 px-3.5 py-3 text-xs leading-5 text-brand-700" role="status">
                <Info class="mt-0.5 size-4 shrink-0" />{{ notice }}
              </div>
            </Transition>

            <button
              type="submit"
              class="mt-7 flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-ink-950 text-sm font-semibold text-white shadow-lg shadow-ink-950/10 transition hover:bg-ink-800 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="loading"
            >
              <LoaderCircle v-if="loading" class="size-4 animate-spin" />
              <span>{{ loading ? '正在安全登录...' : '登 录' }}</span>
              <ArrowRight v-if="!loading" class="size-4" />
            </button>
          </form>

          <button
            type="button"
            class="mt-5 flex w-full items-center justify-between rounded-xl border border-dashed border-slate-200 bg-slate-50/70 px-4 py-3 text-left transition hover:border-brand-200 hover:bg-brand-50/50"
            @click="fillDemoAccount"
          >
            <span>
              <span class="block text-xs font-medium text-ink-700">演示账号</span>
              <span class="mt-1 block font-display text-[11px] text-slate-400">admin / admin123</span>
            </span>
            <span class="text-xs font-medium text-brand-600">一键填充</span>
          </button>
        </div>
      </div>

      <footer class="px-6 pb-6 text-center text-[11px] leading-5 text-slate-400">
        <p>© 2026 自营后台管理系统</p>
        <p class="mt-1">登录即代表您同意遵守企业信息安全与操作规范</p>
      </footer>
    </section>
  </main>
</template>
