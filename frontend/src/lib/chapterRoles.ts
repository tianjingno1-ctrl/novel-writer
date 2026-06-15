/** 与 core/chapter_roles.py 对齐的章叙事角色（Track S2 UI） */

export const CHAPTER_ROLES = [
  'hook_open',
  'buildup',
  'escalation',
  'paywall',
  'paid_open',
  'climax',
  'bridge',
  'finale',
] as const

export type ChapterRole = (typeof CHAPTER_ROLES)[number]

export const CHAPTER_ROLE_LABELS: Record<ChapterRole, string> = {
  hook_open: '开篇钩子',
  buildup: '铺垫',
  escalation: '爆发',
  paywall: '付费切割',
  paid_open: '付费首章',
  climax: '高潮',
  bridge: '过渡',
  finale: '完结',
}

export type ChapterIntent = {
  kind?: string
  ai_suggest?: string
  final?: string | Record<string, unknown>
}

export type PlanChapterRow = {
  num?: number
  title?: string
  beat?: string
  hook?: string
  role?: string
  intent?: ChapterIntent
  word_count_target?: number | null
}

export type IntentFieldDef = {
  key: string
  label: string
  placeholder?: string
}

export const STRUCTURED_INTENT_FIELDS: Partial<
  Record<ChapterRole, IntentFieldDef[]>
> = {
  buildup: [
    { key: 'conditions', label: '条件载体', placeholder: '如：加班、被忽视' },
    {
      key: 'emotions',
      label: '情感叠加方向',
      placeholder: '如：带入自己+开始在乎这段关系',
    },
  ],
  escalation: [
    { key: 'debt', label: '情感债', placeholder: '一触即发的积累' },
    {
      key: 'trigger',
      label: '引爆载体（小而精准）',
      placeholder: '如：一句轻描淡写的否定',
    },
  ],
  climax: [
    { key: 'mechanism', label: '爽感机制', placeholder: '债务清算 / 能力展示 / 关系确认' },
    { key: 'contrast', label: '对比/反差', placeholder: '引爆前→引爆后局势逆转' },
    { key: 'peak_carrier', label: '峰值载体', placeholder: '静止感后的一句话/动作/细节' },
    { key: 'ripple', label: '爆发波（三圈连锁）', placeholder: '对手→旁观者→关系' },
    { key: 'ending_tone', label: '余韵基调', placeholder: '解气收尾 / 留悬念 / 情感升华' },
  ],
  bridge: [
    { key: 'bridge_subtype', label: '子类型', placeholder: '情绪缓冲型 / 铺垫蓄势型 / 关系沉淀型' },
    { key: 'entry_emotion', label: '进入情绪', placeholder: '读者刚经历 climax 后的余温' },
    { key: 'exit_emotion', label: '离开情绪', placeholder: '温热期待 / 轻微好奇' },
    { key: 'reset_method', label: '重置方式', placeholder: '对话 / 环境 / 内心独白' },
    { key: 'info_what', label: '信息补偿', placeholder: '补充什么、与下一 buildup 相关' },
    { key: 'micro_who', label: '变化主体', placeholder: '谁发生了变化' },
    { key: 'micro_what_changed', label: '可见变化', placeholder: '心态/关系/状态的微小变化' },
    { key: 'small_payoff_type', label: '小爽点', placeholder: '漂亮台词 / 小反转 / 路人反应' },
    { key: 'next_seed', label: '下一 buildup 种子', placeholder: '对齐下一章 conditions' },
    { key: 'next_seed_hook_type', label: '种子类型', placeholder: '新威胁 / 关系裂缝 / 隐藏信息' },
    { key: 'next_seed_intensity', label: '种子强度', placeholder: '低 / 中（不可高）' },
  ],
  finale: [
    { key: 'finale_subtype', label: '子类型', placeholder: '胜利落地型 / 和解沉淀型' },
    {
      key: 'opening_gap',
      label: '首尾缺口（core_task）',
      placeholder: '回扣第 1 章 hook_open',
    },
    { key: 'closing_payoff', label: '情感交割（core_task）', placeholder: '核心内心任务如何落地' },
    { key: 'entry_emotion', label: '进入情绪', placeholder: '读者进入 finale 时的状态' },
    { key: 'exit_emotion', label: '离开情绪', placeholder: '舍不得 / 值了 / 还在里面' },
    { key: 'landing_method', label: '落地方式', placeholder: '画面 / 对话 / 环境' },
    { key: 'freeze_who', label: '定格·人物', placeholder: '画面中有谁' },
    { key: 'freeze_what', label: '定格·画面', placeholder: '可截图的动作/话语/细节' },
    { key: 'open_ending_what', label: '余韵留白', placeholder: '留什么没有说完' },
    { key: 'reader_feeling', label: '读者感受', placeholder: '还想多待一会儿' },
  ],
}

