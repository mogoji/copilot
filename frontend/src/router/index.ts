import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '@/views/LoginView.vue'
import DashboardView from '@/views/DashboardView.vue'
import ProfileView from '@/views/ProfileView.vue'
import { isAdmin } from '@/api/auth'
import { AUTH_KEY, TOKEN_KEY } from '@/api/request'

// 重新导出，保持现有 `import { AUTH_KEY } from '@/router'` 的调用点无需改动
export { AUTH_KEY }

export function isAuthenticated() {
  // 以 JWT token 是否存在作为登录态判定的单一真源
  return Boolean(
    localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY),
  )
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/dashboard' },
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { title: '登录', public: true },
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: DashboardView,
      meta: { title: '运营概览', requiresAuth: true },
    },
    {
      path: '/profile',
      name: 'profile',
      component: ProfileView,
      meta: { title: '个人中心', requiresAuth: true },
    },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ],
})

router.beforeEach((to) => {
  if (to.meta.requiresAuth && !isAuthenticated()) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && isAuthenticated()) {
    return { name: 'dashboard' }
  }
  // 知识库管理仅管理员可访问：直接改 URL 也会被重定向回个人信息页
  if (to.name === 'profile' && to.query.tab === 'kb' && !isAdmin()) {
    return { name: 'profile', query: {} }
  }
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title)} · 自营后台管理系统`
})

export default router
