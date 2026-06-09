import { useMutation } from '@tanstack/react-query'

import { api } from '@/api/client'
import { runFlow } from '@/api/endpoints'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useGateStore } from '@/stores/gateStore'

/**
 * 人工门：无 /api/flow/gate/{id}/adopt。
 * 展示 flow run 返回的 next_manual，引导调用对应单步 API。
 */
export function ManualGatePanel() {
  const pending = useGateStore((s) => s.pending)
  const clear = useGateStore((s) => s.clear)
  const step = useGateStore((s) => s.manualStep())

  const continueFlow = useMutation({
    mutationFn: () =>
      runFlow({
        mode: 'continue',
        chapter_num: pending?.chapter_num ?? undefined,
      }),
    onSuccess: (result) => {
      useGateStore.getState().setFromFlowRun(result)
      if (result.ok && result.stop_reason !== 'human_gate') {
        clear()
      }
    },
  })

  const callManual = useMutation({
    mutationFn: async () => {
      if (!step) {
        throw new Error('无待处理步骤')
      }
      const method = (step.method || 'POST').toUpperCase()
      return api<Record<string, unknown>>(step.path, {
        method,
        body: method === 'GET' ? undefined : JSON.stringify({}),
      })
    },
    onSuccess: () => {
      clear()
    },
  })

  if (!pending || !step) {
    return null
  }

  return (
    <Card className="border-primary/40 bg-primary/5">
      <CardHeader>
        <CardTitle>人工确认 · {step.label}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted">
          聚合流程已暂停（{pending.stop_reason}）。请调用单步 API，勿使用不存在的
          gate/adopt 路由。
        </p>
        <div className="rounded-md bg-card p-3 font-mono text-xs">
          <div>
            {step.method} {step.path}
          </div>
          {step.note ? <div className="mt-1 text-muted">{step.note}</div> : null}
        </div>
        {pending.manual_apis_note ? (
          <p className="text-xs text-muted">{pending.manual_apis_note}</p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            onClick={() => callManual.mutate()}
            disabled={callManual.isPending}
          >
            调用单步 API
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => continueFlow.mutate()}
            disabled={continueFlow.isPending}
          >
            继续 flow (continue)
          </Button>
          <Button size="sm" variant="ghost" onClick={clear}>
            忽略
          </Button>
        </div>
        {callManual.error ? (
          <p className="text-xs text-red-600">
            {(callManual.error as Error).message}
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}
