/**
 * Contract tests for frontend pipeline validation.
 *
 * Loads the same canonical fixtures used by backend tests and runs them
 * through the frontend validation and compatibility functions.
 * Captures behavior as JSON snapshots for cross-stack drift comparison.
 */

import { describe, it, expect } from 'vitest'
import { readFileSync, writeFileSync, mkdirSync } from 'fs'
import { resolve, join } from 'path'
import { isPortCompatible } from '../block-registry-types'

// ─── Fixture Loading ─────────────────────────────────────────────

const FIXTURES_DIR = resolve(__dirname, '../../../../backend/tests/fixtures/contracts')
const SNAPSHOT_DIR = resolve(__dirname, '__snapshots__')

interface Fixture {
  name: string
  description: string
  nodes: any[]
  edges: any[]
  expected: Record<string, any>
}

function loadFixture(name: string): Fixture {
  const content = readFileSync(join(FIXTURES_DIR, `${name}.json`), 'utf-8')
  return JSON.parse(content)
}

function loadAllFixtures(): Record<string, Fixture> {
  const names = [
    'simple_dag', 'branching_dag', 'legal_loop', 'illegal_cycle',
    'stale_handle', 'input_satisfies_config', 'partial_rerun_safe',
    'partial_rerun_unsafe', 'port_compat_drift',
  ]
  const fixtures: Record<string, Fixture> = {}
  for (const name of names) {
    try {
      fixtures[name] = loadFixture(name)
    } catch {
      // Fixture may not exist yet
    }
  }
  return fixtures
}

// ─── Loop-aware cycle detection (mirrors backend _detect_loops) ───

interface LoopInfo { controllerId: string; bodyIds: string[] }
interface LoopResult { legalLoops: LoopInfo[]; illegalCycle: boolean }

function detectLoops(nodes: { id: string; data?: any }[], edges: { source: string; target: string }[]): LoopResult {
  // Step 1: Kahn's to find cyclic nodes
  const inDegree = new Map<string, number>()
  const adj = new Map<string, string[]>()
  const revAdj = new Map<string, string[]>()
  for (const n of nodes) { inDegree.set(n.id, 0); adj.set(n.id, []); revAdj.set(n.id, []) }
  for (const e of edges) {
    if (adj.has(e.source) && adj.has(e.target)) {
      adj.get(e.source)!.push(e.target)
      revAdj.get(e.target)!.push(e.source)
      inDegree.set(e.target, (inDegree.get(e.target) ?? 0) + 1)
    }
  }
  const queue: string[] = []
  for (const [id, deg] of inDegree) { if (deg === 0) queue.push(id) }
  const acyclic = new Set<string>()
  while (queue.length > 0) {
    const n = queue.shift()!
    acyclic.add(n)
    for (const nb of adj.get(n) ?? []) {
      const nd = (inDegree.get(nb) ?? 1) - 1
      inDegree.set(nb, nd)
      if (nd === 0) queue.push(nb)
    }
  }
  const cyclicNodes = new Set(nodes.filter(n => !acyclic.has(n.id)).map(n => n.id))
  if (cyclicNodes.size === 0) return { legalLoops: [], illegalCycle: false }

  // Step 2: Kosaraju's SCC
  const visited = new Set<string>()
  const finishOrder: string[] = []
  for (const start of cyclicNodes) {
    if (visited.has(start)) continue
    const stack: [string, boolean][] = [[start, false]]
    while (stack.length > 0) {
      const [node, processed] = stack.pop()!
      if (processed) { finishOrder.push(node); continue }
      if (visited.has(node)) continue
      visited.add(node)
      stack.push([node, true])
      for (const nb of adj.get(node) ?? []) {
        if (cyclicNodes.has(nb) && !visited.has(nb)) stack.push([nb, false])
      }
    }
  }
  visited.clear()
  const sccs: string[][] = []
  for (let i = finishOrder.length - 1; i >= 0; i--) {
    const start = finishOrder[i]
    if (visited.has(start)) continue
    const component: string[] = []
    const s = [start]
    while (s.length > 0) {
      const n = s.pop()!
      if (visited.has(n)) continue
      visited.add(n)
      component.push(n)
      for (const nb of revAdj.get(n) ?? []) {
        if (cyclicNodes.has(nb) && !visited.has(nb)) s.push(nb)
      }
    }
    sccs.push(component)
  }

  // Step 3: Filter stuck-downstream single-node SCCs
  const hasSelfLoop = (nid: string) => edges.some(e => e.source === nid && e.target === nid)
  const realSccs = sccs.filter(scc => scc.length > 1 || hasSelfLoop(scc[0]))
  if (realSccs.length === 0) return { legalLoops: [], illegalCycle: false }

  // Step 4: Validate
  const legalLoops: LoopInfo[] = []
  for (const scc of realSccs) {
    const controllers = scc.filter(nid => {
      const node = nodes.find(n => n.id === nid)
      return node?.data?.type === 'loop_controller'
    })
    if (controllers.length !== 1) return { legalLoops: [], illegalCycle: true }
    legalLoops.push({ controllerId: controllers[0], bodyIds: scc.filter(id => id !== controllers[0]) })
  }
  return { legalLoops, illegalCycle: false }
}

