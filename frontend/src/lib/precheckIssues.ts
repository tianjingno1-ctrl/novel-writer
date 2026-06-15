import type { PrecheckIssue, PrecheckResult } from '@/api/chapterFlow'

const PRECHECK_CODE_LABELS: Record<string, string> = {
  word_count_low: '字数不足',
  word_count_high: '字数偏多',
  word_count_too_short: '正文过短',
  outline_keywords_missing: '大纲关键词',
  hook_open_lead_weak: '开篇钩子',
  escalation_intent_empty: '爆发意图',
  escalation_debt_weak: '情感债对齐',
  escalation_trigger_weak: '引爆对齐',
  escalation_trigger_too_big: '引爆过大',
  buildup_emotion_words: '铺垫情绪词',
  bridge_no_hook: '过渡悬念',
  finale_opening_gap_weak: '首尾呼应',
  paywall_no_suspense_hook: '付费切割章结尾缺悬念',
  paywall_intent_empty: '付费切割章须填付费前心理状态',
  paid_open_empty: '付费首章正文过短',
  paid_open_no_continuity: '付费首章未承接上一章悬念',
  ai_tone_high: 'AI 腔',
}

export function precheckIssueLabel(issue: PrecheckIssue): string {
  const code = issue.code ?? ''
  return PRECHECK_CODE_LABELS[code] ?? (code || '预检')
}

export const PAYWALL_INTENT_EMPTY_CODE = 'paywall_intent_empty'

export function canSkipPaywallIntentPrecheck(
  result: PrecheckResult | null | undefined,
): boolean {
  const { hard } = splitPrecheckIssues(result)
  return hard.some((i) => i.code === PAYWALL_INTENT_EMPTY_CODE)
}

export function splitPrecheckIssues(result: PrecheckResult | null | undefined) {
  const issues = result?.issues ?? []
  return {
    hard: issues.filter((i) => i.severity === 'hard'),
    soft: issues.filter((i) => i.severity === 'soft'),
  }
}

export const PRECHECK_WORD_MIN_RATIO = 0.85
export const PRECHECK_WORD_MAX_RATIO = 1.25

export function countChapterChars(text: string): number {
  return text.replace(/\s/g, '').length
}

export function wordCountBounds(
  target: number,
  minRatio = PRECHECK_WORD_MIN_RATIO,
  maxRatio = PRECHECK_WORD_MAX_RATIO,
): { low: number; high: number } {
  return {
    low: Math.floor(target * minRatio),
    high: Math.floor(target * maxRatio),
  }
}

/** 与 core/chapter_precheck.py 字数 hard/soft 区间一致 */
export function evaluateWordCount(
  count: number,
  target: number | null | undefined,
  minRatio = PRECHECK_WORD_MIN_RATIO,
  maxRatio = PRECHECK_WORD_MAX_RATIO,
): { ok: boolean; label: string; detail?: string } {
  if (!target || target <= 0) {
    if (count > 0 && count < 200) {
      return { ok: false, label: '✗ 正文过短', detail: '至少约 200 字' }
    }
    return { ok: true, label: '' }
  }
  const { low, high } = wordCountBounds(target, minRatio, maxRatio)
  if (count < low) {
    return {
      ok: false,
      label: '✗ 字数不足',
      detail: `目标 ${target}，至少 ${low}`,
    }
  }
  if (count > high) {
    return {
      ok: false,
      label: '✗ 字数偏多',
      detail: `目标 ${target}，建议 ≤ ${high}`,
    }
  }
  return { ok: true, label: '✓ 字数达标', detail: `目标约 ${target}` }
}

export function precheckFailMessage(result: PrecheckResult): string {
  const { hard } = splitPrecheckIssues(result)
  if (hard.length === 0) {
    return result.error ?? '预检未通过'
  }
  if (hard.length === 1) {
    return hard[0]?.message ?? '预检未通过'
  }
  return `有 ${hard.length} 项未通过（见下方列表）`
}
