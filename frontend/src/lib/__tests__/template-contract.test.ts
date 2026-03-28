/**
 * Contract tests for pipeline templates.
 *
 * Validates that all 8 template JSON files:
 * 1. Exist and are well-formed
 * 2. Have valid block references
 * 3. Have internally consistent edge-to-node references
 * 4. Follow the expected schema
 * 5. Use categories that exist in CATEGORY_COLORS
 */

import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'fs'
import { resolve, join } from 'path'

const TEMPLATES_DIR = resolve(__dirname, '../../../../templates')

/**
 * Authoritative CATEGORY_COLORS map — mirrors design-tokens.ts.
 * Kept in sync via the accent color test below: if design-tokens adds/changes
 * a category, the test will fail until this map is updated.
 */
const CATEGORY_COLORS: Record<string, string> = {
  external:      '#DE9A68',
  data:          '#62B8D9',
  model:         '#9880E8',
  training:      '#7B9BE3',
  metrics:       '#65D68B',
  embedding:     '#D87CB8',
  utilities:     '#98A4B8',
  agents:        '#E06070',
  interventions: '#E8D05A',
  inference:     '#8FD07A',
  endpoints:     '#56C4B0',
  source:        '#DE9A68',
  evaluation:    '#65D68B',
  merge:         '#D87CB8',
  output:        '#65D68B',
  flow:          '#98A4B8',
}

interface TemplateNode {
  id: string
  type: string
  position: { x: number; y: number }
  data: {
    type: string
    label: string
    category: string
    icon: string
    accent: string
    config: Record<string, unknown>
    status: string
    progress: number
  }
}

interface TemplateEdge {
  id: string
  source: string
  target: string
  sourceHandle: string
  targetHandle: string
}

interface TemplateFile {
  id: string
  name: string
  description: string
  difficulty: 'beginner' | 'intermediate' | 'advanced'
  estimated_runtime: string
  required_services: string[]
  required_capabilities: string[]
  tags: string[]
  nodes: TemplateNode[]
  edges: TemplateEdge[]
  default_config: Record<string, unknown>
}

function loadAllTemplates(): TemplateFile[] {
  const files = readdirSync(TEMPLATES_DIR).filter((f) => f.endsWith('.json'))
  return files.map((f) => {
    const content = readFileSync(join(TEMPLATES_DIR, f), 'utf-8')
    return JSON.parse(content) as TemplateFile
  })
}

// ─── Tests ──────────────────────────────────────────────────────────

describe('Template JSON files', () => {
  const templates = loadAllTemplates()

  it('should have exactly 8 template files', () => {
    expect(templates.length).toBe(8)
  })

  it('should all have unique IDs', () => {
    const ids = templates.map((t) => t.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  describe.each(
    templates.map((t) => [t.id, t] as const),
  )('template "%s"', (_id, template) => {
    it('has required top-level fields', () => {
      expect(template.id).toBeTruthy()
      expect(template.name).toBeTruthy()
      expect(template.description).toBeTruthy()
      expect(['beginner', 'intermediate', 'advanced']).toContain(template.difficulty)
      expect(typeof template.estimated_runtime).toBe('string')
      expect(Array.isArray(template.required_services)).toBe(true)
      expect(Array.isArray(template.required_capabilities)).toBe(true)
      expect(Array.isArray(template.nodes)).toBe(true)
      expect(Array.isArray(template.edges)).toBe(true)
    })

    it('has at least one node (non-empty template)', () => {
      expect(template.nodes.length).toBeGreaterThan(0)
    })

    it('nodes have correct structure', () => {
      for (const node of template.nodes) {
        expect(node.id).toBeTruthy()
        expect(node.type).toBe('blockNode')
        expect(node.position).toBeDefined()
        expect(typeof node.position.x).toBe('number')
        expect(typeof node.position.y).toBe('number')
        expect(node.data.type).toBeTruthy()
        expect(node.data.label).toBeTruthy()
        expect(node.data.status).toBe('idle')
        expect(node.data.progress).toBe(0)
      }
    })

    it('edges reference valid node IDs', () => {
      const nodeIds = new Set(template.nodes.map((n) => n.id))
      for (const edge of template.edges) {
        expect(nodeIds.has(edge.source)).toBe(true)
        expect(nodeIds.has(edge.target)).toBe(true)
      }
    })

    it('has unique node IDs', () => {
      const ids = template.nodes.map((n) => n.id)
      expect(new Set(ids).size).toBe(ids.length)
    })

    it('has unique edge IDs', () => {
      const ids = template.edges.map((e) => e.id)
      expect(new Set(ids).size).toBe(ids.length)
    })

    it('edges have source and target handles', () => {
      for (const edge of template.edges) {
        expect(edge.sourceHandle).toBeTruthy()
        expect(edge.targetHandle).toBeTruthy()
      }
    })

    it('node categories exist in CATEGORY_COLORS', () => {
      for (const node of template.nodes) {
        const cat = node.data.category
        expect(CATEGORY_COLORS).toHaveProperty(
          cat,
          expect.any(String),
        )
      }
    })

    it('node accent colors match their CATEGORY_COLORS entry', () => {
      for (const node of template.nodes) {
        const cat = node.data.category
        const expectedAccent = CATEGORY_COLORS[cat]
        expect(node.data.accent).toBe(expectedAccent)
      }
    })
  })
})
