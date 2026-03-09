import { useState, useRef, useCallback, useMemo, useEffect } from 'react'
import { motion } from 'framer-motion'
import { T, F, FD, FS } from '@/lib/design-tokens'
import { usePaperStore } from '@/stores/paperStore'
import { useUIStore } from '@/stores/uiStore'
import { PAPER_TEMPLATES } from '@/lib/paper-templates'
import ChartBuilder from '@/components/Paper/ChartBuilder'
import CitationManager from '@/components/Paper/CitationManager'
import {
  FileText, Plus, Download, RotateCcw, ChevronRight, ChevronDown,
  BarChart3, BookOpen, X, Eye, GripVertical, Layout,
  Bold, Italic, Heading1, Heading2, List, Code, Link, Table,
  Save, Trash2, Wand2, Database, LineChart,
} from 'lucide-react'
import PaperBlockLibrary from '@/components/Paper/PaperBlockLibrary'
import ChartBlock from '@/components/Paper/Blocks/ChartBlock'
import { TableBlock, ModuleBlock } from '@/components/Paper/Blocks/DataBlocks'
import { useDataStore } from '@/stores/dataStore'
import { useVizStore } from '@/stores/vizStore'
import toast from 'react-hot-toast'

/* -------------------------------------------------------------------------- */
/*  Section type icon mapping                                                  */
/* -------------------------------------------------------------------------- */

const SECTION_ICONS: Record<string, React.ReactNode> = {
  title: <FileText size={9} />,
  abstract: <FileText size={9} />,
  introduction: <ChevronRight size={9} />,
  related_work: <BookOpen size={9} />,
  methods: <ChevronRight size={9} />,
  experiments: <BarChart3 size={9} />,
  results: <BarChart3 size={9} />,
  analysis: <BarChart3 size={9} />,
  discussion: <ChevronRight size={9} />,
  conclusion: <ChevronRight size={9} />,
  references: <BookOpen size={9} />,
  custom: <FileText size={9} />,
}

/* -------------------------------------------------------------------------- */
/*  Markdown-to-HTML converter (basic, no external deps)                       */
/* -------------------------------------------------------------------------- */

