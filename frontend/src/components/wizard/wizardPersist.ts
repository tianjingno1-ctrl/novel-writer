import type { WizardStep } from '@/stores/wizardStore'
import { updatePlanMeta } from '@/api/productApi'

export const WIZARD_STEP_ORDER: WizardStep[] = [
  'basic',
  'reference',
  'direction',
  'plan',
  'criteria',
]

const VALID_STEPS = WIZARD_STEP_ORDER

export function wizardStepIndex(step: WizardStep): number {
  return WIZARD_STEP_ORDER.indexOf(step)
}

export function prevWizardStep(step: WizardStep): WizardStep | null {
  const idx = wizardStepIndex(step)
  if (idx <= 0) return null
  return WIZARD_STEP_ORDER[idx - 1] ?? null
}

export function isWizardStep(value: string | null | undefined): value is WizardStep {
  return VALID_STEPS.includes(value as WizardStep)
}

export async function persistWizardStep(step: WizardStep) {
  await updatePlanMeta({ wizard_step: step }).catch(() => undefined)
}
