import { useState, useEffect, useRef, useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { useProjectStore } from '@/stores/projectStore'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useGuideStore } from '@/stores/guideStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { DEMO_RUNS } from '@/lib/demo-data'
import {
  FileText, GitBranch, Play, LayoutDashboard, BarChart3,
  Database, Blocks, BookOpen, PanelLeftClose, Activity,
  Settings, Wrench, MessageSquare, LineChart,
} from 'lucide-react'

interface PaletteItem {
  id: string
  label: string
  subtitle?: string
  category: 'Project' | 'Pipeline' | 'Run' | 'Navigation' | 'Action'
  icon: React.ReactNode
  action: () => void
  /** Searchable text beyond label */
  searchText: string
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const setView = useUIStore((s) => s.setView)
  const navigateToMonitor = useUIStore((s) => s.navigateToMonitor)
  const navigateToPaperDetail = useUIStore((s) => s.navigateToPaperDetail)
  const toggleSidebar = useUIStore((s) => s.toggleSidebar)
  const toggleGuide = useGuideStore((s) => s.toggleGuide)

  const projects = useProjectStore((s) => s.projects)
  const pipelines = usePipelineStore((s) => s.pipelines)
  const loadPipeline = usePipelineStore((s) => s.loadPipeline)
  const demoMode = useSettingsStore((s) => s.demoMode)
  const features = useSettingsStore((s) => s.features)

  // Build items list
  const items = useMemo(() => {
    const result: PaletteItem[] = []

    // Navigation commands
    const navItems: { id: string; label: string; view: Parameters<typeof setView>[0]; icon: React.ReactNode }[] = [
      { id: 'nav-dashboard', label: 'Go to Dashboard', view: 'dashboard', icon: <LayoutDashboard size={14} /> },
      { id: 'nav-editor', label: 'Go to Pipeline Editor', view: 'editor', icon: <GitBranch size={14} /> },
      { id: 'nav-monitor', label: 'Go to Monitor', view: 'monitor', icon: <Activity size={14} /> },
      { id: 'nav-results', label: 'Go to Results', view: 'results', icon: <BarChart3 size={14} /> },
      { id: 'nav-datasets', label: 'Go to Datasets', view: 'datasets', icon: <Database size={14} /> },
      { id: 'nav-blocks', label: 'Go to Blocks', view: 'marketplace', icon: <Blocks size={14} /> },
      { id: 'nav-paper', label: 'Go to Paper', view: 'paper', icon: <FileText size={14} /> },
      { id: 'nav-settings', label: 'Go to Settings', view: 'settings', icon: <Settings size={14} /> },
      { id: 'nav-workshop', label: 'Go to Workshop', view: 'workshop', icon: <Wrench size={14} /> },
      { id: 'nav-inference', label: 'Go to Inference', view: 'inference', icon: <MessageSquare size={14} /> },
      { id: 'nav-charts', label: 'Go to Charts', view: 'visualization', icon: <LineChart size={14} /> },
    ]
    navItems
      .filter(({ view }) => view !== 'marketplace' || features?.marketplace)
      .forEach(({ id, label, view, icon }) => {
        result.push({
          id, label, category: 'Navigation', icon,
          action: () => setView(view),
          searchText: label,
        })
      })

    // Actions
    result.push({
      id: 'action-guide', label: 'Toggle Guide', category: 'Action',
      icon: <BookOpen size={14} />, action: toggleGuide, searchText: 'toggle guide help',
    })
    result.push({
      id: 'action-sidebar', label: 'Toggle Sidebar', category: 'Action',
      icon: <PanelLeftClose size={14} />, action: toggleSidebar, searchText: 'toggle sidebar collapse',
    })

    // Projects
    projects.forEach((p) => {
      result.push({
        id: `project-${p.id}`,
        label: p.name,
        subtitle: [p.paper_number, p.status].filter(Boolean).join(' · '),
        category: 'Project',
        icon: <FileText size={14} />,
        action: () => navigateToPaperDetail(p.id),
        searchText: `${p.name} ${p.paper_number || ''} ${p.status} ${p.description || ''}`.toLowerCase(),
      })
    })

    // Pipelines
    pipelines.forEach((p) => {
      result.push({
        id: `pipeline-${p.id}`,
        label: p.name,
        subtitle: `${p.block_count} blocks`,
        category: 'Pipeline',
        icon: <GitBranch size={14} />,
        action: () => {
          loadPipeline(p.id)
          setView('editor')
        },
        searchText: `${p.name} pipeline`.toLowerCase(),
      })
    })

    // Recent runs
    if (demoMode) {
      DEMO_RUNS.forEach((r) => {
        result.push({
          id: `run-${r.id}`,
          label: `Run ${r.id}`,
          subtitle: `${r.status} · ${new Date(r.started_at).toLocaleDateString()}`,
          category: 'Run',
          icon: <Play size={14} />,
          action: () => navigateToMonitor(r.id),
          searchText: `${r.id} ${r.status} run`.toLowerCase(),
        })
      })
    }

    return result
  }, [projects, pipelines, demoMode, features, setView, navigateToMonitor, navigateToPaperDetail, loadPipeline, toggleGuide, toggleSidebar])

