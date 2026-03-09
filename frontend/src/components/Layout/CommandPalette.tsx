import { useState, useEffect, useRef } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { useGuideStore } from '@/stores/guideStore'
import {
  LayoutDashboard,
  GitBranch,
  BarChart3,
  Database,
  Blocks,
  BookOpen,
  PanelLeftClose,
  Plus,
  Undo2,
  Redo2,
} from 'lucide-react'
import { BLOCK_REGISTRY } from '@/lib/block-registry'
import { usePipelineStore } from '@/stores/pipelineStore'

interface Command {
  id: string
  label: string
  category: string
  icon: React.ReactNode
  action: () => void
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const setView = useUIStore((s) => s.setView)
  const toggleSidebar = useUIStore((s) => s.toggleSidebar)
  const toggleGuide = useGuideStore((s) => s.toggleGuide)

  const navCommands: Command[] = [
    { id: 'nav-dashboard', label: 'Go to Dashboard', category: 'Navigation', icon: <LayoutDashboard size={12} />, action: () => setView('dashboard') },
    { id: 'nav-editor', label: 'Go to Pipeline Editor', category: 'Navigation', icon: <GitBranch size={12} />, action: () => setView('editor') },
    { id: 'nav-results', label: 'Go to Results', category: 'Navigation', icon: <BarChart3 size={12} />, action: () => setView('results') },
    { id: 'nav-datasets', label: 'Go to Datasets', category: 'Navigation', icon: <Database size={12} />, action: () => setView('datasets') },
    { id: 'nav-marketplace', label: 'Go to Blocks', category: 'Navigation', icon: <Blocks size={12} />, action: () => setView('marketplace') },
    { id: 'toggle-guide', label: 'Toggle Guide', category: 'Actions', icon: <BookOpen size={12} />, action: () => toggleGuide() },
    { id: 'toggle-sidebar', label: 'Toggle Sidebar', category: 'Actions', icon: <PanelLeftClose size={12} />, action: () => toggleSidebar() },
    { id: 'action-undo', label: 'Undo', category: 'Actions', icon: <Undo2 size={12} />, action: () => usePipelineStore.getState().undo() },
    { id: 'action-redo', label: 'Redo', category: 'Actions', icon: <Redo2 size={12} />, action: () => usePipelineStore.getState().redo() },
  ]

  const blockCommands: Command[] = BLOCK_REGISTRY.map((block) => ({
    id: `add-${block.type}`,
    label: `Add ${block.name}`,
    category: 'Blocks',
    icon: <Plus size={12} />,
    action: () => {
      setView('editor')
      setTimeout(() => usePipelineStore.getState().addNode(block.type, { x: 400, y: 300 }), 100)
    },
  }))

  const commands: Command[] = [...navCommands, ...blockCommands]

  const filtered = search
    ? commands.filter((c) => c.label.toLowerCase().includes(search.toLowerCase()))
    : commands

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen((o) => !o)
        setSearch('')
        setSelectedIndex(0)
      }
      if (e.key === 'Escape' && open) {
        setOpen(false)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  useEffect(() => {
    setSelectedIndex(0)
  }, [search])

  const execute = (cmd: Command) => {
    cmd.action()
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
        position: 'fixed',
        inset: 0,
        zIndex: 10000,
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        paddingTop: 120,
        background: T.shadowHeavy,
      }}
      onClick={() => setOpen(false)}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 440,
          background: T.surface2,
          border: `1px solid ${T.borderHi}`,
          boxShadow: `0 16px 48px ${T.shadowHeavy}`,
          overflow: 'hidden',
        }}
      >
        {/* Search input */}
        <div style={{ padding: '10px 12px', borderBottom: `1px solid ${T.border}` }}>
          <input
            ref={inputRef}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Type a command..."
            style={{
              width: '100%',
              background: 'none',
              border: 'none',
              outline: 'none',
              color: T.text,
              fontFamily: F,
              fontSize: FS.lg,
              letterSpacing: '0.02em',
            }}
          />
        </div>

        {/* Results */}
        <div style={{ maxHeight: 300, overflow: 'auto', padding: '4px 0' }}>
          {filtered.map((cmd, i) => (
            <div
              key={cmd.id}
              onClick={() => execute(cmd)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '7px 12px',
                background: i === selectedIndex ? `${T.cyan}12` : 'transparent',
                borderLeft: i === selectedIndex ? `2px solid ${T.cyan}` : '2px solid transparent',
                cursor: 'pointer',
                transition: 'background 0.1s',
              }}
              onMouseEnter={() => setSelectedIndex(i)}
            >
              <span style={{ color: i === selectedIndex ? T.cyan : T.dim, flexShrink: 0 }}>
                {cmd.icon}
              </span>
              <span
                style={{
                  fontFamily: F,
                  fontSize: FS.sm,
                  color: i === selectedIndex ? T.text : T.sec,
                  fontWeight: i === selectedIndex ? 700 : 400,
                }}
              >
                {cmd.label}
              </span>
              <span
                style={{
                  marginLeft: 'auto',
                  fontFamily: F,
                  fontSize: FS.xxs,
                  color: T.dim,
                  letterSpacing: '0.08em',
                }}
              >
                {cmd.category}
              </span>
            </div>
          ))}
          {filtered.length === 0 && (
            <div style={{ padding: '16px 12px', textAlign: 'center' }}>
              <span style={{ fontFamily: F, fontSize: FS.sm, color: T.dim }}>No commands found</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '6px 12px',
            borderTop: `1px solid ${T.border}`,
            display: 'flex',
            gap: 12,
          }}
        >
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
            {'\u2191\u2193'} navigate
          </span>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
            {'\u23CE'} select
          </span>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
            esc close
          </span>
        </div>
      </div>
    </div>
  )
}
