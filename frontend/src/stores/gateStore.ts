import { create } from 'zustand'

import type { FlowManualStep, FlowRunResponse } from '@/types/api'

type GateState = {
  pending: FlowRunResponse | null
  setFromFlowRun: (result: FlowRunResponse) => void
  clear: () => void
  manualStep: () => FlowManualStep | null
}

export const useGateStore = create<GateState>((set, get) => ({
  pending: null,
  setFromFlowRun: (result) => {
    if (result.stop_reason === 'human_gate' && result.next_manual) {
      set({ pending: result })
      return
    }
    set({ pending: null })
  },
  clear: () => set({ pending: null }),
  manualStep: () => get().pending?.next_manual ?? null,
}))