/** 编辑态：嵌套 intent.final 展平为表单字段 */
export function flattenIntentFinalForEdit(
  _role: string | undefined,
  final: string | Record<string, unknown> | undefined,
): Record<string, string> {
  if (!final || typeof final === 'string') {
    return typeof final === 'string' && final ? { text: final } : {}
  }
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(final)) {
    if (k === 'core_task' && v && typeof v === 'object' && !Array.isArray(v)) {
      for (const [ck, cv] of Object.entries(v as Record<string, unknown>)) {
        out[ck] = typeof cv === 'string' ? cv : String(cv ?? '')
      }
      continue
    }
    if (k === 'emotional_arc' && v && typeof v === 'object' && !Array.isArray(v)) {
      for (const [ek, ev] of Object.entries(v as Record<string, unknown>)) {
        out[ek] = typeof ev === 'string' ? ev : String(ev ?? '')
      }
      continue
    }
    if (k === 'micro_change' && v && typeof v === 'object' && !Array.isArray(v)) {
      const mc = v as Record<string, unknown>
      if (mc.who) out.micro_who = String(mc.who)
      if (mc.what_changed) out.micro_what_changed = String(mc.what_changed)
      continue
    }
    if (k === 'info_payoff' && v && typeof v === 'object' && !Array.isArray(v)) {
      const ip = v as Record<string, unknown>
      if (ip.what) out.info_what = String(ip.what)
      continue
    }
    if (k === 'next_seed' && v && typeof v === 'object' && !Array.isArray(v)) {
      const ns = v as Record<string, unknown>
      if (ns.text) out.next_seed = String(ns.text)
      if (ns.hook_type) out.next_seed_hook_type = String(ns.hook_type)
      if (ns.intensity) out.next_seed_intensity = String(ns.intensity)
      continue
    }
    if (k === 'freeze_frame' && v && typeof v === 'object' && !Array.isArray(v)) {
      const ff = v as Record<string, unknown>
      if (ff.who) out.freeze_who = String(ff.who)
      if (ff.what) out.freeze_what = String(ff.what)
      continue
    }
    if (k === 'open_ending' && v && typeof v === 'object' && !Array.isArray(v)) {
      const oe = v as Record<string, unknown>
      if (oe.what_is_left_unsaid) out.open_ending_what = String(oe.what_is_left_unsaid)
      if (oe.reader_feeling) out.reader_feeling = String(oe.reader_feeling)
      continue
    }
    out[k] = typeof v === 'string' ? v : String(v ?? '')
  }
  return out
}

/** 提交态：扁平字段 → v1.0 嵌套 schema */
export function nestIntentFinalForApply(
  role: ChapterRole | undefined,
  flat: string | Record<string, unknown>,
): string | Record<string, unknown> {
  if (typeof flat === 'string') return flat
  if (role === 'bridge') {
    const out: Record<string, unknown> = {}
    for (const key of ['bridge_subtype', 'climax_type', 'decompression', 'compensation'] as const) {
      const val = String(flat[key] ?? '').trim()
      if (val) out[key] = val
    }
    const arc: Record<string, string> = {}
    for (const key of ['entry_emotion', 'exit_emotion', 'reset_method'] as const) {
      const val = String(flat[key] ?? '').trim()
      if (val) arc[key] = val
    }
    if (Object.keys(arc).length) out.emotional_arc = arc
    const infoWhat = String(flat.info_what ?? '').trim()
    if (infoWhat) out.info_payoff = { what: infoWhat, linked_to_next: true }
    const microWho = String(flat.micro_who ?? '').trim()
    const microChanged = String(flat.micro_what_changed ?? '').trim()
    if (microWho || microChanged) {
      out.micro_change = { who: microWho, what_changed: microChanged }
    }
    const sp = String(flat.small_payoff_type ?? '').trim()
    if (sp) out.small_payoff = { type: sp }
    const seed = String(flat.next_seed ?? '').trim()
    const seedHook = String(flat.next_seed_hook_type ?? '').trim()
    const seedIntensity = String(flat.next_seed_intensity ?? '').trim()
    if (seed || seedHook || seedIntensity) {
      out.next_seed = {
        text: seed,
        hook_type: seedHook,
        intensity: seedIntensity || '低',
      }
    }
    return out
  }
  if (role !== 'finale') return { ...flat }
  const opening = String(flat.opening_gap ?? '').trim()
  const closing = String(flat.closing_payoff ?? '').trim()
  const out: Record<string, unknown> = {}
  const subtype = String(flat.finale_subtype ?? '').trim()
  if (subtype) out.finale_subtype = subtype
  if (opening || closing) {
    out.core_task = { opening_gap: opening, closing_payoff: closing }
  }
  const arc: Record<string, string> = {}
  for (const key of ['entry_emotion', 'exit_emotion', 'landing_method'] as const) {
    const val = String(flat[key] ?? '').trim()
    if (val) arc[key] = val
  }
  if (Object.keys(arc).length) out.emotional_arc = arc
  const freezeWho = String(flat.freeze_who ?? '').trim()
  const freezeWhat = String(flat.freeze_what ?? '').trim()
  if (freezeWho || freezeWhat) {
    out.freeze_frame = { who: freezeWho, what: freezeWhat }
  }
  const openWhat = String(flat.open_ending_what ?? '').trim()
  const readerFeeling = String(flat.reader_feeling ?? '').trim()
  if (openWhat || readerFeeling) {
    out.open_ending = {
      what_is_left_unsaid: openWhat,
      reader_feeling: readerFeeling,
    }
  }
  return out
}

