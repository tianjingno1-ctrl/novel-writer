import { create } from 'zustand'

export type FlowIntent =
  | { kind: 'revise'; chapter: number; note?: string }
  | {
      kind: 'attribution'
      qualityLogId?: string
      diagnosisId?: string
    }

type BookState = {
  activeBookId: string | null
  writeChapterNum: number | null
  flowIntent: FlowIntent | null
  setActiveBookId: (id: string | null) => void
  setWriteChapterNum: (num: number | null) => void
  setFlowIntent: (intent: FlowIntent | null) => void
  consumeFlowIntent: () => FlowIntent | null
}

export const useBookStore = create<BookState>((set, get) => ({
  activeBookId: null,
  writeChapterNum: null,
  flowIntent: null,
  setActiveBookId: (id) => set({ activeBookId: id }),
  setWriteChapterNum: (num) => set({ writeChapterNum: num }),
  setFlowIntent: (intent) => set({ flowIntent: intent }),
  consumeFlowIntent: () => {
    const intent = get().flowIntent
    if (intent) {
      set({ flowIntent: null })
    }
    return intent
  },
}))
