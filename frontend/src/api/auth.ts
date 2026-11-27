/** 认证相关接口：登录 + 从 JWT 中读取当前用户角色 */
import { http } from './request'
import type { ApiResult } from './request'
import { TOKEN_KEY } from './request'

export interface LoginPayload {
  username: string
  password: string
}

export interface UserInfo {
  id: number
  username: string
  nickname: string
  role: string
}

export interface LoginResult {
  access_token: string
  token_type: string
  user: UserInfo
}

/**
 * 登录：POST /api/auth/login
 * 成功返回 { code:0, data:{ access_token, token_type, user } }
 */
export function login(payload: LoginPayload) {
  return http.post<ApiResult<LoginResult>>('/auth/login', payload)
}

export interface TokenPayload {
  sub?: string
  role?: string
  uid?: number
  exp?: number
}

/**
 * 解析 JWT payload（仅取角色/用户名用于界面显示，不做签名校验）。
 * 真正的权限边界在后端 require_admin，前端隐藏入口只是体验层。
 */
export function getTokenPayload(): TokenPayload | null {
  const token =
    localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY)
  if (!token) return null
  const segment = token.split('.')[1]
  if (!segment) return null
  try {
    const base64 = segment.replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4)
    const bytes = atob(padded)
      .split('')
      .map((ch) => `%${`00${ch.charCodeAt(0).toString(16)}`.slice(-2)}`)
      .join('')
    return JSON.parse(decodeURIComponent(bytes)) as TokenPayload
  } catch {
    return null
  }
}

/** 当前登录用户是否为管理员 */
export function isAdmin(): boolean {
  return getTokenPayload()?.role === 'admin'
}
