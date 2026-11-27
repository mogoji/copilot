<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, type Component } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Bell,
  Box,
  CalendarDays,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CircleHelp,
  ClipboardCheck,
  Clock3,
  Download,
  Headphones,
  LayoutDashboard,
  LoaderCircle,
  LogOut,
  Menu,
  MoreHorizontal,
  Package,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  RefreshCw,
  Search,
  SearchX,
  Settings,
  ShieldCheck,
  ShoppingCart,
  Store,
  Truck,
  UserRound,
  Users,
  WalletCards,
  Warehouse,
} from 'lucide-vue-next'
import BrandLogo from '@/components/BrandLogo.vue'
import CustomerServiceWidget from '@/components/CustomerServiceWidget.vue'
import { AUTH_KEY } from '@/router'
import { TOKEN_KEY } from '@/api/request'

type MenuItem = { label: string; icon: Component; badge?: string }
type MenuSection = { title: string; items: MenuItem[] }
type RangeKey = 'week' | 'month' | 'year'
type OrderStatus = '待发货' | '已完成' | '售后中' | '已取消'
type Order = {
  id: string
  customer: string
  product: string
  amount: string
  status: OrderStatus
  time: string
}

const router = useRouter()
const sidebarCollapsed = ref(false)
const mobileSidebarOpen = ref(false)
const userMenuOpen = ref(false)
const notificationOpen = ref(false)
const globalSearch = ref('')
const activeMenu = ref('运营概览')
const refreshing = ref(false)
const toast = ref('')
let toastTimer: number | undefined

const now = new Date()
const today = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: 'long',
  day: 'numeric',
  weekday: 'long',
}).format(now)
const greeting = now.getHours() < 12 ? '上午好' : now.getHours() < 18 ? '下午好' : '晚上好'

const menuSections: MenuSection[] = [
  {
    title: '工作空间',
    items: [{ label: '运营概览', icon: LayoutDashboard }],
  },
  {
    title: '经营管理',
    items: [
      { label: '商品管理', icon: Package },
      { label: '订单管理', icon: ShoppingCart, badge: '8' },
      { label: '库存管理', icon: Warehouse },
    ],
  },
  {
    title: '客户与服务',
    items: [
      { label: '售后工单', icon: Headphones, badge: '12' },
      { label: '客户管理', icon: Users },
    ],
  },
  {
    title: '系统',
    items: [{ label: '系统设置', icon: Settings }],
  },
]

const stats = [
  {
    label: '今日成交额',
    value: '¥128,430',
    change: '12.5%',
    trend: 'up',
    icon: WalletCards,
    tone: 'bg-brand-50 text-brand-600',
    spark: 'M1 24 C12 24 13 17 24 18 S37 8 48 11 S63 3 79 4',
  },
  {
    label: '支付订单',
    value: '1,286',
    change: '8.2%',
    trend: 'up',
    icon: ShoppingCart,
    tone: 'bg-blue-50 text-blue-600',
    spark: 'M1 22 C12 19 17 22 25 16 S42 18 49 10 S66 13 79 5',
  },
  {
    label: '待发货订单',
    value: '86',
    change: '3.1%',
    trend: 'down',
    icon: Truck,
    tone: 'bg-amber-50 text-amber-600',
    spark: 'M1 8 C12 10 17 5 27 12 S39 9 50 17 S64 15 79 23',
  },
  {
    label: '售后处理率',
    value: '96.8%',
    change: '1.6%',
    trend: 'up',
    icon: ClipboardCheck,
    tone: 'bg-violet-50 text-violet-600',
    spark: 'M1 22 C12 22 17 15 27 17 S41 6 52 9 S67 4 79 7',
  },
]

const chartSets: Record<RangeKey, { labels: string[]; values: number[]; total: string; change: string }> = {
  week: {
    labels: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
    values: [68, 82, 76, 98, 92, 126, 128],
    total: '¥670,400',
    change: '12.5%',
  },
  month: {
    labels: ['1日', '5日', '9日', '13日', '17日', '21日', '25日'],
    values: [72, 90, 84, 118, 106, 142, 154],
    total: '¥2,864,900',
    change: '18.3%',
  },
  year: {
    labels: ['1月', '3月', '5月', '7月', '9月', '11月', '12月'],
    values: [86, 96, 116, 108, 138, 168, 182],
    total: '¥18,426,000',
    change: '24.8%',
  },
}
const activeRange = ref<RangeKey>('week')
const activePoint = ref<number | null>(null)

const chartPoints = computed(() => {
  const dataset = chartSets[activeRange.value]
  const max = Math.max(...dataset.values) * 1.15
  const step = dataset.values.length > 1 ? 660 / (dataset.values.length - 1) : 0
  return dataset.values.map((value, index) => ({
    x: 48 + index * step,
    y: 224 - (value / max) * 176,
    value,
    label: dataset.labels[index] ?? '',
  }))
})

