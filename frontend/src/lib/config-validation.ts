/**
 * Frontend declarative cross-field config validation.
 * Mirrors backend/engine/config_rules.py — same operators, same logic.
 */

import type { ConfigValidationRule } from './block-registry-types'

export interface ValidationFailure {
  fields: string[]
  message: string
  severity: 'warning' | 'error'
}

type NumericOp = (values: number[], threshold: number) => boolean

const OPERATORS: Record<string, NumericOp> = {
  lte: (v, t) => v[0] <= t,
  gte: (v, t) => v[0] >= t,
  lt: (v, t) => v[0] < t,
  gt: (v, t) => v[0] > t,
  eq: (v, t) => v[0] === t,
  neq: (v, t) => v[0] !== t,
  product_lte: (v, t) => v.reduce((a, b) => a * b, 1) <= t,
  sum_lte: (v, t) => v.reduce((a, b) => a + b, 0) <= t,
}

function evaluateRule(rule: ConfigValidationRule, config: Record<string, any>): ValidationFailure | null {
  const { fields, op, message, severity } = rule

  // Handle required_if specially
  if (op === 'required_if') {
    const conditionField = rule.condition_field ?? ''
    const conditionValue = rule.condition_value
    if (config[conditionField] === conditionValue) {
      for (const field of fields) {
        const val = config[field]
        if (val === undefined || val === null || val === '' || val === false) {
          return { fields, message, severity }
        }
      }
    }
    return null
  }

  // Standard numeric operators
  const func = OPERATORS[op]
  if (!func) return null

  const values: number[] = []
  for (const field of fields) {
    const raw = config[field]
    if (raw === undefined || raw === null || raw === '') return null
    const num = Number(raw)
    if (isNaN(num)) return null
    values.push(num)
  }

  const threshold = Number(rule.value ?? 0)
  if (isNaN(threshold)) return null

  if (!func(values, threshold)) {
    return { fields, message, severity }
  }

  return null
}

/**
 * Evaluate all cross-field validation rules and return failures only.
 */
export function evaluateConfigRules(
  rules: ConfigValidationRule[] | undefined,
  config: Record<string, any>,
): ValidationFailure[] {
  if (!rules || rules.length === 0) return []

  const failures: ValidationFailure[] = []
  for (const rule of rules) {
    const failure = evaluateRule(rule, config)
    if (failure) failures.push(failure)
  }
  return failures
}

/**
 * Get validation failures for a specific field.
 */
export function getFieldValidationFailures(
  fieldName: string,
  failures: ValidationFailure[],
): ValidationFailure[] {
  return failures.filter(f => f.fields.includes(fieldName))
}
