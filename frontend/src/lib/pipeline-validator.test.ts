import { describe, expect, it } from 'vitest'
import { validatePipelineClient } from './pipeline-validator'

describe('pipeline validator', () => {
  it('flags empty pipelines as invalid', () => {
    const report = validatePipelineClient([], [])

    expect(report.valid).toBe(false)
    expect(report.errors.some((e) => e.category === 'structure')).toBe(true)
  })

  it('marks disconnected nodes as warning', () => {
    const nodes: any[] = [
      { id: 'n1', type: 'blockNode', data: { type: 'llm_inference', label: 'A', config: {} }, position: { x: 0, y: 0 } },
      { id: 'n2', type: 'blockNode', data: { type: 'llm_inference', label: 'B', config: {} }, position: { x: 10, y: 10 } },
    ]

    const report = validatePipelineClient(nodes, [])

    expect(report.warnings.length).toBeGreaterThan(0)
  })
})
