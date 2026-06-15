/** 章规划校验：后端 message 可能含 role 英文名，展示前转为人话 */

export type PlanValidationIssue = {
  code?: string
  severity?: string
  message?: string
  chapter_num?: number
}

export type PlanValidationResult = {
  ok: boolean
  errors?: PlanValidationIssue[]
  warnings?: PlanValidationIssue[]
  validation?: PlanValidationIssue[]
  error?: string
}

export type PlanSemanticValidationResult = {
  ok: boolean
  skipped?: boolean
  reason?: string
  warnings?: PlanValidationIssue[]
  overrides?: string[]
  pairs_checked?: number
  error?: string
}

/** 叙事角色内部名 → 界面已用的中文（与 chapterRoles.ts 一致） */
const ROLE_TERM: Record<string, string> = {
  hook_open: '开篇钩子',
  buildup: '铺垫',
  escalation: '爆发',
  paywall: '付费切割',
  paid_open: '付费首章',
  climax: '高潮',
  bridge: '过渡',
  finale: '完结',
}

const CODE_HINT: Record<string, string> = {
  paywall_count:
    '短篇需要恰好 1 章「付费切割」（读者在此付费），请在每章「叙事角色」里指定',
  paid_open_count:
    '短篇需要恰好 1 章「付费首章」（紧跟付费切割章的下一章）',
  paywall_position_edge:
    '「付费切割」不能放在第 1 章或最后一章，应放在中段让读者先免费读几章',
  paywall_position_range:
    '「付费切割」建议放在全书约 40%～55% 的位置（免费段与付费段比例）',
  paid_open_not_after_paywall:
    '「付费首章」必须是「付费切割」的下一章，中间不能插别的章',
  meta_paywall_mismatch: '系统记录的付费章号与规划不一致，请重新选「付费切割」章',
  bow_too_few_buildup:
    '付费切割前建议至少 2 章「铺垫」，让读者情绪逐步积累',
  bow_no_escalation: '付费切割前建议至少有 1 章「爆发」',
  bow_last_pre_not_escalation:
    '付费切割的前一章建议设为「爆发」，把情绪推到临界点',
  paywall_intent_empty:
    '请在「付费切割」章填写「付费前心理状态」（读者为什么愿意付钱）',
  paid_open_no_continuity:
    '「付费首章」开头要直接接住上一章结尾的悬念，别另起炉灶',
}

export function splitPlanValidation(issues: PlanValidationIssue[] | undefined) {
  const rows = issues ?? []
  return {
    errors: rows.filter((i) => i.severity === 'error'),
    warnings: rows.filter((i) => i.severity === 'warn'),
  }
}

/** 把后端英文 role / 字段名替换为中文，保留数字与章号 */
export function humanizePlanMessage(raw: string): string {
  let s = raw.trim()
  if (!s) return '校验项'

  for (const [en, zh] of Object.entries(ROLE_TERM)) {
    s = s.replaceAll(en, zh)
  }

  const replacements: [RegExp, string][] = [
    [/meta\.paywall_chapter/g, '规划的付费章号'],
    [/intent\.final/g, '叙事意图'],
    [/intent\.final\.debt/g, '情感债'],
    [/intent\.final\.trigger/g, '引爆点'],
    [/conditions\/emotions/g, '条件与情感方向'],
    [/conditions/g, '条件载体'],
    [/emotions/g, '情感方向'],
    [/next_seed/g, '下一章铺垫种子'],
    [/拉弓/g, '付费前节奏'],
    [/拉弓·压力梯度/g, '付费前情绪积累'],
    [/拉弓·临界点/g, '付费前爆发'],
    [/bridge（/g, '「过渡」章（'],
    [/buildup（/g, '「铺垫」章（'],
  ]
  for (const [re, sub] of replacements) {
    s = s.replace(re, sub)
  }
  return s
}

export function formatPlanIssueLine(issue: PlanValidationIssue): string {
  const ch =
    issue.chapter_num != null ? `第 ${issue.chapter_num} 章 · ` : ''
  const raw = issue.message?.trim()
  const body = raw
    ? humanizePlanMessage(raw)
    : CODE_HINT[issue.code ?? ''] ?? issue.code ?? '校验项'
  return `${ch}${body}`
}

/** 向导 StepPlan 顶部说明（短篇付费结构） */
export const SHORT_PAYWALL_HELP =
  '短篇番茄结构：全书中要有 1 章「付费切割」（读者在此付费）+ 紧接的 1 章「付费首章」。在下方每章选「叙事角色」即可，不必记英文名字。'
