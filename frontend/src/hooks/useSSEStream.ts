import { useCallback, useRef, useState } from 'react'

import { ApiError, getToken } from '@/api/client'
import type { SSEEvent } from '@/types/api'

function parseSSELine(line: string): SSEEvent | null {
  const trimmed = line.trim()
  if (!trimmed.startsWith('data:')) {
    return null
  }
  const payload = trimmed.slice(5).trim()
  if (!payload) {
    return null
  }
  try {
    const data = JSON.parse(payload) as SSEEvent
    if (data && typeof data === 'object' && 'type' in data) {
      return data
    }
  } catch {
    return null
  }
  return null
}

export type SSEStreamState = {
  streaming: boolean
  text: string
  error: string | null
  lastEvent: SSEEvent | null
}

export function useSSEStream() {
  const abortRef = useRef<AbortController | null>(null)
  const [state, setState] = useState<SSEStreamState>({
    streaming: false,
    text: '',
    error: null,
    lastEvent: null,
  })

  const stop = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setState((s) => ({ ...s, streaming: false }))
  }, [])

  const start = useCallback(
    async (url: string, body: unknown, onEvent?: (ev: SSEEvent) => void) => {
      stop()
      const controller = new AbortController()
      abortRef.current = controller

      setState({ streaming: true, text: '', error: null, lastEvent: null })

      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      }
      const token = getToken()
      if (token) {
        headers['X-Novel-Token'] = token
      }

      try {
        const res = await fetch(url, {
          method: 'POST',
          headers,
          body: JSON.stringify(body),
          signal: controller.signal,
        })

        if (!res.ok) {
          let detail = res.statusText
          try {
            const j = (await res.json()) as Record<string, unknown>
            detail = String(j.detail ?? j.error ?? detail)
          } catch {
            /* ignore */
          }
          throw new ApiError(res.status, detail)
        }

        const reader = res.body?.getReader()
        if (!reader) {
          throw new Error('响应无 body')
        }

        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) {
            break
          }
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''

          for (const line of lines) {
            const event = parseSSELine(line)
            if (!event) {
              continue
            }
            onEvent?.(event)
            setState((s) => {
              if (event.type === 'chunk') {
                return {
                  ...s,
                  text: s.text + event.text,
                  lastEvent: event,
                }
              }
              if (event.type === 'error') {
                return {
                  ...s,
                  error: event.message,
                  lastEvent: event,
                  streaming: false,
                }
              }
              return { ...s, lastEvent: event, streaming: false }
            })
            if (event.type === 'error') {
              return
            }
          }
        }
      } catch (err) {
        if (controller.signal.aborted) {
          return
        }
        const message =
          err instanceof Error ? err.message : '流式请求失败'
        setState((s) => ({
          ...s,
          error: message,
          streaming: false,
        }))
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null
        }
        setState((s) => ({ ...s, streaming: false }))
      }
    },
    [stop],
  )

  const reset = useCallback(() => {
    setState({ streaming: false, text: '', error: null, lastEvent: null })
  }, [])

  return { ...state, start, stop, reset }
}
