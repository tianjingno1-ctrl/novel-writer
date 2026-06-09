import { create } from 'zustand'

export type WizardStep = 'reference' | 'direction' | 'plan' | 'criteria'

export type DirectionOption = {
  id?: string
  logline?: string
  sell_point?: string
  tone?: string
  hook?: string
  title?: string
  chapter_count?: number
  [key: string]: unknown
}

export type PlanChapter = {
  num?: number
  title?: string
  beat?: string
  hook?: string
  [key: string]: unknown
}

type WizardState = {
  step: WizardStep
  referenceExcerpt: string
  seed: string
  chapterCount: number
  directionOptions: DirectionOption[]
  selectedDirection: DirectionOption | null
  directionLogId: string | null
  planTitle: string
  planChapters: PlanChapter[]
  planLogId: string | null
  deconstructLogId: string | null
  deconstructSummary: string
  setStep: (step: WizardStep) => void
  setReference: (text: string) => void
  setSeed: (text: string) => void
  setChapterCount: (n: number) => void
  setDirectionOptions: (opts: DirectionOption[], logId?: string | null) => void
  selectDirection: (opt: DirectionOption) => void
  setPlan: (title: string, chapters: PlanChapter[], logId?: string | null) => void
  setDeconstruct: (summary: string, logId?: string | null) => void
  reset: () => void
}

const initial = {
  step: 'reference' as WizardStep,
  referenceExcerpt: '',
  seed: '',
  chapterCount: 20,
  directionOptions: [] as DirectionOption[],
  selectedDirection: null as DirectionOption | null,
  directionLogId: null as string | null,
  planTitle: '',
  planChapters: [] as PlanChapter[],
  planLogId: null as string | null,
  deconstructLogId: null as string | null,
  deconstructSummary: '',
}

export const useWizardStore = create<WizardState>((set) => ({
  ...initial,
  setStep: (step) => set({ step }),
  setReference: (text) => set({ referenceExcerpt: text }),
  setSeed: (text) => set({ seed: text }),
  setChapterCount: (n) => set({ chapterCount: n }),
  setDirectionOptions: (opts, logId = null) =>
    set({ directionOptions: opts, directionLogId: logId }),
  selectDirection: (opt) => set({ selectedDirection: opt }),
  setPlan: (title, chapters, logId = null) =>
    set({ planTitle: title, planChapters: chapters, planLogId: logId }),
  setDeconstruct: (summary, logId = null) =>
    set({ deconstructSummary: summary, deconstructLogId: logId }),
  reset: () => set(initial),
}))