const linePath = computed(() =>
  chartPoints.value.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' '),
)
const areaPath = computed(() => {
  const first = chartPoints.value[0]
  const last = chartPoints.value.at(-1)
  if (!first || !last) return ''
  return `${linePath.value} L ${last.x} 224 L ${first.x} 224 Z`
})
const yTicks = computed(() => {
  const values = chartSets[activeRange.value].values
  const max = Math.max(...values) * 1.15
  return [1, 0.75, 0.5, 0.25, 0].map((ratio) => ({
    y: 48 + (1 - ratio) * 176,
    label: ratio === 0 ? '0' : `${Math.round((max * ratio) / 10)}k`,
  }))
})
const hoveredPoint = computed(() =>
  activePoint.value === null ? null : (chartPoints.value[activePoint.value] ?? null),
)

function setRange(range: RangeKey) {
  activeRange.value = range
  activePoint.value = null
}

const todos = ref([
  { id: 1, title: '审核售后申请', detail: '12 笔申请等待处理', icon: Headphones, tone: 'bg-orange-50 text-orange-600', done: false },
  { id: 2, title: '处理缺货预警', detail: '6 个商品低于安全库存', icon: CircleAlert, tone: 'bg-red-50 text-red-500', done: false },
  { id: 3, title: '确认今日发货', detail: '86 笔订单等待出库', icon: Truck, tone: 'bg-blue-50 text-blue-600', done: false },
  { id: 4, title: '完善商品资料', detail: '3 个新品待补充详情', icon: Box, tone: 'bg-brand-50 text-brand-600', done: false },
])
const pendingTodos = computed(() => todos.value.filter((item) => !item.done).length)

function toggleTodo(id: number) {
  const item = todos.value.find((todo) => todo.id === id)
  if (!item) return
  item.done = !item.done
  notify(item.done ? `已完成「${item.title}」` : `已恢复「${item.title}」`)
}

const orders = ref<Order[]>([
  { id: 'ZY202611250018', customer: '陈女士', product: '轻氧便携空气净化器', amount: '¥1,299.00', status: '待发货', time: '10:42' },
  { id: 'ZY202611250017', customer: '林先生', product: '云感人体工学办公椅', amount: '¥2,680.00', status: '已完成', time: '10:28' },
  { id: 'ZY202611250016', customer: '周先生', product: '恒温暖饮杯垫套装', amount: '¥329.00', status: '售后中', time: '10:16' },
  { id: 'ZY202611250015', customer: '许女士', product: '原野香薰礼盒', amount: '¥459.00', status: '待发货', time: '09:54' },
  { id: 'ZY202611250014', customer: '郭先生', product: '极简机械键盘 Pro', amount: '¥899.00', status: '已完成', time: '09:38' },
  { id: 'ZY202611250013', customer: '唐女士', product: '零压记忆棉枕', amount: '¥399.00', status: '已取消', time: '09:21' },
  { id: 'ZY202611250012', customer: '沈先生', product: '山系便携露营灯', amount: '¥269.00', status: '已完成', time: '08:56' },
  { id: 'ZY202611250011', customer: '叶女士', product: '轻氧便携空气净化器', amount: '¥1,299.00', status: '待发货', time: '08:32' },
])
const orderQuery = ref('')
const orderStatus = ref('全部')
const currentPage = ref(1)
const pageSize = 5
const statusOptions = ['全部', '待发货', '已完成', '售后中', '已取消']
const statusClasses: Record<OrderStatus, string> = {
  待发货: 'bg-amber-50 text-amber-700 ring-amber-600/15',
  已完成: 'bg-brand-50 text-brand-700 ring-brand-600/15',
  售后中: 'bg-blue-50 text-blue-700 ring-blue-600/15',
  已取消: 'bg-slate-100 text-slate-500 ring-slate-500/10',
}
const filteredOrders = computed(() => {
  const keyword = orderQuery.value.trim().toLowerCase()
  return orders.value.filter((order) => {
    const matchStatus = orderStatus.value === '全部' || order.status === orderStatus.value
    const matchKeyword =
      !keyword ||
      `${order.id}${order.customer}${order.product}`.toLowerCase().includes(keyword)
    return matchStatus && matchKeyword
  })
})
const pageCount = computed(() => Math.max(1, Math.ceil(filteredOrders.value.length / pageSize)))
const pagedOrders = computed(() =>
  filteredOrders.value.slice((currentPage.value - 1) * pageSize, currentPage.value * pageSize),
)
watch([orderQuery, orderStatus], () => {
  currentPage.value = 1
})
watch(pageCount, (count) => {
  if (currentPage.value > count) currentPage.value = count
})

const notifications = ref([
  { id: 1, title: '新的售后申请', detail: '订单 ZY202611250016 提交了退款申请', time: '5 分钟前', read: false, icon: Headphones },
  { id: 2, title: '库存预警提醒', detail: '「山系便携露营灯」库存低于安全值', time: '28 分钟前', read: false, icon: CircleAlert },
  { id: 3, title: '日报已生成', detail: '昨日运营数据日报已完成汇总', time: '1 小时前', read: true, icon: ClipboardCheck },
])
const unreadCount = computed(() => notifications.value.filter((item) => !item.read).length)

function notify(message: string) {
  toast.value = message
  if (toastTimer) window.clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => {
    toast.value = ''
  }, 2600)
}