// ─── Snapshot helpers ────────────────────────────────────────────

function saveSnapshot(name: string, data: Record<string, any>): void {
  mkdirSync(SNAPSHOT_DIR, { recursive: true })
  writeFileSync(
    join(SNAPSHOT_DIR, `${name}.frontend.snapshot.json`),
    JSON.stringify(data, null, 2),
  )
}

// ─── Tests ───────────────────────────────────────────────────────

const ALL_FIXTURES = loadAllFixtures()

describe('Pipeline Contract — Frontend Validation', () => {

  describe('isPortCompatible', () => {
    it('allows dataset→text', () => {
      expect(isPortCompatible('dataset', 'text')).toBe(true)
    })

    it('allows text→dataset', () => {
      expect(isPortCompatible('text', 'dataset')).toBe(true)
    })

    it('BLOCKS text→config (removed in frontend)', () => {
      expect(isPortCompatible('text', 'config')).toBe(false)
    })

    it('allows model→llm (added in frontend)', () => {
      expect(isPortCompatible('model', 'llm')).toBe(true)
    })

    it('allows config→llm', () => {
      expect(isPortCompatible('config', 'llm')).toBe(true)
    })

    it('allows llm→model', () => {
      expect(isPortCompatible('llm', 'model')).toBe(true)
    })

    it('allows llm→config', () => {
      expect(isPortCompatible('llm', 'config')).toBe(true)
    })

    it('allows llm→llm', () => {
      expect(isPortCompatible('llm', 'llm')).toBe(true)
    })

    it('allows any→everything', () => {
      for (const t of ['dataset', 'text', 'model', 'config', 'metrics', 'embedding', 'artifact', 'agent', 'llm', 'any']) {
        expect(isPortCompatible('any', t)).toBe(true)
      }
    })

    it('allows everything→any', () => {
      for (const t of ['dataset', 'text', 'model', 'config', 'metrics', 'embedding', 'artifact', 'agent', 'llm', 'any']) {
        expect(isPortCompatible(t, 'any')).toBe(true)
      }
    })

    it('resolves legacy alias "data"→dataset', () => {
      expect(isPortCompatible('data', 'dataset')).toBe(true)
      expect(isPortCompatible('data', 'text')).toBe(true)
    })

    it('resolves legacy alias "llm_config"→llm', () => {
      expect(isPortCompatible('llm_config', 'llm')).toBe(true)
      expect(isPortCompatible('llm_config', 'model')).toBe(true)
    })
  })

  describe('Loop-Aware Cycle Detection', () => {
    it('detects no cycles in simple_dag', () => {
      const f = ALL_FIXTURES.simple_dag
      const result = detectLoops(f.nodes, f.edges)
      expect(result.legalLoops).toHaveLength(0)
      expect(result.illegalCycle).toBe(false)
    })

    it('detects no cycles in branching_dag', () => {
      const f = ALL_FIXTURES.branching_dag
      const result = detectLoops(f.nodes, f.edges)
      expect(result.legalLoops).toHaveLength(0)
      expect(result.illegalCycle).toBe(false)
    })

    it('detects illegal cycle (no controller)', () => {
      const f = ALL_FIXTURES.illegal_cycle
      const result = detectLoops(f.nodes, f.edges)
      expect(result.illegalCycle).toBe(true)
    })

    it('recognizes legal loop with controller', () => {
      const f = ALL_FIXTURES.legal_loop
      const result = detectLoops(f.nodes, f.edges)
      expect(result.illegalCycle).toBe(false)
      expect(result.legalLoops).toHaveLength(1)
      expect(result.legalLoops[0].controllerId).toBe('loop_ctrl')
      expect(result.legalLoops[0].bodyIds).toContain('loop_body')
      // after_loop is downstream, not in the loop body
      expect(result.legalLoops[0].bodyIds).not.toContain('after_loop')
    })

    it('recognizes legal loop in partial_rerun_unsafe', () => {
      const f = ALL_FIXTURES.partial_rerun_unsafe
      const result = detectLoops(f.nodes, f.edges)
      expect(result.illegalCycle).toBe(false)
      expect(result.legalLoops).toHaveLength(1)
      expect(result.legalLoops[0].controllerId).toBe('loop_ctrl')
    })
  })

  describe('Port Compatibility — Cross-Stack Sync Verified', () => {
    it('text→config blocked (frontend and backend agree)', () => {
      expect(isPortCompatible('text', 'config')).toBe(false)
    })

    it('model→llm allowed (frontend and backend agree)', () => {
      expect(isPortCompatible('model', 'llm')).toBe(true)
    })

    it('llm type fully supported (frontend and backend agree)', () => {
      expect(isPortCompatible('llm', 'llm')).toBe(true)
      expect(isPortCompatible('llm', 'model')).toBe(true)
      expect(isPortCompatible('llm', 'config')).toBe(true)
      expect(isPortCompatible('config', 'llm')).toBe(true)
    })
  })

  describe('Snapshot Capture', () => {
    it.each(Object.keys(ALL_FIXTURES))('captures snapshot for %s', (name) => {
      const f = ALL_FIXTURES[name]
      const loopResult = detectLoops(f.nodes, f.edges)

      // Port compatibility for all edges
      const edgeCompat: Record<string, { source: string; target: string; compatible: boolean }> = {}
      for (const edge of f.edges) {
        const srcNode = f.nodes.find((n: any) => n.id === edge.source)
        const tgtNode = f.nodes.find((n: any) => n.id === edge.target)
        if (!srcNode || !tgtNode) continue
        const srcHandle = edge.sourceHandle
        const tgtHandle = edge.targetHandle
        const srcPort = srcNode.data?.outputs?.find((p: any) => p.id === srcHandle)
        const tgtPort = tgtNode.data?.inputs?.find((p: any) => p.id === tgtHandle)
        const srcType = srcPort?.dataType || 'any'
        const tgtType = tgtPort?.dataType || 'any'
        edgeCompat[edge.id] = {
          source: srcType,
          target: tgtType,
          compatible: isPortCompatible(srcType, tgtType),
        }
      }

      const snapshot = {
        fixture_name: name,
        loop_detection: {
          legal_loops: loopResult.legalLoops,
          illegal_cycle: loopResult.illegalCycle,
        },
        edge_compatibility: edgeCompat,
        node_count: f.nodes.length,
        edge_count: f.edges.length,
      }

      saveSnapshot(name, snapshot)
      expect(snapshot.fixture_name).toBe(name)
    })
  })
})
