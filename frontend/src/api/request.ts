/**
 * axios 实例封装：统一 baseURL、请求拦截（带 token）、响应拦截（拆响应壳 + 错误处理）。
 *
 * 与后端约定的统一响应壳：{ code, message, data }
 *   - 成功：code === 0，data 为业务数据；
 *   - 失败：code 为 HTTP 状态码，message 为错误描述，data 为 null。
 *
 * 单一真源规则（避免前后端契约不一致踩坑）：
 *   - baseURL 固定指向后端的 /api 前缀，业务模块路径写相对路径（如 '/auth/login'），
 *     最终请求 = baseURL + 路径，禁止在模块里再带 /api；
 *   - 响应拦截器 return response.data（即整个响应壳），业务侧直接用 res.data 取业务数据，
 *     不要再写 res.data.data；
 *   - token 字段固定为 access_token，前端只认这一个字段。
 */
import axios, {
  type AxiosInstance,
  type AxiosRequestConfig,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios'

/** localStorage / sessionStorage 中存放 JWT 的键名 */
export const TOKEN_KEY = 'self-operated-token'
/** 路由守卫用的登录态标记键名（与 token 同时写入/清除，保持兼容） */
export const AUTH_KEY = 'self-operated-auth'

/** 后端统一响应壳 */
export interface ApiResult<T = unknown> {
  code: number
  message: string
  data: T
}

const instance: AxiosInstance = axios.create({
  // 可用环境变量 VITE_API_BASE_URL 覆盖；默认直连本地后端以真实触发 CORS。
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

// ---- 请求拦截：自动在 Header 携带 Bearer token ----
instance.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token =
      localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY)
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

// ---- 响应拦截：拆响应壳 + 统一错误处理 ----
instance.interceptors.response.use(
  (response) => {
    const body = response.data as ApiResult
    // 后端即便 HTTP 200，也可能用业务 code 表达失败（如 code !== 0），统一抛错
    if (body && typeof body.code === 'number' && body.code !== 0) {
      return Promise.reject(new Error(body.message || '请求失败'))
    }
    // 返回整个响应壳，业务侧用 res.data 取业务数据。
    // 这里改变了 axios 默认返回形状（AxiosResponse → 响应壳），http 封装已用
    // 泛型把方法返回对齐到响应壳，故此处做类型断言以满足拦截器签名。
    return body as unknown as AxiosResponse
  },
  (error) => {
    const status = error?.response?.status
    // 优先取后端返回的 message，没有则用 axios 自带 message，兜底网络异常
    const message =
      error?.response?.data?.message || error?.message || '网络异常，请稍后重试'
    // 401：token 失效或未登录，清理登录态并跳转登录页（已在登录页则不跳转）
    if (status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      sessionStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(AUTH_KEY)
      sessionStorage.removeItem(AUTH_KEY)
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(new Error(message))
  },
)

/**
 * 轻量封装：把 axios 方法的返回类型直接对齐到响应壳（运行时拦截器已 return body）。
 * 用法：http.post<ApiResult<LoginResult>>('/auth/login', payload)
 */
export const http = {
  get<T = unknown>(url: string, config?: AxiosRequestConfig) {
    return instance.get<unknown, T>(url, config)
  },
  post<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) {
    return instance.post<unknown, T>(url, data, config)
  },
  put<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) {
    return instance.put<unknown, T>(url, data, config)
  },
  delete<T = unknown>(url: string, config?: AxiosRequestConfig) {
    return instance.delete<unknown, T>(url, config)
  },
}

export default instance