  // Filter
  const filtered = useMemo(() => {
    if (!search) return items.slice(0, 8)
    const q = search.toLowerCase()
    return items
      .filter((item) =>
        item.label.toLowerCase().includes(q) ||
        (item.subtitle?.toLowerCase().includes(q)) ||
        item.searchText.includes(q)
      )
      .slice(0, 8)
  }, [items, search])

  // Keyboard: Cmd+K to open, Escape to close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen((o) => !o)
        setSearch('')
        setSelectedIndex(0)
      }
      if (e.key === 'Escape' && open) {
        e.preventDefault()
        setOpen(false)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open])

  // Focus input when opened
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50)
  }, [open])

  // Reset selection on search change
  useEffect(() => {
    setSelectedIndex(0)
  }, [search])

  // Scroll selected item into view
  useEffect(() => {
    if (listRef.current) {
      const el = listRef.current.children[selectedIndex] as HTMLElement
      if (el) el.scrollIntoView({ block: 'nearest' })
    }
  }, [selectedIndex])

  const execute = (item: PaletteItem) => {
    item.action()
    setOpen(false)
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && filtered[selectedIndex]) {
      e.preventDefault()
      execute(filtered[selectedIndex])
    }
  }

  if (!open) return null

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 10000,
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        paddingTop: 100, background: T.shadowHeavy,
      }}
      onClick={() => setOpen(false)}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 600, maxHeight: 400,
          background: T.surface2, border: `1px solid ${T.borderHi}`,
          boxShadow: `0 16px 48px ${T.shadowHeavy}`,
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}
      >
        {/* Search input */}
        <div style={{ padding: '12px 16px', borderBottom: `1px solid ${T.border}` }}>
          <input
            ref={inputRef}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search projects, pipelines, runs, or type a command..."
            style={{
              width: '100%', background: 'none', border: 'none', outline: 'none',
              color: T.text, fontFamily: F, fontSize: FS.lg, letterSpacing: '0.02em',
            }}
          />
        </div>

        {/* Results */}
        <div ref={listRef} style={{ flex: 1, overflow: 'auto', padding: '4px 0' }}>
          {filtered.map((item, i) => (
            <div
              key={item.id}
              onClick={() => execute(item)}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '8px 16px',
                background: i === selectedIndex ? `${T.cyan}12` : 'transparent',
                borderLeft: i === selectedIndex ? `2px solid ${T.cyan}` : '2px solid transparent',
                cursor: 'pointer', transition: 'background 0.1s',
              }}
              onMouseEnter={() => setSelectedIndex(i)}
            >
              {/* Icon */}
              <span style={{ color: i === selectedIndex ? T.cyan : T.dim, flexShrink: 0 }}>
                {item.icon}
              </span>

              {/* Title + Subtitle */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontFamily: F, fontSize: FS.sm,
                  color: i === selectedIndex ? T.text : T.sec,
                  fontWeight: i === selectedIndex ? 700 : 400,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {item.label}
                </div>
                {item.subtitle && (
                  <div style={{
                    fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 1,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {item.subtitle}
                  </div>
                )}
              </div>

              {/* Category badge */}
              <span style={{
                fontFamily: F, fontSize: FS.xxs, color: T.dim,
                letterSpacing: '0.08em', flexShrink: 0,
              }}>
                {item.category}
              </span>
            </div>
          ))}
          {filtered.length === 0 && (
            <div style={{ padding: '20px 16px', textAlign: 'center' }}>
              <span style={{ fontFamily: F, fontSize: FS.sm, color: T.dim }}>No results found</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: '6px 16px', borderTop: `1px solid ${T.border}`,
          display: 'flex', gap: 16,
        }}>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>{'\u2191\u2193'} navigate</span>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>{'\u23CE'} select</span>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>esc close</span>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginLeft: 'auto' }}>
            {filtered.length} result{filtered.length !== 1 ? 's' : ''}
          </span>
        </div>
      </div>
    </div>
  )
}
