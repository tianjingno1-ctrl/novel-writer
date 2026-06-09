const TOKEN_KEY = 'novel_web_token'

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, message: string, body?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? ''
}

export function setToken(token: string): void {
  if (token.trim()) {
    localStorage.setItem(TOKEN_KEY, token.trim())
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

function buildHeaders(init?: RequestInit): Headers {
  const headers = new Headers(init?.headers)
  if (init?.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getToken()
  if (token) {
    headers.set('X-Novel-Token', token)
  }
  return headers
}

async function parseError(res: Response): Promise<ApiError> {
  let detail = res.statusText
  let body: unknown
  try {
    body = await res.json()
    if (body && typeof body === 'object') {
      const record = body as Record<string, unknown>
      detail = String(record.detail ?? record.error ?? record.message ?? detail)
    }
  } catch {
    try {
      detail = await res.text()
    } catch {
      /* ignore */
    }
  }
  return new ApiError(res.status, detail, body)
}

/** JSON REST 请求；开发时走 Vite proxy → FastAPI :8765 */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: buildHeaders(init),
  })
  if (!res.ok) {
    throw await parseError(res)
  }
  return (await res.json()) as T
}

export async function apiVoid(path: string, init?: RequestInit): Promise<void> {
  const res = await fetch(path, {
    ...init,
    headers: buildHeaders(init),
  })
  if (!res.ok) {
    throw await parseError(res)
  }
}