function selectMenu(label: string) {
  activeMenu.value = label
  mobileSidebarOpen.value = false
  if (label !== '运营概览') {
    notify(`已选择「${label}」，本页保留运营概览演示数据`)
  }
}

function markAllRead() {
  notifications.value.forEach((item) => {
    item.read = true
  })
  notify('所有通知已标记为已读')
}

async function refreshData() {
  if (refreshing.value) return
  refreshing.value = true
  await new Promise((resolve) => window.setTimeout(resolve, 650))
  refreshing.value = false
  notify('运营数据已更新至最新状态')
}

function exportReport() {
  // 直接导出当前订单数据，便于在无后端环境下验证完整交互。
  const header = '订单号,客户,商品,金额,状态,时间\n'
  const rows = filteredOrders.value
    .map((order) => [order.id, order.customer, order.product, order.amount, order.status, order.time].join(','))
    .join('\n')
  const blob = new Blob([`\ufeff${header}${rows}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = '自营运营订单报表.csv'
  link.click()
  URL.revokeObjectURL(url)
  notify('订单报表已导出')
}

function logout() {
  localStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(AUTH_KEY)
  sessionStorage.removeItem(AUTH_KEY)
  userMenuOpen.value = false
  router.replace('/login')
}

function handleDocumentClick(event: MouseEvent) {
  const target = event.target as HTMLElement
  if (!target.closest('[data-user-menu]')) userMenuOpen.value = false
  if (!target.closest('[data-notification-menu]')) notificationOpen.value = false
}

function handleEscape(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    userMenuOpen.value = false
    notificationOpen.value = false
    mobileSidebarOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleDocumentClick)
  window.addEventListener('keydown', handleEscape)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick)
  window.removeEventListener('keydown', handleEscape)
  if (toastTimer) window.clearTimeout(toastTimer)
})
</script>

<template>
  <div class="min-h-screen bg-canvas text-ink-800">
    <!-- 移动端侧栏遮罩 -->
    <Transition name="fade">
      <button
        v-if="mobileSidebarOpen"
        type="button"
        class="fixed inset-0 z-40 bg-ink-950/45 backdrop-blur-sm lg:hidden"
        aria-label="关闭导航菜单"
        @click="mobileSidebarOpen = false"
      ></button>
    </Transition>

    <!-- 侧边导航 -->
    <aside
      class="fixed inset-y-0 left-0 z-50 flex w-[248px] flex-col bg-ink-950 text-slate-300 transition-[width,transform] duration-300"
      :class="[
        sidebarCollapsed ? 'lg:w-[84px]' : 'lg:w-[248px]',
        mobileSidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
      ]"
    >
      <div class="flex h-[72px] shrink-0 items-center border-b border-white/[0.07] px-5">
        <div :class="sidebarCollapsed ? 'lg:hidden' : ''">
          <BrandLogo inverse />
        </div>
        <div v-if="sidebarCollapsed" class="hidden lg:block">
          <BrandLogo inverse compact />
        </div>
      </div>

      <nav class="flex-1 overflow-y-auto px-3 py-5" aria-label="主导航">
        <div v-for="section in menuSections" :key="section.title" class="mb-5 last:mb-0">
          <p
            class="mb-2 px-3 text-[10px] font-medium tracking-[0.16em] text-slate-600"
            :class="sidebarCollapsed ? 'lg:hidden' : ''"
          >
            {{ section.title }}
          </p>
          <div class="space-y-1">
            <button
              v-for="item in section.items"
              :key="item.label"
              type="button"
              :title="sidebarCollapsed ? item.label : undefined"
              class="group relative flex h-11 w-full items-center gap-3 rounded-xl px-3 text-sm transition"
              :class="[
                activeMenu === item.label
                  ? 'bg-brand-500/15 font-medium text-white'
                  : 'text-slate-400 hover:bg-white/[0.055] hover:text-white',
                sidebarCollapsed ? 'lg:justify-center lg:px-0' : '',
              ]"
              @click="selectMenu(item.label)"
            >
              <span
                v-if="activeMenu === item.label"
                class="absolute -left-3 h-5 w-1 rounded-r-full bg-brand-400"
              ></span>
              <component
                :is="item.icon"
                class="size-[18px] shrink-0"
                :class="activeMenu === item.label ? 'text-brand-400' : 'text-slate-500 group-hover:text-slate-300'"
              />
              <span class="flex-1 text-left" :class="sidebarCollapsed ? 'lg:hidden' : ''">{{ item.label }}</span>
              <span
                v-if="item.badge"
                class="rounded-md bg-white/10 px-1.5 py-0.5 font-display text-[10px] font-semibold text-slate-300"
                :class="sidebarCollapsed ? 'lg:hidden' : ''"
              >{{ item.badge }}</span>
            </button>
          </div>
        </div>
      </nav>

      <div class="p-3">
        <div
          class="mb-3 rounded-xl border border-white/[0.08] bg-white/[0.045] p-3.5"
          :class="sidebarCollapsed ? 'lg:hidden' : ''"
        >
          <div class="flex items-center gap-2 text-xs font-medium text-white">
            <CircleHelp class="size-4 text-brand-400" /> 使用帮助
          </div>
          <p class="mt-2 text-[11px] leading-5 text-slate-500">查看操作手册或联系专属技术支持。</p>
          <button type="button" class="mt-3 flex items-center gap-1 text-[11px] font-medium text-brand-400 hover:text-brand-200" @click="notify('帮助中心将在新模块中提供')">
            打开帮助中心 <ArrowRight class="size-3" />
          </button>
        </div>
        <button
          type="button"
          class="hidden h-10 w-full items-center justify-center gap-2 rounded-xl text-slate-500 transition hover:bg-white/5 hover:text-white lg:flex"
          :aria-label="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
          @click="sidebarCollapsed = !sidebarCollapsed"
        >
          <PanelLeftOpen v-if="sidebarCollapsed" class="size-[18px]" />
          <PanelLeftClose v-else class="size-[18px]" />
          <span v-if="!sidebarCollapsed" class="text-xs">收起导航</span>
        </button>
      </div>
    </aside>

    <!-- 顶部导航 + 主工作区 -->
    <div class="min-h-screen transition-[padding] duration-300" :class="sidebarCollapsed ? 'lg:pl-[84px]' : 'lg:pl-[248px]'">
      <header class="sticky top-0 z-30 flex h-[72px] items-center border-b border-slate-200/80 bg-white/95 px-4 backdrop-blur-md sm:px-6">
        <button type="button" class="icon-button mr-1 lg:hidden" aria-label="打开导航菜单" @click="mobileSidebarOpen = true">
          <Menu class="size-5" />
        </button>

        <div class="min-w-0">
          <div class="flex items-center gap-2 text-xs text-slate-400">
            <span>工作空间</span>
            <ChevronRight class="size-3" />
            <span class="truncate text-ink-700">{{ activeMenu }}</span>
          </div>
          <p class="mt-0.5 hidden text-[11px] text-slate-400 sm:block">统一管理和分析您的自营业务</p>
        </div>

        <div class="ml-auto flex items-center gap-1.5 sm:gap-3">
          <div class="relative mr-1 hidden xl:block">
            <Search class="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
            <input
              v-model="globalSearch"
              type="search"
              placeholder="搜索订单、商品或功能"
              class="h-10 w-64 rounded-xl border border-slate-200 bg-slate-50 pl-10 pr-12 text-xs text-ink-800 outline-none transition placeholder:text-slate-400 focus:border-brand-400 focus:bg-white focus:ring-4 focus:ring-brand-500/10"
              @keyup.enter="notify(globalSearch ? `正在搜索「${globalSearch}」` : '请输入搜索内容')"
            />
            <kbd class="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 rounded border border-slate-200 bg-white px-1.5 py-0.5 font-display text-[9px] text-slate-400">Enter</kbd>
          </div>

          <!-- 通知 -->
          <div class="relative" data-notification-menu>
            <button
              type="button"
              class="icon-button relative"
              :class="{ '!bg-slate-100 !text-ink-800': notificationOpen }"
              aria-label="查看通知"
              :aria-expanded="notificationOpen"
              @click.stop="notificationOpen = !notificationOpen; userMenuOpen = false"
            >
              <Bell class="size-[19px]" />
              <span v-if="unreadCount" class="absolute right-2 top-2 size-2 rounded-full border-2 border-white bg-red-500"></span>
            </button>
            <Transition name="dropdown">
              <div v-if="notificationOpen" class="absolute right-0 top-12 w-[min(360px,calc(100vw-32px))] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl shadow-ink-950/10">
                <div class="flex items-center justify-between border-b border-slate-100 px-4 py-3.5">
                  <div>
                    <p class="text-sm font-semibold text-ink-900">消息通知</p>
                    <p class="mt-0.5 text-[11px] text-slate-400">{{ unreadCount }} 条未读消息</p>
                  </div>
                  <button type="button" class="flex items-center gap-1 text-[11px] text-brand-600 hover:text-brand-700" @click="markAllRead">
                    <CheckCheck class="size-3.5" /> 全部已读
                  </button>
                </div>
                <div class="max-h-[340px] overflow-y-auto">
                  <button
                    v-for="item in notifications"
                    :key="item.id"
                    type="button"
                    class="flex w-full gap-3 border-b border-slate-100 px-4 py-3.5 text-left transition last:border-0 hover:bg-slate-50"
                    @click="item.read = true"
                  >
                    <span class="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg" :class="item.read ? 'bg-slate-100 text-slate-400' : 'bg-brand-50 text-brand-600'">
                      <component :is="item.icon" class="size-4" />
                    </span>
                    <span class="min-w-0 flex-1">
                      <span class="flex items-center gap-2">
                        <span class="truncate text-xs font-medium" :class="item.read ? 'text-slate-500' : 'text-ink-800'">{{ item.title }}</span>
                        <span v-if="!item.read" class="size-1.5 shrink-0 rounded-full bg-brand-500"></span>
                      </span>
                      <span class="mt-1 block truncate text-[11px] text-slate-400">{{ item.detail }}</span>
                      <span class="mt-1.5 block text-[10px] text-slate-400">{{ item.time }}</span>
                    </span>
                  </button>
                </div>
              </div>
            </Transition>
          </div>

          <span class="mx-1 hidden h-6 w-px bg-slate-200 sm:block"></span>

          <!-- 用户菜单 -->
          <div class="relative" data-user-menu>
            <button
              type="button"
              class="flex items-center gap-2.5 rounded-xl p-1.5 transition hover:bg-slate-50 sm:pr-2"
              :aria-expanded="userMenuOpen"
              @click.stop="userMenuOpen = !userMenuOpen; notificationOpen = false"
            >
              <span class="flex size-9 items-center justify-center rounded-xl bg-ink-900 font-display text-xs font-bold text-white ring-2 ring-brand-100">AD</span>
              <span class="hidden text-left md:block">
                <span class="block text-xs font-semibold text-ink-800">系统管理员</span>
                <span class="mt-0.5 block text-[10px] text-slate-400">admin</span>
              </span>
              <ChevronDown class="hidden size-3.5 text-slate-400 transition md:block" :class="{ 'rotate-180': userMenuOpen }" />
            </button>
            <Transition name="dropdown">
              <div v-if="userMenuOpen" class="absolute right-0 top-14 w-56 rounded-2xl border border-slate-200 bg-white p-2 shadow-xl shadow-ink-950/10">
                <div class="border-b border-slate-100 px-3 pb-3 pt-2">
                  <p class="text-sm font-semibold text-ink-900">系统管理员</p>
                  <p class="mt-1 text-[11px] text-slate-400">admin@self-operated.cn</p>
                </div>
                <button type="button" class="mt-2 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-xs text-ink-700 transition hover:bg-slate-50" @click="router.push('/profile'); userMenuOpen = false">
                  <UserRound class="size-4 text-slate-400" /> 个人中心
                </button>
                <button type="button" class="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-xs text-ink-700 transition hover:bg-slate-50" @click="notify('账号设置演示入口'); userMenuOpen = false">
                  <ShieldCheck class="size-4 text-slate-400" /> 账号与安全
                </button>
                <div class="my-2 h-px bg-slate-100"></div>
                <button type="button" class="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-xs text-red-600 transition hover:bg-red-50" @click="logout">
                  <LogOut class="size-4" /> 退出登录
                </button>
              </div>
            </Transition>
          </div>
        </div>
      </header>

      <main class="mx-auto max-w-[1600px] p-4 sm:p-6 xl:p-7">
        <!-- 页面标题与操作 -->
        <section class="stagger-in mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div>
            <div class="flex items-center gap-2 text-xs text-slate-400">
              <CalendarDays class="size-3.5" />{{ today }}
            </div>
            <h1 class="mt-2 text-[26px] font-semibold tracking-tight text-ink-950">{{ greeting }}，管理员</h1>
            <p class="mt-1.5 text-sm text-slate-500">这是您今天的经营概况，所有核心业务运转正常。</p>
          </div>
          <!-- 右侧预留 72px，避免与悬浮的智能客服入口重叠 -->
          <div class="flex shrink-0 items-center gap-2.5 sm:pr-[72px]">
            <button type="button" class="secondary-button" @click="exportReport">
              <Download class="size-4" /> 导出报表
            </button>
            <button type="button" class="primary-button" :disabled="refreshing" @click="refreshData">
              <LoaderCircle v-if="refreshing" class="size-4 animate-spin" />
              <RefreshCw v-else class="size-4" />
              {{ refreshing ? '更新中' : '刷新数据' }}
            </button>
          </div>
        </section>

        <!-- 核心指标 -->
        <section class="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 2xl:grid-cols-4" aria-label="核心经营指标">
          <article
            v-for="(stat, index) in stats"
            :key="stat.label"
            class="panel-card stagger-in group relative overflow-hidden p-5 transition duration-300 hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-lg hover:shadow-ink-950/[0.04]"
            :style="{ animationDelay: `${index * 55 + 60}ms` }"
          >
            <div class="flex items-start justify-between">
              <span class="flex size-10 items-center justify-center rounded-xl" :class="stat.tone">
                <component :is="stat.icon" class="size-[19px]" />
              </span>
              <span
                class="flex items-center gap-1 rounded-md px-1.5 py-1 font-display text-[11px] font-bold"
                :class="stat.trend === 'up' ? 'bg-brand-50 text-brand-600' : 'bg-blue-50 text-blue-600'"
              >
                <ArrowUpRight v-if="stat.trend === 'up'" class="size-3" />
                <ArrowDownRight v-else class="size-3" />
                {{ stat.change }}
              </span>
            </div>
            <p class="mt-5 text-xs text-slate-500">{{ stat.label }}</p>
            <div class="mt-1.5 flex items-end justify-between gap-3">
              <p class="font-display text-[28px] font-bold leading-tight tracking-tight text-ink-950">{{ stat.value }}</p>
              <svg class="h-7 w-20 overflow-visible" viewBox="0 0 80 28" fill="none" aria-hidden="true">
                <path :d="stat.spark" :stroke="stat.trend === 'up' ? '#139a75' : '#5385b5'" stroke-width="2" stroke-linecap="round" />
              </svg>
            </div>
            <p class="mt-2 text-[10px] text-slate-400">较上一统计周期</p>
          </article>
        </section>

        <!-- 趋势 + 待办 -->
        <section class="mb-6 grid grid-cols-1 gap-5 xl:grid-cols-12">
          <article class="panel-card stagger-in overflow-hidden xl:col-span-8" style="animation-delay: 240ms">
            <div class="flex flex-col gap-4 border-b border-slate-100 px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
              <div>
                <h2 class="text-sm font-semibold text-ink-900">成交趋势</h2>
                <p class="mt-1 text-[11px] text-slate-400">统计周期内每日支付成交金额</p>
              </div>
              <div class="flex rounded-lg bg-slate-100 p-1">
                <button
                  v-for="option in ([['week', '近7日'], ['month', '近30日'], ['year', '本年度']] as const)"
                  :key="option[0]"
                  type="button"
                  class="rounded-md px-3 py-1.5 text-[11px] transition"
                  :class="activeRange === option[0] ? 'bg-white font-medium text-ink-900 shadow-sm' : 'text-slate-500 hover:text-ink-800'"
                  @click="setRange(option[0])"
                >{{ option[1] }}</button>
              </div>
            </div>
            <div class="px-5 pb-5 pt-5 sm:px-6">
              <div class="mb-2 flex flex-wrap items-end gap-x-4 gap-y-2">
                <div>
                  <p class="text-[11px] text-slate-400">累计成交额</p>
                  <p class="mt-1 font-display text-2xl font-bold text-ink-950">{{ chartSets[activeRange].total }}</p>
                </div>
                <span class="mb-1 flex items-center gap-1 text-[11px] font-medium text-brand-600">
                  <ArrowUpRight class="size-3.5" />{{ chartSets[activeRange].change }}
                  <span class="font-normal text-slate-400">同比增长</span>
                </span>
              </div>

              <div class="relative mt-1 w-full overflow-x-auto">
                <svg class="h-[280px] min-w-[560px] w-full" viewBox="0 0 760 280" fill="none" role="img" aria-label="成交金额折线图">
                  <defs>
                    <linearGradient id="sales-area" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stop-color="#139a75" stop-opacity="0.22" />
                      <stop offset="100%" stop-color="#139a75" stop-opacity="0" />
                    </linearGradient>
                  </defs>
                  <g v-for="tick in yTicks" :key="tick.y">
                    <line x1="48" :y1="tick.y" x2="716" :y2="tick.y" stroke="#e9edf1" stroke-dasharray="4 5" />
                    <text x="34" :y="tick.y + 3" text-anchor="end" fill="#94a3b8" font-size="9" font-family="Manrope">{{ tick.label }}</text>
                  </g>
                  <path :d="areaPath" fill="url(#sales-area)" />
                  <path :d="linePath" stroke="#139a75" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
                  <g v-for="(point, index) in chartPoints" :key="`${activeRange}-${point.label}`">
                    <text :x="point.x" y="252" text-anchor="middle" fill="#94a3b8" font-size="10">{{ point.label }}</text>
                    <circle :cx="point.x" :cy="point.y" r="10" fill="transparent" @mouseenter="activePoint = index" @mouseleave="activePoint = null" />
                    <circle
                      :cx="point.x"
                      :cy="point.y"
                      :r="activePoint === index ? 5 : 3"
                      fill="white"
                      stroke="#139a75"
                      :stroke-width="activePoint === index ? 3 : 2"
                      class="pointer-events-none transition-all"
                    />
                  </g>
                  <g v-if="hoveredPoint" :transform="`translate(${hoveredPoint.x}, ${hoveredPoint.y})`" class="pointer-events-none">
                    <rect x="-48" y="-55" width="96" height="39" rx="8" fill="#0b1626" />
                    <text x="0" y="-39" text-anchor="middle" fill="#94a3b8" font-size="9">{{ hoveredPoint.label }}</text>
                    <text x="0" y="-26" text-anchor="middle" fill="white" font-size="11" font-weight="600">¥{{ hoveredPoint.value }},000</text>
                    <path d="M-4 -16 L0 -11 L4 -16 Z" fill="#0b1626" />
                  </g>
                </svg>
              </div>
            </div>
          </article>

          <article class="panel-card stagger-in flex flex-col xl:col-span-4" style="animation-delay: 280ms">
            <div class="flex items-center justify-between border-b border-slate-100 px-5 py-5">
              <div>
                <h2 class="text-sm font-semibold text-ink-900">今日待办</h2>
                <p class="mt-1 text-[11px] text-slate-400">{{ pendingTodos }} 项工作等待处理</p>
              </div>
              <span class="flex size-9 items-center justify-center rounded-xl bg-slate-50 text-slate-500"><Clock3 class="size-4" /></span>
            </div>
            <div class="flex-1 divide-y divide-slate-100 px-5">
              <div v-for="item in todos" :key="item.id" class="group flex items-center gap-3 py-4">
                <button
                  type="button"
                  class="flex size-5 shrink-0 items-center justify-center rounded-md border transition"
                  :class="item.done ? 'border-brand-600 bg-brand-600' : 'border-slate-300 bg-white group-hover:border-brand-400'"
                  :aria-label="item.done ? `恢复${item.title}` : `完成${item.title}`"
                  @click="toggleTodo(item.id)"
                >
                  <Check v-if="item.done" class="size-3 text-white" :stroke-width="3" />
                </button>
                <span class="flex size-9 shrink-0 items-center justify-center rounded-xl transition" :class="item.done ? 'bg-slate-50 text-slate-300' : item.tone">
                  <component :is="item.icon" class="size-4" />
                </span>
                <div class="min-w-0 flex-1" :class="{ 'opacity-45': item.done }">
                  <p class="truncate text-xs font-medium text-ink-800" :class="{ 'line-through': item.done }">{{ item.title }}</p>
                  <p class="mt-1 truncate text-[10px] text-slate-400">{{ item.detail }}</p>
                </div>
                <ChevronRight class="size-3.5 shrink-0 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-slate-400" />
              </div>
            </div>
            <button type="button" class="m-4 flex h-9 items-center justify-center gap-1.5 rounded-xl bg-slate-50 text-[11px] font-medium text-slate-500 transition hover:bg-brand-50 hover:text-brand-700" @click="notify('已展示当前全部待办事项')">
              查看全部待办 <ArrowRight class="size-3.5" />
            </button>
          </article>
        </section>

        <!-- 订单列表 + 渠道概况 -->
        <section class="grid grid-cols-1 items-start gap-5 xl:grid-cols-12">
          <article class="panel-card stagger-in overflow-hidden xl:col-span-8" style="animation-delay: 320ms">
            <div class="border-b border-slate-100 px-5 py-5 sm:px-6">
              <div class="flex items-center justify-between gap-3">
                <div>
                  <h2 class="text-sm font-semibold text-ink-900">最新订单</h2>
                  <p class="mt-1 text-[11px] text-slate-400">实时跟踪订单状态与履约进度</p>
                </div>
                <button type="button" class="icon-button !size-8" aria-label="更多订单操作" @click="notify('更多订单操作演示入口')"><MoreHorizontal class="size-4" /></button>
              </div>
              <div class="mt-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div class="flex max-w-full gap-1 overflow-x-auto rounded-lg bg-slate-100 p-1">
                  <button
                    v-for="status in statusOptions"
                    :key="status"
                    type="button"
                    class="shrink-0 rounded-md px-2.5 py-1.5 text-[10px] transition"
                    :class="orderStatus === status ? 'bg-white font-medium text-ink-900 shadow-sm' : 'text-slate-500 hover:text-ink-800'"
                    @click="orderStatus = status"
                  >{{ status }}</button>
                </div>
                <div class="relative lg:w-52">
                  <Search class="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-slate-400" />
                  <input v-model="orderQuery" type="search" placeholder="搜索订单" class="h-9 w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-[11px] outline-none transition placeholder:text-slate-400 focus:border-brand-400 focus:ring-4 focus:ring-brand-500/10" />
                </div>
              </div>
            </div>

            <div class="overflow-x-auto">
              <table class="w-full min-w-[680px] border-collapse text-left">
                <thead>
                  <tr class="bg-slate-50/70 text-[10px] font-medium tracking-wide text-slate-400">
                    <th class="px-6 py-3">订单信息</th>
                    <th class="px-4 py-3">客户</th>
                    <th class="px-4 py-3">金额</th>
                    <th class="px-4 py-3">状态</th>
                    <th class="px-4 py-3">下单时间</th>
                    <th class="px-5 py-3 text-right">操作</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-for="order in pagedOrders" :key="order.id" class="group transition hover:bg-slate-50/60">
                    <td class="px-6 py-4">
                      <p class="max-w-[190px] truncate text-xs font-medium text-ink-800">{{ order.product }}</p>
                      <p class="mt-1 font-display text-[9px] tracking-wide text-slate-400">{{ order.id }}</p>
                    </td>
                    <td class="px-4 py-4">
                      <div class="flex items-center gap-2">
                        <span class="flex size-7 items-center justify-center rounded-lg bg-slate-100 text-[10px] font-medium text-slate-500">{{ order.customer.slice(0, 1) }}</span>
                        <span class="whitespace-nowrap text-[11px] text-ink-700">{{ order.customer }}</span>
                      </div>
                    </td>
                    <td class="whitespace-nowrap px-4 py-4 font-display text-[11px] font-semibold text-ink-900">{{ order.amount }}</td>
                    <td class="px-4 py-4">
                      <span class="inline-flex whitespace-nowrap rounded-md px-2 py-1 text-[10px] ring-1 ring-inset" :class="statusClasses[order.status]">{{ order.status }}</span>
                    </td>
                    <td class="whitespace-nowrap px-4 py-4 font-display text-[10px] text-slate-400">{{ order.time }}</td>
                    <td class="px-5 py-4 text-right">
                      <button type="button" class="text-[11px] font-medium text-brand-600 opacity-80 transition hover:text-brand-700 group-hover:opacity-100" @click="notify(`正在查看订单 ${order.id}`)">查看</button>
                    </td>
                  </tr>
                </tbody>
              </table>
              <div v-if="!pagedOrders.length" class="flex flex-col items-center justify-center px-6 py-14 text-center">
                <span class="flex size-11 items-center justify-center rounded-2xl bg-slate-100 text-slate-400"><SearchX class="size-5" /></span>
                <p class="mt-3 text-xs font-medium text-ink-700">没有找到匹配的订单</p>
                <button type="button" class="mt-2 text-[11px] text-brand-600" @click="orderQuery = ''; orderStatus = '全部'">清除筛选条件</button>
              </div>
            </div>

            <div class="flex flex-col gap-3 border-t border-slate-100 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
              <p class="text-[10px] text-slate-400">共 {{ filteredOrders.length }} 笔订单 · 第 {{ currentPage }}/{{ pageCount }} 页</p>
              <div class="flex items-center gap-2">
                <button type="button" class="icon-button !size-8 !rounded-lg !border-slate-200 disabled:opacity-40" :disabled="currentPage <= 1" aria-label="上一页" @click="currentPage--"><ChevronLeft class="size-3.5" /></button>
                <button type="button" class="icon-button !size-8 !rounded-lg !border-slate-200 disabled:opacity-40" :disabled="currentPage >= pageCount" aria-label="下一页" @click="currentPage++"><ChevronRight class="size-3.5" /></button>
              </div>
            </div>
          </article>

          <div class="space-y-5 xl:col-span-4">
            <article class="panel-card stagger-in p-5" style="animation-delay: 350ms">
              <div class="flex items-center justify-between">
                <div>
                  <h2 class="text-sm font-semibold text-ink-900">销售渠道</h2>
                  <p class="mt-1 text-[11px] text-slate-400">本月成交订单来源分布</p>
                </div>
                <Store class="size-4 text-slate-400" />
              </div>
              <div class="mt-6 flex items-center gap-6">
                <div class="relative size-28 shrink-0 rounded-full" style="background: conic-gradient(#139a75 0 58%, #31577a 58% 82%, #d8a446 82% 100%)">
                  <div class="absolute inset-[13px] flex flex-col items-center justify-center rounded-full bg-white">
                    <span class="font-display text-xl font-bold text-ink-950">8,642</span>
                    <span class="mt-0.5 text-[9px] text-slate-400">总订单</span>
                  </div>
                </div>
                <div class="flex-1 space-y-3">
                  <div v-for="channel in [{ name: '官方商城', value: '58%', color: '#139a75' }, { name: '小程序', value: '24%', color: '#31577a' }, { name: '其他渠道', value: '18%', color: '#d8a446' }]" :key="channel.name">
                    <div class="flex items-center justify-between text-[11px]">
                      <span class="flex items-center gap-2 text-slate-500"><span class="size-2 rounded-full" :style="{ background: channel.color }"></span>{{ channel.name }}</span>
                      <span class="font-display font-semibold text-ink-800">{{ channel.value }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </article>

            <article class="stagger-in overflow-hidden rounded-2xl bg-ink-950 p-5 text-white shadow-lg shadow-ink-950/10" style="animation-delay: 390ms">
              <div class="flex items-start justify-between">
                <span class="flex size-9 items-center justify-center rounded-xl bg-brand-500/15 text-brand-400"><Plus class="size-4" /></span>
                <span class="rounded-full bg-white/[0.06] px-2 py-1 text-[9px] text-slate-400">快捷操作</span>
              </div>
              <h2 class="mt-4 text-sm font-semibold">新增一个商品</h2>
              <p class="mt-2 text-[11px] leading-5 text-slate-400">快速录入商品信息，完善库存后即可上架销售。</p>
              <button type="button" class="mt-5 flex h-9 w-full items-center justify-center gap-2 rounded-xl bg-brand-500 text-[11px] font-semibold text-white transition hover:bg-brand-400" @click="notify('商品创建表单将在商品管理模块中打开')">
                开始创建 <ArrowRight class="size-3.5" />
              </button>
            </article>
          </div>
        </section>

        <footer class="mt-7 flex flex-col gap-2 border-t border-slate-200/70 pt-5 text-[10px] text-slate-400 sm:flex-row sm:items-center sm:justify-between">
          <p>© 2026 自营后台管理系统 · 企业运营工作台</p>
          <p class="flex items-center gap-1.5"><span class="size-1.5 rounded-full bg-brand-500"></span>系统服务正常 · 最近同步 {{ now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}</p>
        </footer>
      </main>
    </div>

    <!-- 智能客服：右上角悬浮入口 + 对话弹窗 -->
    <CustomerServiceWidget />

    <Transition name="toast">
      <div v-if="toast" class="fixed bottom-6 left-1/2 z-[70] flex max-w-[calc(100vw-32px)] -translate-x-1/2 items-center gap-2.5 rounded-xl bg-ink-950 px-4 py-3 text-xs text-white shadow-2xl shadow-ink-950/20" role="status">
        <span class="flex size-5 shrink-0 items-center justify-center rounded-full bg-brand-500/20 text-brand-400"><Check class="size-3" /></span>
        {{ toast }}
      </div>
    </Transition>
  </div>
</template>
