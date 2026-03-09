import { create } from 'zustand'
import { PAPER_TEMPLATES } from '@/lib/paper-templates'

export interface PaperBlock {
  id: string
  type: 'markdown' | 'chart' | 'table' | 'module' | 'data_table' | 'viz_chart'
  // Text for markdown, chart/table/module IDs respectively
  // For data_table: JSON string of { tableId, caption }
  // For viz_chart: JSON string of { chartId, caption }
  content: string
}

export interface PaperSection {
  id: string
  title: string
  type: 'title' | 'abstract' | 'introduction' | 'related_work' | 'methods' | 'experiments' | 'results' | 'analysis' | 'discussion' | 'conclusion' | 'references' | 'custom'
  // Legacy string content. Transitioning to blocks.
  content: string
  blocks: PaperBlock[]
  order: number
  tables?: ImportedTable[]
}

export interface ImportedTable {
  id: string
  runId: string
  tableName: string
  headers: string[]
  rows: string[][]
}

export interface Citation {
  id: string
  key: string
  authors: string
  title: string
  journal: string
  year: string
  doi: string
  url: string
}

export interface ChartConfig {
  id: string
  title: string
  type: 'bar' | 'line' | 'scatter' | 'heatmap' | 'box'
  xField: string
  yField: string
  colorField: string
  data: Record<string, any>[]
  width: number
  height: number
}

let idCounter = 0
function nextId(prefix: string) {
  return `${prefix}_${++idCounter}_${Date.now()}`
}

function createDefaultBlock(content: string = ''): PaperBlock[] {
  return [{ id: nextId('blk'), type: 'markdown', content }]
}

const DEFAULT_SECTIONS: PaperSection[] = [
  { id: 'title', title: 'Title', type: 'title', content: '', blocks: createDefaultBlock(), order: 0 },
  { id: 'abstract', title: 'Abstract', type: 'abstract', content: '', blocks: createDefaultBlock(), order: 1 },
  { id: 'intro', title: 'Introduction', type: 'introduction', content: '', blocks: createDefaultBlock(), order: 2 },
  { id: 'methods', title: 'Methods', type: 'methods', content: '', blocks: createDefaultBlock(), order: 3 },
  { id: 'results', title: 'Results', type: 'results', content: '', blocks: createDefaultBlock(), order: 4 },
  { id: 'discussion', title: 'Discussion', type: 'discussion', content: '', blocks: createDefaultBlock(), order: 5 },
  { id: 'conclusion', title: 'Conclusion', type: 'conclusion', content: '', blocks: createDefaultBlock(), order: 6 },
  { id: 'references', title: 'References', type: 'references', content: '', blocks: createDefaultBlock(), order: 7 },
]

interface PaperState {
  id: string | null
  projectId: string | null
  sections: PaperSection[]
  citations: Citation[]
  charts: ChartConfig[]
  activeSectionId: string | null
  paperTitle: string

  // Project isolation & Backend Sync
  fetchProjectPapers: (projectId: string) => Promise<any[]>
  loadPaper: (paperId: string) => Promise<void>
  savePaper: (projectId: string) => Promise<void>
  deletePaper: (paperId: string) => Promise<void>

  setId: (id: string | null) => void
  setProjectId: (projectId: string | null) => void
  setActiveSectionId: (id: string | null) => void
  setPaperTitle: (title: string) => void

  addSection: (title: string, type: PaperSection['type']) => void
  updateSection: (id: string, updates: Partial<PaperSection>) => void
  removeSection: (id: string) => void
  reorderSections: (sourceIdx: number, destIdx: number) => void

  // Block management
  addBlockToSection: (sectionId: string, block: Omit<PaperBlock, 'id'>) => void
  updateBlock: (sectionId: string, blockId: string, content: string) => void
  removeBlock: (sectionId: string, blockId: string) => void
  reorderBlocks: (sectionId: string, sourceIdx: number, destIdx: number) => void

  addCitation: (citation: Omit<Citation, 'id'>) => void
  updateCitation: (id: string, updates: Partial<Citation>) => void
  removeCitation: (id: string) => void

  addChart: (chart: Omit<ChartConfig, 'id'>) => void
  updateChart: (id: string, updates: Partial<ChartConfig>) => void
  removeChart: (id: string) => void

  insertDataTable: (sectionId: string, tableId: string, caption: string) => void
  insertVizChart: (sectionId: string, chartId: string, caption: string) => void
  autoFormat: (templateId: string) => void

  loadTemplate: (templateId: string) => void
  importRunTable: (runId: string, tableName: string, data: any) => void
  importChart: (config: ChartConfig) => void
  exportMarkdown: () => string
  resetPaper: () => void
}

