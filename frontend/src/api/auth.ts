/** 认证相关接口：登录 */
import { http } from './request'
import type { ApiResult } from './request'

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
