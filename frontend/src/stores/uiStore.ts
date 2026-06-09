import { create } from 'zustand'

/** flow = 心流沉浸；gate = 决策弹层；default = 常规页 */
export type ShellMode = 'default' | 'flow' | 'gate'

type UiState = {
  shellMode: ShellMode
  setShellMode: (mode: ShellMode) => void
}

export const useUiStore = create<UiState>((set) => ({
  shellMode: 'default',
  setShellMode: (mode) => set({ shellMode: mode }),
}))