function markdownToHtml(md: string): string {
  if (!md) return ''
  let html = md
    // Escape HTML entities first
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Code blocks (fenced)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_m, _lang, code) =>
    `<pre style="background:${T.surface3};padding:8px;border:1px solid ${T.border};overflow-x:auto;font-family:${F};font-size:${FS.sm}px"><code>${code.trim()}</code></pre>`)

  // Inline code
  html = html.replace(/`([^`]+)`/g, `<code style="background:${T.surface3};padding:1px 4px;font-family:${F};font-size:${FS.sm}px">$1</code>`)

  // Headers
  html = html.replace(/^#### (.+)$/gm, `<h4 style="font-family:${FD};font-size:${FS.lg}px;font-weight:700;color:${T.text};margin:12px 0 4px 0">$1</h4>`)
  html = html.replace(/^### (.+)$/gm, `<h3 style="font-family:${FD};font-size:${FS.xl}px;font-weight:700;color:${T.text};margin:14px 0 6px 0">$1</h3>`)
  html = html.replace(/^## (.+)$/gm, `<h2 style="font-family:${FD};font-size:${FS.h3}px;font-weight:700;color:${T.text};margin:16px 0 6px 0">$1</h2>`)
  html = html.replace(/^# (.+)$/gm, `<h1 style="font-family:${FD};font-size:${FS.h2}px;font-weight:700;color:${T.text};margin:16px 0 8px 0">$1</h1>`)

  // Bold & italic
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  html = html.replace(/_(.+?)_/g, '<em>$1</em>')

  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, `<a href="$2" style="color:${T.cyan};text-decoration:none" target="_blank" rel="noopener">$1</a>`)

  // Tables
  html = html.replace(/((?:\|[^\n]+\|\n)+)/g, (tableBlock) => {
    const lines = tableBlock.trim().split('\n')
    if (lines.length < 2) return tableBlock
    const headerCells = lines[0].split('|').filter((c) => c.trim())
    // Check if line 2 is separator
    const isSep = /^\|?\s*[-:]+/.test(lines[1])
    const dataStart = isSep ? 2 : 1
    let tbl = `<table style="border-collapse:collapse;width:100%;margin:8px 0;font-family:${F};font-size:${FS.sm}px">`
    tbl += '<thead><tr>'
    headerCells.forEach((c) => {
      tbl += `<th style="border:1px solid ${T.border};padding:4px 8px;text-align:left;background:${T.surface2};color:${T.text};font-weight:700;font-size:${FS.xs}px;text-transform:uppercase;letter-spacing:0.06em">${c.trim()}</th>`
    })
    tbl += '</tr></thead><tbody>'
    for (let i = dataStart; i < lines.length; i++) {
      const cells = lines[i].split('|').filter((c) => c.trim())
      tbl += '<tr>'
      cells.forEach((c) => {
        tbl += `<td style="border:1px solid ${T.border};padding:4px 8px;color:${T.sec}">${c.trim()}</td>`
      })
      tbl += '</tr>'
    }
    tbl += '</tbody></table>'
    return tbl
  })

  // Unordered lists
  html = html.replace(/^[\-\*] (.+)$/gm, `<li style="margin-left:16px;color:${T.sec}">$1</li>`)

  // Ordered lists
  html = html.replace(/^\d+\. (.+)$/gm, `<li style="margin-left:16px;color:${T.sec};list-style-type:decimal">$1</li>`)

  // Horizontal rules
  html = html.replace(/^---$/gm, `<hr style="border:none;border-top:1px solid ${T.border};margin:12px 0" />`)

  // Paragraphs (double newline)
  html = html.replace(/\n\n+/g, '</p><p>')
  html = `<p>${html}</p>`
  html = html.replace(/<p><\/p>/g, '')

  // Single line breaks
  html = html.replace(/\n/g, '<br/>')

  return html
}

/* -------------------------------------------------------------------------- */
/*  Right panel type                                                           */
/* -------------------------------------------------------------------------- */

type RightPanel = 'charts' | 'citations' | 'preview'

/* -------------------------------------------------------------------------- */
/*  PaperView                                                                  */
/* -------------------------------------------------------------------------- */

export default function PaperView() {
  const {
    projectId, sections, activeSectionId, paperTitle,
    setActiveSectionId, setPaperTitle,
    addSection, updateSection, removeSection, reorderSections,
    addBlockToSection, updateBlock, removeBlock, reorderBlocks,
    loadTemplate, autoFormat,
    insertDataTable, insertVizChart,
    exportMarkdown, resetPaper, savePaper
  } = usePaperStore()

  const { selectedProjectId, setView } = useUIStore()
  const dataTables = useDataStore((s) => s.tables)
  const vizDashboards = useVizStore((s) => s.dashboards)

  // Enforce project isolation and match projects
  useEffect(() => {
    if (!selectedProjectId) {
      toast.error('Please select a project first')
      setView('dashboard')
    } else if (projectId && projectId !== selectedProjectId) {
      // Trying to open a paper belonging to another project
      setView('dashboard')
      toast.error('The selected paper does not belong to the active project')
    } else if (!projectId && selectedProjectId) {
      // New paper, make sure it knows the active project
      usePaperStore.getState().setProjectId(selectedProjectId)
    }
  }, [selectedProjectId, projectId, setView])

  const [rightPanel, setRightPanel] = useState<RightPanel>('preview')
  const [templateDropdown, setTemplateDropdown] = useState(false)
  const [autoFormatDropdown, setAutoFormatDropdown] = useState(false)
  const [importDataDropdown, setImportDataDropdown] = useState(false)
  const [importChartDropdown, setImportChartDropdown] = useState(false)
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null)

  // Block dragging state
  const [dragBlockIdx, setDragBlockIdx] = useState<number | null>(null)
  const [dragBlockOverIdx, setDragBlockOverIdx] = useState<number | null>(null)

  // Track which block is focused for toolbar injections
  const [activeBlockId, setActiveBlockId] = useState<string | null>(null)

  // Ref mapped by block ID for targeted insertions
  const textareasRef = useRef<Record<string, HTMLTextAreaElement | null>>({})

  const sortedSections = useMemo(
    () => [...sections].sort((a, b) => a.order - b.order),
    [sections],
  )

  const activeSection = sections.find((s) => s.id === activeSectionId)

  // Auto-numbering: scan all blocks across all sections and assign Fig/Table numbers
  const autoNumbers = useMemo(() => {
    const numbers: Record<string, string> = {}
    let figCount = 0
    let tableCount = 0
    for (const sec of sortedSections) {
      for (const block of sec.blocks || []) {
        if (block.type === 'chart' || block.type === 'viz_chart') {
          figCount++
          numbers[block.id] = `Fig. ${figCount}`
        } else if (block.type === 'table' || block.type === 'data_table') {
          tableCount++
          numbers[block.id] = `Table ${tableCount}`
        }
      }
    }
    return numbers
  }, [sortedSections])

  /* ------ Export handler ------ */
  const handleExport = () => {
    const md = exportMarkdown()
    const blob = new Blob([md], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${paperTitle.replace(/\s+/g, '_').toLowerCase()}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  /* ------ Add section handler ------ */
  const handleAddSection = () => {
    addSection('New Section', 'custom')
  }

  /* ------ Save Paper ------ */
  const handleSave = async () => {
    if (!selectedProjectId) return
    await savePaper(selectedProjectId)
    toast.success('Paper saved to project')
  }

  /* ------ Insert Markdown syntax at cursor ------ */
  const insertAtCursor = useCallback((before: string, after: string = '') => {
    if (!activeSection || !activeBlockId) return
    const ta = textareasRef.current[activeBlockId]
    if (!ta) return

    // Find the actual block data
    const block = activeSection.blocks.find(b => b.id === activeBlockId)
    if (!block) return

    const start = ta.selectionStart
    const end = ta.selectionEnd
    const text = block.content
    const selected = text.substring(start, end)
    const newText = text.substring(0, start) + before + selected + after + text.substring(end)

    updateBlock(activeSection.id, activeBlockId, newText)

    // Restore cursor
    requestAnimationFrame(() => {
      if (ta) {
        ta.focus()
        const cursorPos = start + before.length + selected.length + after.length
        ta.setSelectionRange(
          selected.length > 0 ? cursorPos : start + before.length,
          selected.length > 0 ? cursorPos : start + before.length,
        )
      }
    })
  }, [activeSection, activeBlockId, updateBlock])

  /* ------ Toolbar buttons config ------ */
  const toolbarButtons = [
    { icon: Bold, label: 'B', action: () => insertAtCursor('**', '**') },
    { icon: Italic, label: 'I', action: () => insertAtCursor('*', '*') },
    { icon: Heading1, label: 'H1', action: () => insertAtCursor('\n# ') },
    { icon: Heading2, label: 'H2', action: () => insertAtCursor('\n## ') },
    { icon: List, label: 'List', action: () => insertAtCursor('\n- ') },
    { icon: Code, label: 'Code', action: () => insertAtCursor('`', '`') },
    { icon: Link, label: 'Link', action: () => insertAtCursor('[', '](url)') },
    { icon: Table, label: 'Table', action: () => insertAtCursor('\n| Column 1 | Column 2 | Column 3 |\n| --- | --- | --- |\n| Cell | Cell | Cell |\n') },
  ]

  /* ------ Drag handlers for section reorder ------ */
  const handleDragStart = (idx: number) => {
    setDragIdx(idx)
  }
  const handleDragOver = (e: React.DragEvent, idx: number) => {
    e.preventDefault()
    setDragOverIdx(idx)
  }
  const handleDrop = (idx: number) => {
    if (dragIdx !== null && dragIdx !== idx) {
      reorderSections(dragIdx, idx)
    }
    setDragIdx(null)
    setDragOverIdx(null)
  }
  const handleDragEnd = () => {
    setDragIdx(null)
    setDragOverIdx(null)
  }

  /* ------ Drag handlers for Blocks ------ */
  const handleBlockDragStart = (idx: number) => {
    setDragBlockIdx(idx)
  }
  const handleBlockDragOver = (e: React.DragEvent, idx: number) => {
    e.preventDefault()
    setDragBlockOverIdx(idx)
  }
  const handleBlockDrop = (e: React.DragEvent, idx: number) => {
    e.preventDefault()
    e.stopPropagation()
    if (!activeSection) return

    // If this is a palette drop onto a specific block position, insert there
    const blockType = e.dataTransfer.getData('application/blueprint-paper-block')
    if (blockType && (blockType === 'markdown' || blockType === 'chart' || blockType === 'table' || blockType === 'module')) {
      // Insert at this position
      addBlockToSection(activeSection.id, { type: blockType, content: '' })
      setDragBlockIdx(null)
      setDragBlockOverIdx(null)
      return
    }

    // Otherwise it's a block reorder
    if (dragBlockIdx !== null && dragBlockIdx !== idx) {
      reorderBlocks(activeSection.id, dragBlockIdx, idx)
    }
    setDragBlockIdx(null)
    setDragBlockOverIdx(null)
  }
  const handleBlockDragEnd = () => {
    setDragBlockIdx(null)
    setDragBlockOverIdx(null)
  }

  const handleEditorDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (!activeSection) return

    // Check if it's a new block from the library
    const blockType = e.dataTransfer.getData('application/blueprint-paper-block')
    if (blockType && (blockType === 'markdown' || blockType === 'chart' || blockType === 'table' || blockType === 'module')) {
      addBlockToSection(activeSection.id, {
        type: blockType,
        content: ''
      })
    }
  }

  const handleEditorDragOver = (e: React.DragEvent) => {
    e.preventDefault() // Required to allow drop
  }

  /* ------ Preview HTML for active section ------ */
  const previewHtml = useMemo(() => {
    if (!activeSection) return ''
    let fullMd = ''
    for (const b of activeSection.blocks || []) {
      if (b.type === 'markdown') fullMd += b.content + '\n\n'
      else if (b.type === 'module') fullMd += `\`\`\`blueprint-module\n${b.content}\n\`\`\`\n\n`
      else if (b.type === 'chart') fullMd += `*[Chart Placeholder: ${b.content}]*\n\n`
      else if (b.type === 'table') fullMd += `*[Table Placeholder: ${b.content}]*\n\n`
    }
    // Legacy fallback
    if ((!activeSection.blocks || activeSection.blocks.length === 0) && activeSection.content) {
      fullMd += activeSection.content
    }
    return markdownToHtml(fullMd)
  }, [activeSection])

  /* ------ Full document preview HTML ------ */
  const fullPreviewHtml = useMemo(() => {
    let html = `<h1 style="font-family:${FD};font-size:${FS.h2}px;font-weight:700;color:${T.text};margin-bottom:12px;letter-spacing:0.04em">${paperTitle}</h1>`
    for (const sec of sortedSections) {
      if (sec.type === 'title') continue
      html += `<h2 style="font-family:${FD};font-size:${FS.xl}px;font-weight:700;color:${T.text};margin:14px 0 4px 0">${sec.title}</h2>`

      let secMd = ''
      for (const b of sec.blocks || []) {
        if (b.type === 'markdown') secMd += b.content + '\n\n'
        else if (b.type === 'module') secMd += `\`\`\`blueprint-module\n${b.content}\n\`\`\`\n\n`
        else if (b.type === 'chart') secMd += `*[Chart Placeholder: ${b.content}]*\n\n`
        else if (b.type === 'table') secMd += `*[Table Placeholder: ${b.content}]*\n\n`
      }

      if ((!sec.blocks || sec.blocks.length === 0) && sec.content) {
        secMd += sec.content
      }

      if (secMd) {
        html += markdownToHtml(secMd)
      } else {
        html += `<p style="color:${T.dim};font-style:italic">Empty section</p>`
      }
    }
    return html
  }, [sortedSections, paperTitle])

  /* ---------- Shared button style helper ---------- */
  const btnStyle = (active?: boolean): React.CSSProperties => ({
    display: 'flex', alignItems: 'center', gap: 4,
    padding: '3px 8px',
    background: active ? `${T.cyan}14` : T.surface3,
    border: `1px solid ${active ? T.cyan + '40' : T.border}`,
    color: active ? T.cyan : T.sec,
    fontFamily: F, fontSize: FS.xs,
    letterSpacing: '0.08em', cursor: 'pointer',
    fontWeight: active ? 900 : 400,
  })

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* ====== TOP TOOLBAR ====== */}
      <div
        style={{
          height: 34, display: 'flex', alignItems: 'center',
          padding: '0 10px', gap: 8,
          borderBottom: `1px solid ${T.border}`,
          background: T.surface1, flexShrink: 0,
        }}
      >
        {/* Paper title */}
        <input
          value={paperTitle}
          onChange={(e) => setPaperTitle(e.target.value)}
          style={{
            background: 'none', border: 'none', color: T.text,
            fontFamily: F, fontSize: FS.lg, fontWeight: 600,
            outline: 'none', padding: '2px 4px', width: 200,
          }}
        />

        <div style={{ flex: 1 }} />

        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          {sections.length} SECTIONS
        </span>
        <div style={{ width: 1, height: 14, background: T.border }} />

        {/* Template dropdown */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setTemplateDropdown(!templateDropdown)}
            style={btnStyle(templateDropdown)}
          >
            <Layout size={10} />
            NEW FROM TEMPLATE
            <ChevronDown size={8} style={{ transform: templateDropdown ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }} />
          </button>
          {templateDropdown && (
            <div
              style={{
                position: 'absolute', top: '100%', right: 0,
                marginTop: 4, width: 260, zIndex: 100,
                background: T.surface2, border: `1px solid ${T.border}`,
                boxShadow: `0 8px 24px ${T.shadow}`,
              }}
            >
              {PAPER_TEMPLATES.map((tmpl) => (
                <button
                  key={tmpl.id}
                  onClick={() => {
                    loadTemplate(tmpl.id)
                    setTemplateDropdown(false)
                  }}
                  style={{
                    display: 'block', width: '100%', textAlign: 'left',
                    padding: '8px 12px', background: 'transparent',
                    border: 'none', borderBottom: `1px solid ${T.border}`,
                    cursor: 'pointer', transition: 'background 0.1s',
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = T.surface4}
                  onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                >
                  <div style={{ fontFamily: F, fontSize: FS.sm, fontWeight: 700, color: T.text, letterSpacing: '0.06em' }}>
                    {tmpl.name}
                  </div>
                  <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 2 }}>
                    {tmpl.description} -- {tmpl.sections.length} sections
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Auto-Format dropdown */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setAutoFormatDropdown(!autoFormatDropdown)}
            style={{
              ...btnStyle(autoFormatDropdown),
              color: T.purple,
              borderColor: `${T.purple}40`,
              background: autoFormatDropdown ? `${T.purple}14` : T.surface3,
            }}
          >
            <Wand2 size={10} />
            AUTO-FORMAT
            <ChevronDown size={8} style={{ transform: autoFormatDropdown ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }} />
          </button>
          {autoFormatDropdown && (
            <div
              style={{
                position: 'absolute', top: '100%', right: 0,
                marginTop: 4, width: 260, zIndex: 100,
                background: T.surface2, border: `1px solid ${T.border}`,
                boxShadow: `0 8px 24px ${T.shadow}`,
                borderRadius: 4,
              }}
            >
              <div style={{
                padding: '6px 12px', fontFamily: F, fontSize: FS.xxs, color: T.dim,
                fontWeight: 700, letterSpacing: '0.08em', borderBottom: `1px solid ${T.border}`,
              }}>
                APPLY TEMPLATE FORMAT
              </div>
              {PAPER_TEMPLATES.map((tmpl) => (
                <button
                  key={tmpl.id}
                  onClick={() => {
                    autoFormat(tmpl.id)
                    setAutoFormatDropdown(false)
                    toast.success(`Applied ${tmpl.name} formatting`)
                  }}
                  style={{
                    display: 'block', width: '100%', textAlign: 'left',
                    padding: '8px 12px', background: 'transparent',
                    border: 'none', borderBottom: `1px solid ${T.border}`,
                    cursor: 'pointer', transition: 'background 0.1s',
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = T.surface4}
                  onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                >
                  <div style={{ fontFamily: F, fontSize: FS.sm, fontWeight: 700, color: T.text, letterSpacing: '0.06em' }}>
                    {tmpl.name}
                  </div>
                  <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 2 }}>
                    Reorder sections to match {tmpl.name} format
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Save */}
        <button onClick={handleSave} style={{ ...btnStyle(), color: T.green, borderColor: `${T.green}40`, background: `${T.green}14` }}>
          <Save size={10} /> SAVE
        </button>

        {/* Export */}
        <button onClick={handleExport} style={btnStyle()}>
          <Download size={10} /> EXPORT MARKDOWN
        </button>

        {/* Reset */}
        <button
          onClick={resetPaper}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '3px 8px', background: 'transparent',
            border: `1px solid ${T.border}`, color: T.dim,
            fontFamily: F, fontSize: FS.xs, cursor: 'pointer',
          }}
        >
          <RotateCcw size={9} />
        </button>
      </div>

      {/* ====== MAIN AREA ====== */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* ====== LEFT: Block Palette (260px) ====== */}
        <PaperBlockLibrary />

        {/* ====== MID-LEFT: Section Navigator (200px) ====== */}
        <div
          style={{
            width: 200, minWidth: 200,
            borderRight: `1px solid ${T.border}`,
            background: T.surface0,
            display: 'flex', flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              padding: '8px 10px',
              fontFamily: F, fontSize: FS.xxs, fontWeight: 900,
              letterSpacing: '0.12em', color: T.dim,
              borderBottom: `1px solid ${T.border}`,
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            }}
          >
            SECTIONS
            <button
              onClick={handleAddSection}
              style={{
                background: 'none', border: 'none', color: T.cyan,
                cursor: 'pointer', padding: 2, display: 'flex',
              }}
            >
              <Plus size={10} />
            </button>
          </div>

          <div style={{ flex: 1, overflowY: 'auto' }}>
            {sortedSections.map((sec, index) => (
              <motion.div
                key={sec.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.03, duration: 0.2 }}
                draggable
                onDragStart={() => handleDragStart(index)}
                onDragOver={(e) => handleDragOver(e as unknown as React.DragEvent, index)}
                onDrop={() => handleDrop(index)}
                onDragEnd={handleDragEnd}
                style={{
                  borderBottom: dragOverIdx === index ? `2px solid ${T.cyan}` : '2px solid transparent',
                  opacity: dragIdx === index ? 0.4 : 1,
                  transition: 'opacity 0.15s',
                }}
              >
                <button
                  onClick={() => setActiveSectionId(sec.id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    width: '100%', padding: '7px 10px',
                    background: activeSectionId === sec.id ? `${T.cyan}08` : 'transparent',
                    border: 'none',
                    borderLeft: activeSectionId === sec.id ? `2px solid ${T.cyan}` : '2px solid transparent',
                    color: activeSectionId === sec.id ? T.text : T.dim,
                    fontFamily: F, fontSize: FS.sm, fontWeight: activeSectionId === sec.id ? 700 : 400,
                    cursor: 'pointer', textAlign: 'left',
                    transition: 'all 0.12s',
                  }}
                  onMouseEnter={(e) => {
                    if (activeSectionId !== sec.id) e.currentTarget.style.background = T.surface2
                  }}
                  onMouseLeave={(e) => {
                    if (activeSectionId !== sec.id) e.currentTarget.style.background = 'transparent'
                  }}
                >
                  {/* Drag handle */}
                  <span style={{ flexShrink: 0, color: T.dim, cursor: 'grab', display: 'flex' }}>
                    <GripVertical size={8} />
                  </span>
                  {/* Icon */}
                  <span style={{ flexShrink: 0, color: activeSectionId === sec.id ? T.cyan : T.dim }}>
                    {SECTION_ICONS[sec.type] || <FileText size={9} />}
                  </span>
                  {/* Title + type */}
                  <span style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', gap: 1 }}>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {sec.title}
                    </span>
                    <span style={{
                      fontFamily: F, fontSize: FS.xxs, color: T.dim,
                      letterSpacing: '0.08em', textTransform: 'uppercase',
                    }}>
                      {sec.type.replace('_', ' ')}
                    </span>
                  </span>
                  {/* Remove */}
                  <span
                    onClick={(e) => { e.stopPropagation(); removeSection(sec.id) }}
                    style={{ color: T.dim, cursor: 'pointer', flexShrink: 0, display: 'flex' }}
                  >
                    <X size={7} />
                  </span>
                </button>
              </motion.div>
            ))}

            {/* Add section button at bottom */}
            <button
              onClick={handleAddSection}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4,
                width: '100%', padding: '10px',
                background: 'transparent', border: 'none',
                borderTop: `1px solid ${T.border}`,
                color: T.dim, fontFamily: F, fontSize: FS.xs,
                letterSpacing: '0.08em', cursor: 'pointer',
                transition: 'color 0.1s',
              }}
              onMouseEnter={(e) => e.currentTarget.style.color = T.cyan}
              onMouseLeave={(e) => e.currentTarget.style.color = T.dim}
            >
              <Plus size={9} /> ADD SECTION
            </button>
          </div>
        </div>

        {/* ====== CENTER: Editor ====== */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {activeSection ? (
            <>
              {/* Section header */}
              <div
                style={{
                  padding: '10px 16px',
                  borderBottom: `1px solid ${T.border}`,
                  background: T.surface0,
                }}
              >
                <input
                  value={activeSection.title}
                  onChange={(e) => updateSection(activeSection.id, { title: e.target.value })}
                  style={{
                    background: 'none', border: 'none', color: T.text,
                    fontFamily: FD, fontSize: FS.h2, fontWeight: 700,
                    letterSpacing: '0.04em', outline: 'none', width: '100%',
                  }}
                />
                <div style={{
                  fontFamily: F, fontSize: FS.xxs, color: T.dim,
                  marginTop: 2, letterSpacing: '0.08em',
                }}>
                  {activeSection.type.toUpperCase().replace('_', ' ')} -- {activeSection.blocks?.length || 0} BLOCKS
                </div>
              </div>

              {/* Formatting toolbar */}
              <div
                style={{
                  display: 'flex', alignItems: 'center', gap: 2,
                  padding: '4px 16px',
                  borderBottom: `1px solid ${T.border}`,
                  background: T.surface1,
                  flexShrink: 0,
                }}
              >
                {toolbarButtons.map(({ icon: Icon, label, action }) => (
                  <button
                    key={label}
                    onClick={action}
                    title={label}
                    style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 3,
                      padding: '3px 7px',
                      background: 'transparent',
                      border: `1px solid transparent`,
                      color: T.sec,
                      fontFamily: F, fontSize: FS.xs, fontWeight: 700,
                      cursor: 'pointer',
                      transition: 'all 0.1s',
                      minWidth: 24, height: 22,
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = T.surface3
                      e.currentTarget.style.borderColor = T.border
                      e.currentTarget.style.color = T.cyan
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = 'transparent'
                      e.currentTarget.style.borderColor = 'transparent'
                      e.currentTarget.style.color = T.sec
                    }}
                  >
                    <Icon size={10} />
                    <span style={{ fontSize: FS.xxs, letterSpacing: '0.06em' }}>{label}</span>
                  </button>
                ))}
                <div style={{ width: 1, height: 14, background: T.border, margin: '0 4px' }} />

                {/* Import from Data */}
                <div style={{ position: 'relative' }}>
                  <button
                    onClick={() => { setImportDataDropdown(!importDataDropdown); setImportChartDropdown(false) }}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 4,
                      padding: '3px 7px', background: importDataDropdown ? `${T.cyan}12` : 'transparent',
                      border: `1px solid ${importDataDropdown ? T.cyan + '40' : 'transparent'}`,
                      color: importDataDropdown ? T.cyan : T.sec,
                      fontFamily: F, fontSize: FS.xxs, fontWeight: 700,
                      cursor: 'pointer', transition: 'all 0.1s', height: 22,
                      letterSpacing: '0.06em',
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = T.surface3; e.currentTarget.style.color = T.cyan }}
                    onMouseLeave={(e) => {
                      if (!importDataDropdown) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = T.sec }
                    }}
                  >
                    <Database size={9} />
                    DATA
                  </button>
                  {importDataDropdown && (
                    <div style={{
                      position: 'absolute', top: '100%', left: 0, marginTop: 4,
                      width: 220, zIndex: 100, background: T.surface2,
                      border: `1px solid ${T.border}`, boxShadow: `0 8px 24px ${T.shadow}`,
                      borderRadius: 4, maxHeight: 240, overflowY: 'auto',
                    }}>
                      <div style={{
                        padding: '6px 10px', fontFamily: F, fontSize: FS.xxs, color: T.dim,
                        fontWeight: 700, letterSpacing: '0.08em', borderBottom: `1px solid ${T.border}`,
                      }}>
                        INSERT DATA TABLE
                      </div>
                      {dataTables.length === 0 ? (
                        <div style={{ padding: '10px 12px', fontFamily: F, fontSize: FS.xxs, color: T.dim, fontStyle: 'italic' }}>
                          No data tables available
                        </div>
                      ) : (
                        dataTables.map((dt) => (
                          <button
                            key={dt.id}
                            onClick={() => {
                              if (activeSection) {
                                insertDataTable(activeSection.id, dt.id, dt.name)
                                toast.success(`Inserted table: ${dt.name}`)
                              }
                              setImportDataDropdown(false)
                            }}
                            style={{
                              display: 'flex', alignItems: 'center', gap: 8,
                              width: '100%', padding: '7px 12px', background: 'transparent',
                              border: 'none', borderBottom: `1px solid ${T.border}`,
                              cursor: 'pointer', textAlign: 'left',
                            }}
                            onMouseEnter={(e) => e.currentTarget.style.background = T.surface4}
                            onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                          >
                            <Database size={10} color={T.cyan} />
                            <div>
                              <div style={{ fontFamily: F, fontSize: FS.xs, fontWeight: 600, color: T.text }}>{dt.name}</div>
                              <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>{dt.rows.length} rows, {dt.columns.length} cols</div>
                            </div>
                          </button>
                        ))
                      )}
                    </div>
                  )}
                </div>

                {/* Import from Charts */}
                <div style={{ position: 'relative' }}>
                  <button
                    onClick={() => { setImportChartDropdown(!importChartDropdown); setImportDataDropdown(false) }}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 4,
                      padding: '3px 7px', background: importChartDropdown ? `${T.cyan}12` : 'transparent',
                      border: `1px solid ${importChartDropdown ? T.cyan + '40' : 'transparent'}`,
                      color: importChartDropdown ? T.cyan : T.sec,
                      fontFamily: F, fontSize: FS.xxs, fontWeight: 700,
                      cursor: 'pointer', transition: 'all 0.1s', height: 22,
                      letterSpacing: '0.06em',
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = T.surface3; e.currentTarget.style.color = T.cyan }}
                    onMouseLeave={(e) => {
                      if (!importChartDropdown) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = T.sec }
                    }}
                  >
                    <LineChart size={9} />
                    CHARTS
                  </button>
                  {importChartDropdown && (
                    <div style={{
                      position: 'absolute', top: '100%', left: 0, marginTop: 4,
                      width: 240, zIndex: 100, background: T.surface2,
                      border: `1px solid ${T.border}`, boxShadow: `0 8px 24px ${T.shadow}`,
                      borderRadius: 4, maxHeight: 280, overflowY: 'auto',
                    }}>
                      <div style={{
                        padding: '6px 10px', fontFamily: F, fontSize: FS.xxs, color: T.dim,
                        fontWeight: 700, letterSpacing: '0.08em', borderBottom: `1px solid ${T.border}`,
                      }}>
                        INSERT CHART FROM DASHBOARD
                      </div>
                      {vizDashboards.length === 0 ? (
                        <div style={{ padding: '10px 12px', fontFamily: F, fontSize: FS.xxs, color: T.dim, fontStyle: 'italic' }}>
                          No dashboards available
                        </div>
                      ) : (
                        vizDashboards.map((dash) => (
                          <div key={dash.id}>
                            <div style={{
                              padding: '5px 10px', fontFamily: F, fontSize: FS.xxs, fontWeight: 700,
                              color: T.dim, background: T.surface3, letterSpacing: '0.06em',
                              borderBottom: `1px solid ${T.border}`,
                            }}>
                              {dash.name}
                            </div>
                            {dash.panels.length === 0 ? (
                              <div style={{ padding: '6px 12px', fontFamily: F, fontSize: FS.xxs, color: T.dim, fontStyle: 'italic' }}>
                                No charts in this dashboard
                              </div>
                            ) : (
                              dash.panels.map((panel) => (
                                <button
                                  key={panel.id}
                                  onClick={() => {
                                    if (activeSection) {
                                      insertVizChart(activeSection.id, panel.id, panel.title)
                                      toast.success(`Inserted chart: ${panel.title}`)
                                    }
                                    setImportChartDropdown(false)
                                  }}
                                  style={{
                                    display: 'flex', alignItems: 'center', gap: 8,
                                    width: '100%', padding: '7px 12px', background: 'transparent',
                                    border: 'none', borderBottom: `1px solid ${T.border}`,
                                    cursor: 'pointer', textAlign: 'left',
                                  }}
                                  onMouseEnter={(e) => e.currentTarget.style.background = T.surface4}
                                  onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                                >
                                  <BarChart3 size={10} color={T.cyan} />
                                  <div>
                                    <div style={{ fontFamily: F, fontSize: FS.xs, fontWeight: 600, color: T.text }}>{panel.title}</div>
                                    <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>{panel.chartType} chart</div>
                                  </div>
                                </button>
                              ))
                            )}
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>

                <div style={{ flex: 1 }} />
                <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>
                  MARKDOWN
                </span>
              </div>

              {/* Content editor (block list) */}
              <div
                style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', background: T.bg }}
                onDragOver={handleEditorDragOver}
                onDrop={handleEditorDrop}
              >
                {(!activeSection.blocks || activeSection.blocks.length === 0) && (
                  <div style={{
                    width: '100%', height: 100, border: `2px dashed ${T.border}`, borderRadius: 8,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontFamily: F, fontSize: FS.sm, color: T.dim, marginTop: 10,
                  }}>
                    Drag blocks here from the palette
                  </div>
                )}

                {activeSection.blocks?.map((block, bIdx) => (
                  <motion.div
                    key={block.id}
                    layout
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    onDragOver={(e: any) => handleBlockDragOver(e, bIdx)}
                    onDrop={(e: any) => handleBlockDrop(e, bIdx)}
                    style={{
                      marginBottom: 16,
                      background: T.surface1,
                      border: `1px solid ${T.border}`,
                      borderRadius: 8,
                      overflow: 'hidden',
                      opacity: dragBlockIdx === bIdx ? 0.5 : 1,
                      borderTop: dragBlockOverIdx === bIdx ? `2px solid ${T.cyan}` : `1px solid ${T.border}`,
                      transition: 'border 0.2s ease',
                      position: 'relative',
                    }}
                  >
                    {/* Block Toolbar — ONLY this div is draggable */}
                    <div
                      draggable
                      onDragStart={() => handleBlockDragStart(bIdx)}
                      onDragEnd={handleBlockDragEnd}
                      style={{
                        display: 'flex', alignItems: 'center', padding: '4px 8px',
                        background: T.surface2, borderBottom: `1px solid ${T.borderHi}`,
                        gap: 8, cursor: 'grab',
                      }}
                    >
                      <div style={{ color: T.dim }}><GripVertical size={12} /></div>
                      <span style={{
                        fontFamily: F, fontSize: FS.xs, fontWeight: 700,
                        color: T.dim, textTransform: 'uppercase', letterSpacing: '0.08em'
                      }}>
                        {block.type === 'data_table' ? 'DATA TABLE' : block.type === 'viz_chart' ? 'VIZ CHART' : block.type}
                      </span>
                      {/* Auto-numbering badge */}
                      {autoNumbers[block.id] && (
                        <span style={{
                          fontFamily: F, fontSize: FS.xxs, fontWeight: 700,
                          color: T.cyan, padding: '1px 6px',
                          background: `${T.cyan}12`, border: `1px solid ${T.cyan}30`,
                          borderRadius: 3, letterSpacing: '0.04em',
                        }}>
                          {autoNumbers[block.id]}
                        </span>
                      )}
                      <div style={{ flex: 1 }} />
                      <button
                        onClick={() => removeBlock(activeSection.id, block.id)}
                        style={{
                          background: 'none', border: 'none', cursor: 'pointer',
                          color: T.dim, display: 'flex', padding: 2, borderRadius: 4,
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.color = '#ef4444'; e.currentTarget.style.background = '#ef444420' }}
                        onMouseLeave={(e) => { e.currentTarget.style.color = T.dim; e.currentTarget.style.background = 'transparent' }}
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>

                    {/* Block Content */}
                    <div style={{ padding: 0 }}>
                      {block.type === 'markdown' ? (
                        <textarea
                          ref={(el) => { textareasRef.current[block.id] = el }}
                          value={block.content}
                          onChange={(e) => updateBlock(activeSection.id, block.id, e.target.value)}
                          onFocus={() => setActiveBlockId(block.id)}
                          placeholder="Write markdown text here..."
                          style={{
                            width: '100%', minHeight: 120,
                            background: 'transparent', color: T.text,
                            fontFamily: F, fontSize: FS.md, lineHeight: 1.6,
                            border: 'none', outline: 'none', resize: 'vertical',
                            padding: '12px 14px', boxSizing: 'border-box',
                          }}
                        />
                      ) : block.type === 'chart' ? (
                        <ChartBlock sectionId={activeSection.id} blockId={block.id} chartId={block.content} />
                      ) : block.type === 'table' ? (
                        <TableBlock sectionId={activeSection.id} blockId={block.id} tableId={block.content} />
                      ) : block.type === 'module' ? (
                        <ModuleBlock sectionId={activeSection.id} blockId={block.id} moduleId={block.content} />
                      ) : block.type === 'data_table' ? (
                        <DataTableBlockPreview blockId={block.id} content={block.content} autoNumber={autoNumbers[block.id]} />
                      ) : block.type === 'viz_chart' ? (
                        <VizChartBlockPreview blockId={block.id} content={block.content} autoNumber={autoNumbers[block.id]} />
                      ) : null}
                    </div>
                  </motion.div>
                ))}
              </div>
            </>
          ) : (
            <div style={{
              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: T.bg
            }}>
              <div style={{ textAlign: 'center' }}>
                <FileText size={24} color={T.dim} style={{ marginBottom: 8, opacity: 0.4 }} />
                <div style={{ fontFamily: F, fontSize: FS.sm, color: T.dim }}>
                  Select a section to start editing
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ====== RIGHT: Preview / Tools Panel (350px) ====== */}
        <div
          style={{
            width: 350, minWidth: 350,
            borderLeft: `1px solid ${T.border}`,
            background: T.surface1,
            display: 'flex', flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {/* Panel tabs */}
          <div style={{ display: 'flex', borderBottom: `1px solid ${T.border}` }}>
            {([
              { id: 'preview' as const, label: 'PREVIEW', icon: Eye },
              { id: 'charts' as const, label: 'CHARTS', icon: BarChart3 },
              { id: 'citations' as const, label: 'CITATIONS', icon: BookOpen },
            ]).map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setRightPanel(id)}
                style={{
                  flex: 1, padding: '7px 4px',
                  background: rightPanel === id ? `${T.cyan}08` : 'transparent',
                  border: 'none',
                  borderBottom: rightPanel === id ? `2px solid ${T.cyan}` : '2px solid transparent',
                  color: rightPanel === id ? T.cyan : T.dim,
                  fontFamily: F, fontSize: FS.xxs, fontWeight: 900,
                  letterSpacing: '0.08em', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 3,
                }}
              >
                <Icon size={9} />
                {label}
              </button>
            ))}
          </div>

          {/* Panel content */}
          <div style={{ flex: 1, overflowY: 'auto', padding: 10 }}>
            {rightPanel === 'preview' && (
              <div>
                {/* Toggle: active section vs full document */}
                <div style={{
                  display: 'flex', gap: 4, marginBottom: 10,
                }}>
                  <PreviewToggle
                    activeSection={activeSection}
                    sectionPreviewHtml={previewHtml}
                    fullPreviewHtml={fullPreviewHtml}
                  />
                </div>
              </div>
            )}
            {rightPanel === 'charts' && <ChartBuilder />}
            {rightPanel === 'citations' && <CitationManager />}
          </div>
        </div>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/*  Preview toggle sub-component                                               */
/* -------------------------------------------------------------------------- */

function PreviewToggle({
  activeSection,
  sectionPreviewHtml,
  fullPreviewHtml,
}: {
  activeSection: any
  sectionPreviewHtml: string
  fullPreviewHtml: string
}) {
  const [mode, setMode] = useState<'section' | 'full'>('section')

  return (
    <div style={{ width: '100%' }}>
      <div style={{ display: 'flex', gap: 4, marginBottom: 10 }}>
        <button
          onClick={() => setMode('section')}
          style={{
            padding: '3px 8px',
            background: mode === 'section' ? `${T.cyan}20` : T.surface3,
            border: `1px solid ${mode === 'section' ? T.cyan + '50' : T.border}`,
            color: mode === 'section' ? T.cyan : T.dim,
            fontFamily: F, fontSize: FS.xxs, fontWeight: 900,
            letterSpacing: '0.08em', cursor: 'pointer',
          }}
        >
          SECTION
        </button>
        <button
          onClick={() => setMode('full')}
          style={{
            padding: '3px 8px',
            background: mode === 'full' ? `${T.cyan}20` : T.surface3,
            border: `1px solid ${mode === 'full' ? T.cyan + '50' : T.border}`,
            color: mode === 'full' ? T.cyan : T.dim,
            fontFamily: F, fontSize: FS.xxs, fontWeight: 900,
            letterSpacing: '0.08em', cursor: 'pointer',
          }}
        >
          FULL DOCUMENT
        </button>
      </div>

      {mode === 'section' ? (
        activeSection ? (
          <div>
            <div style={{
              fontFamily: FD, fontSize: FS.xl, fontWeight: 700,
              color: T.text, marginBottom: 8, letterSpacing: '0.04em',
            }}>
              {activeSection.title}
            </div>
            {sectionPreviewHtml ? (
              <div
                style={{
                  fontFamily: F, fontSize: FS.sm, color: T.sec,
                  lineHeight: 1.8, wordBreak: 'break-word',
                }}
                dangerouslySetInnerHTML={{ __html: sectionPreviewHtml }}
              />
            ) : (
              <div style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, fontStyle: 'italic' }}>
                Start writing to see a preview...
              </div>
            )}
          </div>
        ) : (
          <div style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, textAlign: 'center', padding: 20 }}>
            Select a section to preview
          </div>
        )
      ) : (
        <div
          style={{
            fontFamily: F, fontSize: FS.sm, color: T.sec,
            lineHeight: 1.8, wordBreak: 'break-word',
          }}
          dangerouslySetInnerHTML={{ __html: fullPreviewHtml }}
        />
      )}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/*  Data Table block preview                                                    */
/* -------------------------------------------------------------------------- */

function DataTableBlockPreview({ content, autoNumber }: { blockId: string; content: string; autoNumber?: string }) {
  const tables = useDataStore((s) => s.tables)

  let tableId = ''
  let caption = ''
  try {
    const parsed = JSON.parse(content)
    tableId = parsed.tableId || ''
    caption = parsed.caption || ''
  } catch {
    tableId = content
  }

  const table = tables.find((t) => t.id === tableId)

  return (
    <div style={{ padding: 14 }}>
      {autoNumber && (
        <div style={{
          fontFamily: F, fontSize: FS.xxs, fontWeight: 700, color: T.cyan,
          letterSpacing: '0.06em', marginBottom: 6,
        }}>
          {autoNumber}
        </div>
      )}
      {table ? (
        <div>
          <div style={{
            fontFamily: FD, fontSize: FS.sm, fontWeight: 700, color: T.text, marginBottom: 8,
          }}>
            {caption || table.name}
          </div>
          <div style={{
            background: T.surface0, border: `1px solid ${T.border}`, borderRadius: 4,
            overflow: 'auto', maxHeight: 200,
          }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  {table.columns.map((col) => (
                    <th key={col.id} style={{
                      fontFamily: F, fontSize: FS.xxs, fontWeight: 700, color: T.dim,
                      letterSpacing: '0.06em', textTransform: 'uppercase' as const,
                      padding: '5px 8px', borderBottom: `1px solid ${T.border}`,
                      textAlign: 'left', background: T.surface2,
                    }}>
                      {col.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.slice(0, 8).map((row, ri) => (
                  <tr key={ri}>
                    {table.columns.map((col) => (
                      <td key={col.id} style={{
                        fontFamily: F, fontSize: FS.xxs, color: T.sec,
                        padding: '4px 8px', borderBottom: `1px solid ${T.border}`,
                      }}>
                        {String(row[col.id] ?? '')}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {table.rows.length > 8 && (
              <div style={{
                padding: '4px 8px', fontFamily: F, fontSize: FS.xxs, color: T.dim,
                fontStyle: 'italic', borderTop: `1px solid ${T.border}`,
              }}>
                ... and {table.rows.length - 8} more rows
              </div>
            )}
          </div>
        </div>
      ) : (
        <div style={{
          padding: 16, textAlign: 'center', fontFamily: F, fontSize: FS.sm,
          color: T.dim, background: T.surface0, border: `1px dashed ${T.border}`,
          borderRadius: 4,
        }}>
          Data table not found (ID: {tableId || 'none'})
        </div>
      )}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/*  Viz Chart block preview                                                     */
/* -------------------------------------------------------------------------- */

function VizChartBlockPreview({ content, autoNumber }: { blockId: string; content: string; autoNumber?: string }) {
  const dashboards = useVizStore((s) => s.dashboards)

  let chartId = ''
  let caption = ''
  try {
    const parsed = JSON.parse(content)
    chartId = parsed.chartId || ''
    caption = parsed.caption || ''
  } catch {
    chartId = content
  }

  // Search across all dashboards for the panel
  let panel = null
  for (const dash of dashboards) {
    const found = dash.panels.find((p) => p.id === chartId)
    if (found) { panel = found; break }
  }

  return (
    <div style={{ padding: 14 }}>
      {autoNumber && (
        <div style={{
          fontFamily: F, fontSize: FS.xxs, fontWeight: 700, color: T.cyan,
          letterSpacing: '0.06em', marginBottom: 6,
        }}>
          {autoNumber}
        </div>
      )}
      {panel ? (
        <div>
          <div style={{
            fontFamily: FD, fontSize: FS.sm, fontWeight: 700, color: T.text, marginBottom: 8,
          }}>
            {caption || panel.title}
          </div>
          <div style={{
            padding: 12, background: T.surface0, border: `1px solid ${T.border}`,
            borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center',
            gap: 8, minHeight: 60,
          }}>
            <BarChart3 size={16} color={T.cyan} />
            <div>
              <div style={{ fontFamily: F, fontSize: FS.xs, color: T.text, fontWeight: 600 }}>
                {panel.title}
              </div>
              <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                {panel.chartType} chart -- {panel.xField} vs {panel.yField}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div style={{
          padding: 16, textAlign: 'center', fontFamily: F, fontSize: FS.sm,
          color: T.dim, background: T.surface0, border: `1px dashed ${T.border}`,
          borderRadius: 4,
        }}>
          Chart not found (ID: {chartId || 'none'})
        </div>
      )}
    </div>
  )
}