export function isChapterRole(value: string | undefined): value is ChapterRole {
  return CHAPTER_ROLES.includes(value as ChapterRole)
}

export function getStructuredIntentFields(
  role: string | undefined,
): IntentFieldDef[] | null {
  if (!role || !isChapterRole(role)) return null
  return STRUCTURED_INTENT_FIELDS[role] ?? null
}

export function emptyStructuredFinal(role: ChapterRole): Record<string, string> {
  const fields = STRUCTURED_INTENT_FIELDS[role]
  if (!fields) return {}
  return Object.fromEntries(fields.map((f) => [f.key, '']))
}

export function intentFinalText(ch: PlanChapterRow): string {
  const final = ch.intent?.final
  if (typeof final === 'string') return final
  if (final && typeof final === 'object' && Object.keys(final).length > 0) {
    try {
      return JSON.stringify(final, null, 2)
    } catch {
      return ''
    }
  }
  return ch.intent?.ai_suggest ?? ''
}

/** 写作页规划面板：结构化 intent 转可读文案 */
export function formatPlanIntentDisplay(plan: {
  role?: string
  intent?: ChapterIntent
}): string {
  const role = plan.role
  const fields = getStructuredIntentFields(role)
  const final = plan.intent?.final
  if (fields && final && typeof final === 'object' && !Array.isArray(final)) {
    return fields
      .map((f) => {
        const v = String((final as Record<string, string>)[f.key] ?? '').trim()
        return v ? `${f.label}：${v}` : ''
      })
      .filter(Boolean)
      .join('\n')
  }
  const text = intentFinalText({ role, intent: plan.intent })
  if (text.trim()) return text.trim()
  return plan.intent?.ai_suggest?.trim() ?? ''
}

/** 提交给 API 的 final：结构化 role 传 object，其余传 string */
export function intentFinalPayload(
  ch: PlanChapterRow,
): string | Record<string, unknown> {
  const final = ch.intent?.final
  if (typeof final === 'string') return final
  if (final && typeof final === 'object' && !Array.isArray(final)) {
    const role = isChapterRole(ch.role) ? ch.role : undefined
    return nestIntentFinalForApply(role, final as Record<string, unknown>)
  }
  return ch.intent?.ai_suggest ?? ''
}

export function intentFieldLabel(role: string | undefined): string {
  switch (role) {
    case 'hook_open':
      return '开篇配方（确认）'
    case 'paywall':
      return '付费前心理状态（确认）'
    case 'paid_open':
      return ''
    default:
      return getStructuredIntentFields(role) ? '叙事意图（结构化）' : '叙事意图（确认）'
  }
}

export function chapterForApply(ch: PlanChapterRow): Record<string, unknown> {
  const num = ch.num
  const role = isChapterRole(ch.role) ? ch.role : undefined
  const row: Record<string, unknown> = {
    num,
    title: ch.title,
    beat: ch.beat,
    hook: ch.hook,
  }
  if (role) {
    row.role = role
  }
  if (ch.word_count_target != null && ch.word_count_target > 0) {
    row.word_count_target = ch.word_count_target
  }
  if (role && role !== 'paid_open') {
    row.intent = {
      kind: role,
      ai_suggest: ch.intent?.ai_suggest ?? '',
      final: intentFinalPayload(ch),
    }
  }
  return row
}