export const usePaperStore = create<PaperState>((set, get) => ({
  id: null,
  projectId: null,
  sections: [...DEFAULT_SECTIONS],
  citations: [],
  charts: [],
  activeSectionId: 'title',
  paperTitle: 'Untitled Paper',

  fetchProjectPapers: async (projectId: string) => {
    try {
      const baseUrl = import.meta.env.VITE_API_URL || '/api'
      const res = await fetch(`${baseUrl}/papers?project_id=${projectId}`)
      if (!res.ok) throw new Error('Failed to fetch project papers')
      return await res.json()
    } catch (e) {
      console.error('Error fetching papers:', e)
      return []
    }
  },

  loadPaper: async (paperId: string) => {
    try {
      const baseUrl = import.meta.env.VITE_API_URL || '/api'
      const res = await fetch(`${baseUrl}/papers/${paperId}`)
      if (!res.ok) throw new Error('Failed to fetch paper')
      const paper = await res.json()

      const content = paper.content || {}
      set({
        id: paper.id,
        projectId: paper.project_id,
        paperTitle: paper.name,
        sections: content.sections || [...DEFAULT_SECTIONS],
        citations: content.citations || [],
        charts: content.charts || [],
        activeSectionId: content.sections && content.sections.length > 0 ? content.sections[0].id : null,
      })
    } catch (e) {
      console.error('Failed to load paper:', e)
    }
  },

  savePaper: async (projectId: string) => {
    try {
      const state = get()
      const baseUrl = import.meta.env.VITE_API_URL || '/api'

      const isNew = !state.id
      const method = isNew ? 'POST' : 'PUT'
      const url = isNew ? `${baseUrl}/papers` : `${baseUrl}/papers/${state.id}`

      const payload = {
        name: state.paperTitle,
        project_id: projectId,
        content: {
          sections: state.sections,
          citations: state.citations,
          charts: state.charts,
        }
      }

      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })

      if (!res.ok) throw new Error('Failed to save paper')
      const saved = await res.json()
      if (isNew) {
        set({ id: saved.id, projectId: saved.project_id })
      }
    } catch (e) {
      console.error('Error saving paper:', e)
    }
  },

  deletePaper: async (paperId: string) => {
    try {
      const baseUrl = import.meta.env.VITE_API_URL || '/api'
      await fetch(`${baseUrl}/papers/${paperId}`, { method: 'DELETE' })
      const state = get()
      if (state.id === paperId) {
        state.resetPaper()
      }
    } catch (e) {
      console.error('Error deleting paper:', e)
    }
  },

  setId: (id) => set({ id }),
  setProjectId: (projectId) => set({ projectId }),
  setActiveSectionId: (id) => set({ activeSectionId: id }),
  setPaperTitle: (paperTitle) => set({ paperTitle }),

  addSection: (title, type) => {
    const id = nextId('sec')
    set((s) => ({
      sections: [...s.sections, {
        id, title, type, content: '', blocks: [{ id: nextId('blk'), type: 'markdown', content: '' }], order: s.sections.length,
      }],
    }))
  },

  updateSection: (id, updates) => {
    set((s) => ({
      sections: s.sections.map((sec) =>
        sec.id === id ? { ...sec, ...updates } : sec
      ),
    }))
  },

  removeSection: (id) => {
    set((s) => ({
      sections: s.sections.filter((sec) => sec.id !== id),
      activeSectionId: s.activeSectionId === id ? null : s.activeSectionId,
    }))
  },

  reorderSections: (sourceIdx, destIdx) => {
    set((s) => {
      const newSections = [...s.sections]
      const [moved] = newSections.splice(sourceIdx, 1)
      newSections.splice(destIdx, 0, moved)
      return { sections: newSections.map((sec, i) => ({ ...sec, order: i })) }
    })
  },

  addBlockToSection: (sectionId, block) => {
    set((s) => ({
      sections: s.sections.map((sec) => {
        if (sec.id !== sectionId) return sec
        return {
          ...sec,
          blocks: [...(sec.blocks || []), { ...block, id: nextId('blk') }],
        }
      })
    }))
  },

  updateBlock: (sectionId, blockId, content) => {
    set((s) => ({
      sections: s.sections.map((sec) => {
        if (sec.id !== sectionId) return sec
        return {
          ...sec,
          blocks: sec.blocks.map(b => b.id === blockId ? { ...b, content } : b)
        }
      })
    }))
  },

  removeBlock: (sectionId, blockId) => {
    set((s) => ({
      sections: s.sections.map((sec) => {
        if (sec.id !== sectionId) return sec
        return {
          ...sec,
          blocks: sec.blocks.filter(b => b.id !== blockId)
        }
      })
    }))
  },

  reorderBlocks: (sectionId, sourceIdx, destIdx) => {
    set((s) => ({
      sections: s.sections.map((sec) => {
        if (sec.id !== sectionId) return sec
        const newBlocks = [...sec.blocks]
        const [moved] = newBlocks.splice(sourceIdx, 1)
        newBlocks.splice(destIdx, 0, moved)
        return { ...sec, blocks: newBlocks }
      })
    }))
  },

  addCitation: (citation) => {
    const id = nextId('cite')
    set((s) => ({
      citations: [...s.citations, { ...citation, id }],
    }))
  },

  updateCitation: (id, updates) => {
    set((s) => ({
      citations: s.citations.map((c) =>
        c.id === id ? { ...c, ...updates } : c
      ),
    }))
  },

  removeCitation: (id) => {
    set((s) => ({
      citations: s.citations.filter((c) => c.id !== id),
    }))
  },

  addChart: (chart) => {
    const id = nextId('chart')
    set((s) => ({
      charts: [...s.charts, { ...chart, id }],
    }))
  },

  updateChart: (id, updates) => {
    set((s) => ({
      charts: s.charts.map((c) =>
        c.id === id ? { ...c, ...updates } : c
      ),
    }))
  },

  removeChart: (id) => {
    set((s) => ({
      charts: s.charts.filter((c) => c.id !== id),
    }))
  },

  insertDataTable: (sectionId: string, tableId: string, caption: string) => {
    const content = JSON.stringify({ tableId, caption })
    set((s) => ({
      sections: s.sections.map((sec) => {
        if (sec.id !== sectionId) return sec
        return {
          ...sec,
          blocks: [...(sec.blocks || []), { id: nextId('blk'), type: 'data_table' as const, content }],
        }
      }),
    }))
  },

  insertVizChart: (sectionId: string, chartId: string, caption: string) => {
    const content = JSON.stringify({ chartId, caption })
    set((s) => ({
      sections: s.sections.map((sec) => {
        if (sec.id !== sectionId) return sec
        return {
          ...sec,
          blocks: [...(sec.blocks || []), { id: nextId('blk'), type: 'viz_chart' as const, content }],
        }
      }),
    }))
  },

  autoFormat: (templateId: string) => {
    const template = PAPER_TEMPLATES.find((t) => t.id === templateId)
    if (!template) return

    // Apply template formatting rules: reorder sections to match template order,
    // add missing template sections, and preserve existing content
    const state = get()
    const existingSections = [...state.sections]
    const newSections: PaperSection[] = []

    for (let i = 0; i < template.sections.length; i++) {
      const tmplSec = template.sections[i]
      // Try to find a matching existing section by type
      const existing = existingSections.find(
        (s) => s.type === tmplSec.type || s.title.toLowerCase() === tmplSec.title.toLowerCase()
      )

      if (existing) {
        // Remove from existingSections so it won't be matched again
        const idx = existingSections.indexOf(existing)
        existingSections.splice(idx, 1)
        newSections.push({ ...existing, order: i, title: tmplSec.title })
      } else {
        // Create new empty section from template
        newSections.push({
          id: nextId('sec'),
          title: tmplSec.title,
          type: tmplSec.type as PaperSection['type'],
          content: tmplSec.content,
          blocks: createDefaultBlock(tmplSec.content),
          order: i,
        })
      }
    }

    // Append any remaining existing sections that didn't match
    for (const leftover of existingSections) {
      newSections.push({ ...leftover, order: newSections.length })
    }

    set({
      sections: newSections,
      activeSectionId: newSections.length > 0 ? newSections[0].id : null,
    })
  },

  loadTemplate: (templateId: string) => {
    const template = PAPER_TEMPLATES.find((t) => t.id === templateId)
    if (!template) return
    const sections: PaperSection[] = template.sections.map((sec, i) => ({
      id: nextId('sec'),
      title: sec.title,
      type: sec.type as PaperSection['type'],
      content: sec.content,
      blocks: createDefaultBlock(sec.content),
      order: i,
    }))
    set({
      sections,
      citations: [],
      charts: [],
      activeSectionId: sections.length > 0 ? sections[0].id : null,
      paperTitle: `${template.name} Paper`,
    })
  },

  importRunTable: (runId: string, tableName: string, data: any) => {
    const state = get()
    const sectionId = state.activeSectionId
    if (!sectionId) return

    // Parse data into headers and rows
    let headers: string[] = []
    let rows: string[][] = []

    if (Array.isArray(data) && data.length > 0) {
      headers = Object.keys(data[0])
      rows = data.map((row: any) => headers.map((h) => String(row[h] ?? '')))
    } else if (typeof data === 'object' && data !== null) {
      headers = Object.keys(data)
      rows = [headers.map((h) => String(data[h] ?? ''))]
    }

    const table: ImportedTable = {
      id: nextId('tbl'),
      runId,
      tableName,
      headers,
      rows,
    }

    // Build markdown table
    const mdHeader = `| ${headers.join(' | ')} |`
    const mdSep = `| ${headers.map(() => '---').join(' | ')} |`
    const mdRows = rows.map((row) => `| ${row.join(' | ')} |`).join('\n')
    const mdTable = `\n\n**${tableName}** _(Run: ${runId})_\n\n${mdHeader}\n${mdSep}\n${mdRows}\n`

    set((s) => ({
      sections: s.sections.map((sec) => {
        if (sec.id !== sectionId) return sec
        return {
          ...sec,
          content: sec.content + mdTable,
          tables: [...(sec.tables || []), table],
        }
      }),
    }))
  },

  importChart: (config: ChartConfig) => {
    const state = get()
    // Add the chart to the charts list if not already present
    const exists = state.charts.find((c) => c.id === config.id)
    if (!exists) {
      set((s) => ({
        charts: [...s.charts, config],
      }))
    }

    // Also append a chart reference to the active section content
    const sectionId = state.activeSectionId
    if (!sectionId) return

    const chartRef = `\n\n![${config.title}](chart:${config.id})\n_${config.type} chart: ${config.title}_\n`

    set((s) => ({
      sections: s.sections.map((sec) => {
        if (sec.id !== sectionId) return sec
        return { ...sec, content: sec.content + chartRef }
      }),
    }))
  },

  exportMarkdown: () => {
    const { sections, citations, charts, paperTitle } = get()
    let md = `# ${paperTitle}\n\n`

    for (const sec of sections.sort((a, b) => a.order - b.order)) {
      if (sec.type === 'title') continue

      md += `## ${sec.title}\n\n`

      // Serialize blocks
      const blocks = sec.blocks || []

      for (const block of blocks) {
        if (block.type === 'markdown') {
          if (block.content) md += `${block.content}\n\n`
        } else if (block.type === 'chart') {
          const chart = charts.find(c => c.id === block.content)
          if (chart) {
            md += `![${chart.title}](chart:${chart.id})\n*${chart.type} chart: ${chart.title}*\n\n`
          } else {
            md += `*[Missing Chart]*\n\n`
          }
        } else if (block.type === 'table') {
          md += `*Table Reference: ${block.content}*\n\n`
        } else if (block.type === 'module') {
          md += `\`\`\`blueprint-module\n${block.content}\n\`\`\`\n\n`
        } else if (block.type === 'data_table') {
          try {
            const { tableId, caption } = JSON.parse(block.content)
            md += `*[Data Table: ${caption || tableId}]*\n\n`
          } catch {
            md += `*[Data Table]*\n\n`
          }
        } else if (block.type === 'viz_chart') {
          try {
            const { chartId, caption } = JSON.parse(block.content)
            md += `*[Visualization: ${caption || chartId}]*\n\n`
          } catch {
            md += `*[Visualization]*\n\n`
          }
        }
      }

      // Legacy fallback if no blocks exist but content does (e.g. older saved papers)
      if (blocks.length === 0 && sec.content) {
        md += `${sec.content}\n\n`
      }

      // Citations for references section
      if (sec.type === 'references' && citations.length > 0) {
        citations.forEach((c, i) => {
          md += `[${i + 1}] ${c.authors}. "${c.title}." ${c.journal}, ${c.year}.`
          if (c.doi) md += ` DOI: ${c.doi}`
          md += '\n\n'
        })
      }
    }

    // Append chart data as appendix if charts exist
    if (charts.length > 0) {
      md += `---\n\n## Appendix: Chart Data\n\n`
      for (const chart of charts) {
        md += `### ${chart.title} (${chart.type})\n\n`
        if (chart.data.length > 0) {
          const headers = Object.keys(chart.data[0])
          md += `| ${headers.join(' | ')} |\n`
          md += `| ${headers.map(() => '---').join(' | ')} |\n`
          for (const row of chart.data) {
            md += `| ${headers.map((h) => String(row[h] ?? '')).join(' | ')} |\n`
          }
          md += '\n'
        }
      }
    }

    return md
  },

  resetPaper: () => {
    set({
      id: null,
      projectId: null,
      sections: [...DEFAULT_SECTIONS],
      citations: [],
      charts: [],
      activeSectionId: 'title',
      paperTitle: 'Untitled Paper',
    })
  },
}))
