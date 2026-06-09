import { useQuery } from '@tanstack/react-query'

import { fetchWorkQueue } from '@/api/endpoints'

export function useWorkQueue(enabled = true) {
  return useQuery({
    queryKey: ['flow', 'work-queue'],
    queryFn: fetchWorkQueue,
    enabled,
    refetchInterval: 30_000,
  })
}
