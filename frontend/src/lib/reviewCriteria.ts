import type { ResolvedCriterion } from '@/types/api'

export function criterionKey(
  c: ResolvedCriterion,
  prefix: string,
  index: number,
): string {
  return String(c.ref ?? c.id ?? `${prefix}-${index}`)
}

export function criterionLabel(c: ResolvedCriterion): string {
  const text =
    c.label ?? c.content ?? c.description ?? c.ref ?? c.id ?? '未命名规则'
  return String(text).trim() || '未命名规则'
}

/** 平台 / 全局规则；不含 custom_checks（由单独 textarea 编辑） */
export function profileHardRules(rules: ResolvedCriterion[] | undefined): ResolvedCriterion[] {
  return (rules ?? []).filter((c) => c.source !== 'custom' && !String(c.ref ?? '').startsWith('custom:'))
}
