import { create } from 'zustand'

type BookState = {
  activeBookId: string | null
  writeChapterNum: number | null
  setActiveBookId: (id: string | null) => void
  setWriteChapterNum: (num: number | null) => void
}

export const useBookStore = create<BookState>((set) => ({
  activeBookId: null,
  writeChapterNum: null,
  setActiveBookId: (id) => set({ activeBookId: id }),
  setWriteChapterNum: (num) => set({ writeChapterNum: num }),
}))
