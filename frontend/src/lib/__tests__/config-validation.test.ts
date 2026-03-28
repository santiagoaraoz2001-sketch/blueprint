/**
 * Tests for the frontend declarative config validation engine.
 * Mirrors the backend config_rules.py tests to ensure parity.
 */

import { describe, it, expect } from 'vitest'
import { evaluateConfigRules, getFieldValidationFailures, type ValidationFailure } from '../config-validation'
import type { ConfigValidationRule } from '../block-registry-types'

// ── Numeric operators ────────────────────────────────────────

describe('numeric operators', () => {
  it('lte passes when value <= threshold', () => {
    const rules: ConfigValidationRule[] = [
      { fields: ['batch_size'], op: 'lte', value: 32, message: 'Too big', severity: 'warning' },
    ]
    expect(evaluateConfigRules(rules, { batch_size: 16 })).toEqual([])
  })

  it('lte fails when value > threshold', () => {
    const rules: ConfigValidationRule[] = [
      { fields: ['batch_size'], op: 'lte', value: 32, message: 'Too big', severity: 'warning' },
    ]
    const failures = evaluateConfigRules(rules, { batch_size: 64 })
    expect(failures).toHaveLength(1)
    expect(failures[0].message).toBe('Too big')
  })

  it('gte passes', () => {
    const rules: ConfigValidationRule[] = [
      { fields: ['alpha'], op: 'gte', value: 1, message: 'Too small', severity: 'error' },
    ]
    expect(evaluateConfigRules(rules, { alpha: 16 })).toEqual([])
  })

  it('gte fails', () => {
    const rules: ConfigValidationRule[] = [
      { fields: ['alpha'], op: 'gte', value: 1, message: 'Too small', severity: 'error' },
    ]
    const failures = evaluateConfigRules(rules, { alpha: 0 })
    expect(failures).toHaveLength(1)
    expect(failures[0].severity).toBe('error')
  })

  it('lt and gt', () => {
    const rules: ConfigValidationRule[] = [
      { fields: ['lr'], op: 'lt', value: 0.01, message: 'LR too high', severity: 'warning' },
      { fields: ['epochs'], op: 'gt', value: 0, message: 'Need epochs', severity: 'error' },
    ]
    expect(evaluateConfigRules(rules, { lr: 0.001, epochs: 3 })).toEqual([])
    expect(evaluateConfigRules(rules, { lr: 0.01, epochs: 0 })).toHaveLength(2)
  })

  it('eq and neq', () => {
    const eq: ConfigValidationRule[] = [
      { fields: ['r'], op: 'eq', value: 16, message: 'Must be 16', severity: 'warning' },
    ]
    expect(evaluateConfigRules(eq, { r: 16 })).toEqual([])
    expect(evaluateConfigRules(eq, { r: 8 })).toHaveLength(1)

    const neq: ConfigValidationRule[] = [
      { fields: ['dropout'], op: 'neq', value: 0, message: 'Use dropout', severity: 'warning' },
    ]
    expect(evaluateConfigRules(neq, { dropout: 0.1 })).toEqual([])
    expect(evaluateConfigRules(neq, { dropout: 0 })).toHaveLength(1)
  })
})

// ── Multi-field operators ────────────────────────────────────

describe('multi-field operators', () => {
  it('product_lte passes when product <= threshold', () => {
    const rules: ConfigValidationRule[] = [
      { fields: ['batch_size', 'grad_accum'], op: 'product_lte', value: 32, message: 'Too big', severity: 'warning' },
    ]
    expect(evaluateConfigRules(rules, { batch_size: 4, grad_accum: 8 })).toEqual([])
  })

  it('product_lte fails when product > threshold', () => {
    const rules: ConfigValidationRule[] = [
      { fields: ['batch_size', 'grad_accum'], op: 'product_lte', value: 32, message: 'Too big', severity: 'warning' },
    ]
    const failures = evaluateConfigRules(rules, { batch_size: 8, grad_accum: 8 })
    expect(failures).toHaveLength(1)
  })

  it('sum_lte works correctly', () => {
    const rules: ConfigValidationRule[] = [
      { fields: ['train', 'eval'], op: 'sum_lte', value: 1.0, message: 'Over 100%', severity: 'error' },
    ]
    expect(evaluateConfigRules(rules, { train: 0.8, eval: 0.2 })).toEqual([])
    expect(evaluateConfigRules(rules, { train: 0.8, eval: 0.3 })).toHaveLength(1)
  })
})

// ── required_if ──────────────────────────────────────────────

describe('required_if operator', () => {
  const rules: ConfigValidationRule[] = [
    {
      fields: ['gradient_checkpointing'],
      op: 'required_if',
      condition_field: 'use_lora',
      condition_value: true,
      message: 'Required when use_lora is enabled',
      severity: 'error',
    },
  ]

  it('passes when condition met and field present', () => {
    expect(evaluateConfigRules(rules, { use_lora: true, gradient_checkpointing: true })).toEqual([])
  })

  it('fails when condition met and field missing', () => {
    const failures = evaluateConfigRules(rules, { use_lora: true })
    expect(failures).toHaveLength(1)
    expect(failures[0].severity).toBe('error')
  })

  it('passes when condition not met', () => {
    expect(evaluateConfigRules(rules, { use_lora: false })).toEqual([])
  })
})

// ── Edge cases ───────────────────────────────────────────────

describe('edge cases', () => {
  it('missing field skips validation', () => {
    const rules: ConfigValidationRule[] = [
      { fields: ['batch_size'], op: 'lte', value: 32, message: 'Too big', severity: 'warning' },
    ]
    expect(evaluateConfigRules(rules, {})).toEqual([])
  })

  it('empty string field skips', () => {
    const rules: ConfigValidationRule[] = [
      { fields: ['batch_size'], op: 'lte', value: 32, message: 'Too big', severity: 'warning' },
    ]
    expect(evaluateConfigRules(rules, { batch_size: '' })).toEqual([])
  })

  it('non-numeric field skips', () => {
    const rules: ConfigValidationRule[] = [
      { fields: ['model_name'], op: 'lte', value: 100, message: 'Bad', severity: 'warning' },
    ]
    expect(evaluateConfigRules(rules, { model_name: 'llama-3' })).toEqual([])
  })

  it('unknown operator skips', () => {
    const rules: ConfigValidationRule[] = [
      { fields: ['x'], op: 'bogus_op' as any, value: 1, message: 'Unknown', severity: 'warning' },
    ]
    expect(evaluateConfigRules(rules, { x: 5 })).toEqual([])
  })

  it('undefined/empty rules returns empty', () => {
    expect(evaluateConfigRules(undefined, { x: 1 })).toEqual([])
    expect(evaluateConfigRules([], { x: 1 })).toEqual([])
  })
})

// ── getFieldValidationFailures ───────────────────────────────

describe('getFieldValidationFailures', () => {
  it('filters failures for a specific field', () => {
    const failures: ValidationFailure[] = [
      { fields: ['batch_size', 'grad_accum'], message: 'Product too big', severity: 'warning' },
      { fields: ['lr'], message: 'LR too high', severity: 'warning' },
    ]
    expect(getFieldValidationFailures('batch_size', failures)).toHaveLength(1)
    expect(getFieldValidationFailures('lr', failures)).toHaveLength(1)
    expect(getFieldValidationFailures('epochs', failures)).toHaveLength(0)
    // grad_accum is also in the first failure
    expect(getFieldValidationFailures('grad_accum', failures)).toHaveLength(1)
  })
})
