import {
  resolveWizardChapterCount,
  resolveWordsPerChapter,
} from '@/lib/wordBudget'
import { useWizardStore } from '@/stores/wizardStore'

export function useWizardWordBudget() {
  const basicBookType = useWizardStore((s) => s.basicBookType)
  const basicPlatform = useWizardStore((s) => s.basicPlatform)
  const totalWords = useWizardStore((s) => s.totalWords)
  const shortChapterCount = useWizardStore((s) => s.shortChapterCount)
  const novelChapterCount = useWizardStore((s) => s.novelChapterCount)
  const wordsPerChapter = useWizardStore((s) => s.wordsPerChapter)
  const chapterCount = resolveWizardChapterCount(
    basicBookType,
    totalWords,
    novelChapterCount,
    basicPlatform,
    shortChapterCount,
  )
  const wordsPerChapterResolved = resolveWordsPerChapter(
    basicBookType,
    totalWords,
    chapterCount,
    wordsPerChapter,
  )
  return {
    basicBookType,
    basicPlatform,
    totalWords,
    shortChapterCount,
    novelChapterCount,
    wordsPerChapter,
    chapterCount,
    wordsPerChapterResolved,
  }
}
