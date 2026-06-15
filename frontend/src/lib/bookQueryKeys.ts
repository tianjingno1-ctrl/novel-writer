import type { QueryClient } from '@tanstack/react-query'

import { fetchStatus } from '@/api/endpoints'
import { fetchPlanProduct } from '@/api/productApi'

export function planProductQueryKey(bookId?: string | null) {
  return ['plan', 'product', bookId ?? ''] as const
}

export function chapterQueryKey(bookId: string | null | undefined, num: number) {
  return ['chapter', bookId ?? '', num] as const
}

export function chaptersListQueryKey(bookId?: string | null) {
  return ['chapters', bookId ?? ''] as const
}

export function chatHistoryQueryKey(bookId?: string | null) {
  return ['chat', 'history', bookId ?? ''] as const
}

/** 切书后清掉上一本书的缓存，再拉当前书的 plan（依赖服务端 active book）。 */
export async function refreshAfterBookSwitch(qc: QueryClient) {
  qc.removeQueries({ queryKey: ['plan'] })
  qc.removeQueries({ queryKey: ['chapters'] })
  qc.removeQueries({ queryKey: ['chapter'] })
  qc.removeQueries({ queryKey: ['chat'] })
  const status = await qc.fetchQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
  })
  const bookId = status?.book_id ?? ''
  const plan = await qc.fetchQuery({
    queryKey: planProductQueryKey(bookId),
    queryFn: fetchPlanProduct,
  })
  return { bookId, plan, status }
}
