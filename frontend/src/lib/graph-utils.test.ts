import { describe, expect, it } from 'vitest'
import { containsLoopOrCycle, isPipelineExportable, exportDisabledReason } from './graph-utils'

const node = (id: string, type = 'loader') => ({ id, data: { type } })
const edge = (source: string, target: string) => ({ source, target })

describe('containsLoopOrCycle', () => {
  it('returns false for a simple DAG', () => {
    expect(containsLoopOrCycle(
      [node('A'), node('B'), node('C')],
      [edge('A', 'B'), edge('B', 'C')],
    )).toBe(false)
  })

  it('returns true for an explicit loop_controller', () => {
    expect(containsLoopOrCycle(
      [node('A'), node('L', 'loop_controller'), node('B')],
      [edge('A', 'L'), edge('L', 'B')],
    )).toBe(true)
  })

  it('returns true for a graph cycle without loop_controller', () => {
    expect(containsLoopOrCycle(
      [node('A'), node('B'), node('C')],
      [edge('A', 'B'), edge('B', 'C'), edge('C', 'A')],
    )).toBe(true)
  })

  it('returns false for an empty pipeline', () => {
    expect(containsLoopOrCycle([], [])).toBe(false)
  })

  it('returns false for disconnected nodes', () => {
    expect(containsLoopOrCycle(
      [node('A'), node('B')],
      [],
    )).toBe(false)
  })

  it('detects self-loop', () => {
    expect(containsLoopOrCycle(
      [node('A')],
      [edge('A', 'A')],
    )).toBe(true)
  })

  it('returns true for a diamond with back-edge', () => {
    expect(containsLoopOrCycle(
      [node('A'), node('B'), node('C'), node('D')],
      [edge('A', 'B'), edge('A', 'C'), edge('B', 'D'), edge('C', 'D'), edge('D', 'A')],
    )).toBe(true)
  })
})

describe('isPipelineExportable', () => {
  it('returns true for a simple DAG of normal blocks', () => {
    expect(isPipelineExportable(
      [node('A'), node('B')],
      [edge('A', 'B')],
    )).toBe(true)
  })

  it('returns false for loops', () => {
    expect(isPipelineExportable(
      [node('A'), node('L', 'loop_controller')],
      [edge('A', 'L')],
    )).toBe(false)
  })

  it('returns false for python_runner', () => {
    expect(isPipelineExportable(
      [node('A'), node('P', 'python_runner')],
      [edge('A', 'P')],
    )).toBe(false)
  })

  it('returns false for cycles', () => {
    expect(isPipelineExportable(
      [node('A'), node('B')],
      [edge('A', 'B'), edge('B', 'A')],
    )).toBe(false)
  })
})

describe('exportDisabledReason', () => {
  it('returns empty string for exportable pipeline', () => {
    expect(exportDisabledReason(
      [node('A'), node('B')],
      [edge('A', 'B')],
    )).toBe('')
  })

  it('returns loop reason for loop_controller', () => {
    const reason = exportDisabledReason(
      [node('A'), node('L', 'loop_controller')],
      [edge('A', 'L')],
    )
    expect(reason).toContain('loops')
  })

  it('returns custom code reason for python_runner', () => {
    const reason = exportDisabledReason(
      [node('A'), node('P', 'python_runner')],
      [edge('A', 'P')],
    )
    expect(reason).toContain('custom code')
  })
})
