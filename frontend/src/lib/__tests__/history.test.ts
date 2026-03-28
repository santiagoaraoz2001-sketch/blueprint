import { describe, it, expect } from 'vitest'
import {
  inferOperationType,
  serializeHistory,
  serializeHistoryMeta,
  deserializeHistory,
  deserializeHistoryMeta,
  type HistoryEntry,
} from '../history'

// ── Helpers ──────────────────────────────────────────

function makeNode(id: string, label = 'Node', config: Record<string, unknown> = {}) {
  return {
    id,
    type: 'blockNode',
    position: { x: 0, y: 0 },
    data: { type: 'test', label, category: 'data', icon: '', accent: '', config, status: 'idle' as const, progress: 0 },
  } as any
}

function makeEdge(id: string, source: string, target: string) {
  return { id, source, target } as any
}

function makeEntry(overrides: Partial<HistoryEntry> = {}): HistoryEntry {
  return {
    nodes: [makeNode('a')],
    edges: [],
    description: 'Test entry',
    type: 'add',
    timestamp: '2026-03-28T12:00:00Z',
    ...overrides,
  }
}

// ── inferOperationType ──────────────────────────────

describe('inferOperationType', () => {
  it('detects node addition', () => {
    const prev = [makeNode('a')]
    const curr = [makeNode('a'), makeNode('b', 'LLM Block')]
    const result = inferOperationType(prev, [], curr, [])
    expect(result.type).toBe('add')
    expect(result.description).toContain('LLM Block')
  })

  it('detects multiple node additions', () => {
    const curr = [makeNode('a'), makeNode('b'), makeNode('c')]
    const result = inferOperationType([], [], curr, [])
    expect(result.type).toBe('add')
    expect(result.description).toContain('3 nodes')
  })

  it('detects node removal', () => {
    const prev = [makeNode('a'), makeNode('b', 'Removed')]
    const curr = [makeNode('a')]
    const result = inferOperationType(prev, [], curr, [])
    expect(result.type).toBe('remove')
    expect(result.description).toContain('Removed')
  })

  it('detects edge connection', () => {
    const edges = [makeEdge('e1', 'a', 'b')]
    const result = inferOperationType([], [], [], edges)
    expect(result.type).toBe('connect')
  })

  it('detects edge disconnection', () => {
    const prevEdges = [makeEdge('e1', 'a', 'b')]
    const result = inferOperationType([], prevEdges, [], [])
    expect(result.type).toBe('disconnect')
  })

  it('detects position move', () => {
    const prev = [makeNode('a')]
    const curr = [{ ...makeNode('a'), position: { x: 100, y: 200 } }]
    const result = inferOperationType(prev, [], curr, [])
    expect(result.type).toBe('move')
  })

  it('detects config change', () => {
    const prev = [makeNode('a', 'Node', { model: 'gpt-4' })]
    const curr = [makeNode('a', 'Node', { model: 'claude-3' })]
    const result = inferOperationType(prev, [], curr, [])
    expect(result.type).toBe('config')
  })

  it('detects bulk changes', () => {
    const prev = [makeNode('a')]
    const curr = [makeNode('a'), makeNode('b')]
    const prevEdges: any[] = []
    const currEdges = [makeEdge('e1', 'a', 'b')]
    const result = inferOperationType(prev, prevEdges, curr, currEdges)
    expect(result.type).toBe('bulk')
  })

  it('returns unknown for identical states', () => {
    const nodes = [makeNode('a')]
    const result = inferOperationType(nodes, [], nodes, [])
    expect(result.type).toBe('unknown')
  })
})

// ── serializeHistory / deserializeHistory (full snapshots) ───────

