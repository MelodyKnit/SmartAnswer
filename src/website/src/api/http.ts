/**
 * Axios 实例与统一响应处理。
 *
 * - 开发期：Vite 代理把平台接口前缀转发到后端 127.0.0.1:8765，保持同源。
 * - 生产期：通过 VITE_API_BASE 指定后端地址，并以 Bearer 令牌跨域鉴权。
 * - 后端约定：成功 `{ ok: true, ... }`；失败 `{ ok: false, error: { code, message } }` + HTTP 状态码。
 */
import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'

const TOKEN_KEY = 'stqb_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

/** 后端统一错误结构。 */
export interface ApiError {
  code: string
  message: string
}

/** 业务异常：携带后端错误码与 HTTP 状态。 */
export class ApiException extends Error {
  code: string
  status: number
  constructor(message: string, code: string, status: number) {
    super(message)
    this.name = 'ApiException'
    this.code = code
    this.status = status
  }
}

/** 401 回调：由 auth store 注册，用于令牌失效时自动登出并跳转登录。 */
let onUnauthorized: (() => void) | null = null
export function registerUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler
}

const http: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '',
  timeout: 20000,
})

http.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status ?? 0
    const data = error?.response?.data
    const apiError: ApiError | undefined = data?.error
    if (status === 401 && onUnauthorized) {
      onUnauthorized()
    }
    const message =
      apiError?.message || error?.message || '请求失败，请稍后重试'
    const code = apiError?.code || (status ? `HTTP_${status}` : 'NETWORK_ERROR')
    return Promise.reject(new ApiException(message, code, status))
  },
)

/**
 * 发起请求并解包后端响应。
 * 后端始终返回 `{ ok, ... }`；当 ok=false（且 HTTP 2xx）时也抛出业务异常。
 */
export async function request<T = unknown>(config: AxiosRequestConfig): Promise<T> {
  const response = await http.request<Record<string, unknown>>(config)
  const data = response.data
  if (data && typeof data === 'object' && data.ok === false) {
    const err = (data.error as ApiError) || { code: 'UNKNOWN', message: '请求失败' }
    throw new ApiException(err.message, err.code, response.status)
  }
  return data as T
}

export const api = {
  get: <T = unknown>(url: string, params?: Record<string, unknown>) =>
    request<T>({ url, method: 'GET', params }),
  post: <T = unknown>(url: string, body?: unknown) =>
    request<T>({ url, method: 'POST', data: body }),
  patch: <T = unknown>(url: string, body?: unknown) =>
    request<T>({ url, method: 'PATCH', data: body }),
  put: <T = unknown>(url: string, body?: unknown) =>
    request<T>({ url, method: 'PUT', data: body }),
  delete: <T = unknown>(url: string) => request<T>({ url, method: 'DELETE' }),
}


const API_TOKEN_SECRET_PREFIX = 'stqb_api_token_secret:'

export function setApiTokenSecret(tokenId: string, secret: string): void {
  localStorage.setItem(`${API_TOKEN_SECRET_PREFIX}${tokenId}`, secret)
}

export function getApiTokenSecret(tokenId: string): string | null {
  return localStorage.getItem(`${API_TOKEN_SECRET_PREFIX}${tokenId}`)
}

export function removeApiTokenSecret(tokenId: string): void {
  localStorage.removeItem(`${API_TOKEN_SECRET_PREFIX}${tokenId}`)
}

export default http
