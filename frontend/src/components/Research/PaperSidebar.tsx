import { T, F, FS } from '@/lib/design-tokens'
import type { Project } from '@/stores/projectStore'
import PaperBadge, { PAPER_STATUS_COLORS } from './PaperBadge'
import { Plus, FileJson } from 'lucide-react'

interface PaperSidebarProps {
  projects: Project[]
  onSelect: (id: string) => void
  onAdd: () => void
  onImport?: () => void
}

const STATUS_ORDER: Record<string, number> = {
  active: 0,
  blocked: 1,
  analyzing: 2,
  writing: 3,
  queued: 4,
  planned: 5,
  complete: 6,
}

export default function PaperSidebar({ projects, onSelect, onAdd, onImport }: PaperSidebarProps) {
  const sorted = [...projects].sort((a, b) => {
    const aOrder = STATUS_ORDER[a.status] ?? 5
    const bOrder = STATUS_ORDER[b.status] ?? 5
    return aOrder - bOrder
  })

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        background: T.surface1,
        border: `1px solid ${T.border}`,
        height: '100%',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          padding: '10px 12px',
          borderBottom: `1px solid ${T.border}`,
          fontFamily: F,
          fontSize: FS.xxs,
          color: T.dim,
          letterSpacing: '0.14em',
          textTransform: 'uppercase',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        Papers
        <span style={{ color: T.sec, fontWeight: 600 }}>{projects.length}</span>
      </div>

      <div style={{ flex: 1, overflow: 'auto' }}>
        {sorted.map((project) => {
          const color = PAPER_STATUS_COLORS[project.status] || '#64748B'
          return (
            <div
              key={project.id}
              onClick={() => onSelect(project.id)}
              style={{
                padding: '8px 12px',
                borderBottom: `1px solid ${T.border}`,
                cursor: 'pointer',
                transition: 'background 0.15s',
                display: 'flex',
                flexDirection: 'column',
                gap: 4,
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = T.surface2 }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <PaperBadge paperNumber={project.paper_number ?? null} status={project.status} />
                <span
                  style={{
                    fontFamily: F,
                    fontSize: FS.sm,
                    color: T.text,
                    flex: 1,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {project.name}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span
                  style={{
                    fontFamily: F,
                    fontSize: FS.xxs,
                    color,
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                  }}
                >
                  {project.status}
                </span>
              </div>
            </div>
          )
        })}
      </div>

      <div style={{ display: 'flex', borderTop: `1px solid ${T.border}` }}>
        <button
          onClick={onAdd}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            padding: '10px 12px',
            background: 'transparent',
            border: 'none',
            color: T.cyan,
            fontFamily: F,
            fontSize: FS.xs,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            cursor: 'pointer',
            transition: 'background 0.15s',
            flex: 1,
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = `${T.cyan}08` }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
        >
          <Plus size={12} />
          Add Paper
        </button>
        {onImport && (
          <button
            onClick={onImport}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
              padding: '10px 12px',
              background: 'transparent',
              border: 'none',
              borderLeft: `1px solid ${T.border}`,
              color: T.sec,
              fontFamily: F,
              fontSize: FS.xs,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              cursor: 'pointer',
              transition: 'background 0.15s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = `${T.cyan}08`; e.currentTarget.style.color = T.cyan }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = T.sec }}
          >
            <FileJson size={12} />
            Import
          </button>
        )}
      </div>
    </div>
  )
}
