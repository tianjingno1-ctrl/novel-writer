import type { BookFormatId } from '@/lib/bookMeta'
import type { PlanChapterRow } from '@/lib/chapterRoles'

/** 与 library/profiles 中「章均 2000~3000」对齐的平台默认章均字数 */
const PLATFORM_WORDS_PER_CHAPTER: Record<string, number> = {
  tomato: 2500,
  midu: 2500,
  qimao: 2500,
  short_drama: 2000,
  other: 2500,
}

export const DEFAULT_SHORT_TOTAL_WORDS = 10_000
export const DEFAULT_NOVEL_CHAPTER_COUNT = 20
export const DEFAULT_WORDS_PER_CHAPTER = 2500

export const SHORT_CHAPTER_MIN = 3
export const SHORT_CHAPTER_MAX = 10

export function clampShortChapterCount(n: number): number {
  return Math.min(
    SHORT_CHAPTER_MAX,
    Math.max(SHORT_CHAPTER_MIN, Math.round(n)),
  )
}

export function platformDefaultWordsPerChapter(platform: string): number {
  return PLATFORM_WORDS_PER_CHAPTER[platform] ?? DEFAULT_WORDS_PER_CHAPTER
}

/** 短篇默认章数（与 DEFAULT_SHORT_TOTAL_WORDS + 番茄章均一致） */
export const DEFAULT_SHORT_CHAPTER_COUNT = clampShortChapterCount(
  Math.round(
    DEFAULT_SHORT_TOTAL_WORDS / platformDefaultWordsPerChapter('tomato'),
  ),
)

export function platformWordsHint(platform: string): string {
  const w = platformDefaultWordsPerChapter(platform)
  if (platform === 'tomato' || platform === 'midu' || platform === 'qimao') {
    return `平台建议章均约 2000~3000 字（默认 ${w}）`
  }
  return `默认章均约 ${w} 字`
}

/** 短篇：总字数 ÷ 平台章均估算，限制 3~10 章（满足 paywall 结构下限） */
export function deriveShortChapterCount(
  totalWords: number,
  platform: string,
): number {
  const slice = platformDefaultWordsPerChapter(platform)
  const raw = Math.round(totalWords / Math.max(slice, 500))
  return Math.min(SHORT_CHAPTER_MAX, Math.max(SHORT_CHAPTER_MIN, raw))
}

export function shortWordsPerChapter(totalWords: number, chapterCount: number): number {
  const n = Math.max(1, chapterCount)
  return Math.max(500, Math.round(totalWords / n))
}

export function resolveWizardChapterCount(
  bookType: BookFormatId,
  totalWords: number,
  novelChapterCount: number,
  platform: string,
  shortChapterCount?: number,
): number {
  if (bookType === 'short') {
    if (shortChapterCount != null && shortChapterCount > 0) {
      return clampShortChapterCount(shortChapterCount)
    }
    return deriveShortChapterCount(totalWords, platform)
  }
  return Math.max(1, Math.min(200, novelChapterCount))
}

export function resolveWordsPerChapter(
  bookType: BookFormatId,
  totalWords: number,
  chapterCount: number,
  wordsPerChapter: number,
): number {
  if (bookType === 'short') {
    return shortWordsPerChapter(totalWords, chapterCount)
  }
  return Math.max(500, wordsPerChapter)
}

export function applyBookTypeWordDefaults(
  bookType: BookFormatId,
  platform: string,
): {
  totalWords: number
  novelChapterCount: number
  wordsPerChapter: number
  shortChapterCount: number
} {
  const wordsPerChapter = platformDefaultWordsPerChapter(platform)
  if (bookType === 'short') {
    return {
      totalWords: DEFAULT_SHORT_TOTAL_WORDS,
      novelChapterCount: DEFAULT_NOVEL_CHAPTER_COUNT,
      wordsPerChapter,
      shortChapterCount: deriveShortChapterCount(
        DEFAULT_SHORT_TOTAL_WORDS,
        platform,
      ),
    }
  }
  return {
    totalWords: DEFAULT_SHORT_TOTAL_WORDS,
    novelChapterCount: DEFAULT_NOVEL_CHAPTER_COUNT,
    wordsPerChapter,
    shortChapterCount: DEFAULT_SHORT_CHAPTER_COUNT,
  }
}

export function stampChapterWordTargets(
  chapters: PlanChapterRow[],
  defaultWpc: number,
): PlanChapterRow[] {
  return chapters.map((ch) => ({
    ...ch,
    word_count_target:
      ch.word_count_target != null && ch.word_count_target > 0
        ? ch.word_count_target
        : defaultWpc,
  }))
}
