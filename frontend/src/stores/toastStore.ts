import { create } from 'zustand'

export type ToastKind = 'success' | 'warning' | 'info'

export type ToastItem = {
  id: string
  kind: ToastKind
  message: string
}

type ToastState = {
  toasts: ToastItem[]
  push: (kind: ToastKind, message: string) => void
  dismiss: (id: string) => void
}

let seq = 0

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (kind, message) => {
    const id = `toast-${++seq}`
    set((s) => ({ toasts: [...s.toasts, { id, kind, message }] }))
    window.setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
    }, 4000)
  },
  dismiss: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))

export function toast(kind: ToastKind, message: string) {
  useToastStore.getState().push(kind, message)
}