describe('serializeHistory / deserializeHistory', () => {
  it('roundtrips history entries', () => {
    const entry = makeEntry({
      nodes: [makeNode('a')],
      edges: [makeEdge('e1', 'a', 'b')],
      description: 'Added node',
      type: 'add',
    })

    const { json, trimmed } = serializeHistory([entry], [])
    expect(trimmed).toBe(false)

    const restored = deserializeHistory(json)
    expect(restored.past).toHaveLength(1)
    expect(restored.past[0].description).toBe('Added node')
    expect(restored.past[0].type).toBe('add')
    expect(restored.past[0].nodes).toHaveLength(1)
    expect(restored.past[0].edges).toHaveLength(1)
    expect(restored.future).toHaveLength(0)
  })

  it('handles null input', () => {
    const result = deserializeHistory(null)
    expect(result.past).toEqual([])
    expect(result.future).toEqual([])
  })

  it('handles undefined input', () => {
    const result = deserializeHistory(undefined)
    expect(result.past).toEqual([])
    expect(result.future).toEqual([])
  })

  it('handles malformed JSON', () => {
    const result = deserializeHistory('not json')
    expect(result.past).toEqual([])
    expect(result.future).toEqual([])
  })

  it('handles empty string', () => {
    const result = deserializeHistory('')
    expect(result.past).toEqual([])
    expect(result.future).toEqual([])
  })

  it('preserves both past and future', () => {
    const pastEntry = makeEntry({ description: 'Past edit', type: 'config' })
    const futureEntry = makeEntry({ description: 'Future add', type: 'add' })

    const { json } = serializeHistory([pastEntry], [futureEntry])
    const restored = deserializeHistory(json)

    expect(restored.past).toHaveLength(1)
    expect(restored.past[0].description).toBe('Past edit')
    expect(restored.future).toHaveLength(1)
    expect(restored.future[0].description).toBe('Future add')
  })

  it('fills in defaults for missing fields', () => {
    const json = JSON.stringify({
      past: [{ nodes: [makeNode('a')] }],
      future: [],
    })
    const restored = deserializeHistory(json)
    expect(restored.past[0].description).toBe('Edit')
    expect(restored.past[0].type).toBe('unknown')
    expect(restored.past[0].timestamp).toBeTruthy()
  })

  it('returns trimmed=false when under size budget', () => {
    const small = [makeEntry()]
    const { trimmed } = serializeHistory(small, [])
    expect(trimmed).toBe(false)
  })

  it('trims large histories and sets trimmed=true', () => {
    // Create a very large history that would exceed 5MB
    const bigConfig: Record<string, unknown> = {}
    for (let i = 0; i < 200; i++) {
      bigConfig[`key_${i}`] = 'x'.repeat(500)
    }
    const bigNodes = Array.from({ length: 50 }, (_, i) =>
      makeNode(`node_${i}`, `Block ${i}`, bigConfig)
    )
    const entries: HistoryEntry[] = Array.from({ length: 50 }, (_, i) =>
      makeEntry({ nodes: bigNodes, description: `Entry ${i}` })
    )

    const { json, trimmed } = serializeHistory(entries, [])
    // Should have trimmed to fit within budget
    expect(trimmed).toBe(true)
    // Result should still be valid JSON
    const restored = deserializeHistory(json)
    expect(restored.past.length).toBeLessThan(50)
    expect(restored.past.length).toBeGreaterThan(0)
  })
})

// ── serializeHistoryMeta / deserializeHistoryMeta (lightweight) ──

describe('serializeHistoryMeta / deserializeHistoryMeta', () => {
  it('produces lightweight metadata without nodes/edges', () => {
    const entry = makeEntry({
      nodes: [makeNode('a'), makeNode('b')],
      edges: [makeEdge('e1', 'a', 'b')],
      description: 'Added 2 nodes',
      type: 'add',
    })

    const json = serializeHistoryMeta([entry], [])
    const parsed = JSON.parse(json)

    // Should NOT contain nodes/edges
    expect(parsed.past[0].nodes).toBeUndefined()
    expect(parsed.past[0].edges).toBeUndefined()
    // Should contain metadata
    expect(parsed.past[0].description).toBe('Added 2 nodes')
    expect(parsed.past[0].type).toBe('add')
    expect(parsed.past[0].nodeCount).toBe(2)
    expect(parsed.past[0].edgeCount).toBe(1)
  })

  it('is dramatically smaller than full serialization', () => {
    const bigNodes = Array.from({ length: 20 }, (_, i) =>
      makeNode(`node_${i}`, `Block ${i}`, { model: 'gpt-4', temperature: 0.7 })
    )
    const entries: HistoryEntry[] = Array.from({ length: 20 }, (_, i) =>
      makeEntry({ nodes: bigNodes, description: `Entry ${i}` })
    )

    const metaJson = serializeHistoryMeta(entries, [])
    const { json: fullJson } = serializeHistory(entries, [])

    // Metadata should be at least 10x smaller
    expect(metaJson.length).toBeLessThan(fullJson.length / 10)
  })

  it('roundtrips metadata entries', () => {
    const entry = makeEntry({
      nodes: [makeNode('a')],
      edges: [makeEdge('e1', 'a', 'b')],
      description: 'Test',
      type: 'config',
    })

    const json = serializeHistoryMeta([entry], [])
    const restored = deserializeHistoryMeta(json)

    expect(restored.past).toHaveLength(1)
    expect(restored.past[0].description).toBe('Test')
    expect(restored.past[0].type).toBe('config')
    expect(restored.past[0].nodeCount).toBe(1)
    expect(restored.past[0].edgeCount).toBe(1)
  })

  it('handles null/undefined/empty gracefully', () => {
    expect(deserializeHistoryMeta(null).past).toEqual([])
    expect(deserializeHistoryMeta(undefined).past).toEqual([])
    expect(deserializeHistoryMeta('').past).toEqual([])
    expect(deserializeHistoryMeta('bad json').past).toEqual([])
  })
})
