import { useState, useRef, useEffect } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { usePipelineStore, type PipelineTab } from '@/stores/pipelineStore'
import { useShallow } from 'zustand/react/shallow'
import { Plus, X, Copy, Pencil, Loader2, CheckCircle2, XCircle } from 'lucide-react'

const STATUS_COLORS: Record<PipelineTab['runStatus'], string> = {
  idle: T.dim,
  running: T.cyan,
  complete: T.green,
  failed: T.red,
}

export default function PipelineTabBar() {
  const { tabs, activeTabId } = usePipelineStore(useShallow((s) => ({
    tabs: s.tabs,
    activeTabId: s.activeTabId,
  })))
  const addTab = usePipelineStore((s) => s.addTab)
  const removeTab = usePipelineStore((s) => s.removeTab)
  const switchTab = usePipelineStore((s) => s.switchTab)
  const renameTab = usePipelineStore((s) => s.renameTab)
  const duplicateTab = usePipelineStore((s) => s.duplicateTab)

  const [editingTabId, setEditingTabId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [contextMenu, setContextMenu] = useState<{ tabId: string; x: number; y: number } | null>(null)
  const editInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editingTabId && editInputRef.current) {
      editInputRef.current.focus()
      editInputRef.current.select()
    }
  }, [editingTabId])

  // Close context menu on outside click
  useEffect(() => {
    if (!contextMenu) return
    const handler = () => setContextMenu(null)
    window.addEventListener('click', handler)
    return () => window.removeEventListener('click', handler)
  }, [contextMenu])

  const handleStartRename = (tabId: string) => {
    const tab = tabs.find((t) => t.id === tabId)
    if (!tab) return
    setEditingTabId(tabId)
    setEditValue(tab.name)
    setContextMenu(null)
  }

  const handleFinishRename = () => {
    if (editingTabId && editValue.trim()) {
      renameTab(editingTabId, editValue.trim())
    }
    setEditingTabId(null)
  }

  const handleContextMenu = (e: React.MouseEvent, tabId: string) => {
    e.preventDefault()
    setContextMenu({ tabId, x: e.clientX, y: e.clientY })
  }

  const StatusIcon = ({ status }: { status: PipelineTab['runStatus'] }) => {
    if (status === 'running') return <Loader2 size={8} color={T.cyan} style={{ animation: 'spin 1s linear infinite' }} />
    if (status === 'complete') return <CheckCircle2 size={8} color={T.green} />
    if (status === 'failed') return <XCircle size={8} color={T.red} />
    return null
  }

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        height: 28,
        background: T.surface1,
        borderBottom: `1px solid ${T.border}`,
        paddingLeft: 4,
        paddingRight: 4,
        gap: 1,
        flexShrink: 0,
        overflowX: 'auto',
        overflowY: 'hidden',
      }}
    >
      {tabs.map((tab) => {
        const isActive = tab.id === activeTabId
        const isEditing = editingTabId === tab.id
        const statusColor = STATUS_COLORS[tab.runStatus]

        return (
          <div
            key={tab.id}
            onClick={() => !isEditing && switchTab(tab.id)}
            onContextMenu={(e) => handleContextMenu(e, tab.id)}
            onDoubleClick={() => handleStartRename(tab.id)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              padding: '0 8px',
              height: 24,
              background: isActive ? T.surface3 : 'transparent',
              borderTop: isActive ? `2px solid ${statusColor}` : '2px solid transparent',
              borderLeft: `1px solid ${isActive ? T.border : 'transparent'}`,
              borderRight: `1px solid ${isActive ? T.border : 'transparent'}`,
              cursor: 'pointer',
              transition: 'all 0.1s',
              flexShrink: 0,
              ...(tab.runStatus === 'running' && isActive ? {
                boxShadow: `inset 0 2px 0 ${T.cyan}`,
              } : {}),
            }}
            onMouseEnter={(e) => {
              if (!isActive) e.currentTarget.style.background = T.surface2
            }}
            onMouseLeave={(e) => {
              if (!isActive) e.currentTarget.style.background = 'transparent'
            }}
          >
            <StatusIcon status={tab.runStatus} />

            {isEditing ? (
              <input
                ref={editInputRef}
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onBlur={handleFinishRename}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleFinishRename()
                  if (e.key === 'Escape') setEditingTabId(null)
                }}
                style={{
                  background: T.surface4,
                  border: `1px solid ${T.cyan}`,
                  color: T.text,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  padding: '1px 4px',
                  width: 100,
                  outline: 'none',
                }}
              />
            ) : (
              <span
                style={{
                  fontFamily: F,
                  fontSize: FS.xxs,
                  color: isActive ? T.text : T.dim,
                  fontWeight: isActive ? 600 : 400,
                  letterSpacing: '0.04em',
                  maxWidth: 120,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {tab.name}
              </span>
            )}

            {tab.isDirty && !isEditing && (
              <span style={{ color: T.amber, fontSize: 8, lineHeight: 1 }}>●</span>
            )}

            {tabs.length > 1 && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  removeTab(tab.id)
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  color: T.dim,
                  cursor: 'pointer',
                  padding: 1,
                  display: 'flex',
                  opacity: 0.6,
                }}
                onMouseEnter={(e) => { e.currentTarget.style.opacity = '1'; e.currentTarget.style.color = T.red }}
                onMouseLeave={(e) => { e.currentTarget.style.opacity = '0.6'; e.currentTarget.style.color = T.dim }}
              >
                <X size={8} />
              </button>
            )}
          </div>
        )
      })}

      {/* Add tab button */}
      <button
        onClick={() => addTab()}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 22,
          height: 22,
          background: 'none',
          border: `1px solid transparent`,
          color: T.dim,
          cursor: 'pointer',
          flexShrink: 0,
          marginLeft: 2,
          transition: 'all 0.1s',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = T.surface3
          e.currentTarget.style.borderColor = T.border
          e.currentTarget.style.color = T.sec
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = 'none'
          e.currentTarget.style.borderColor = 'transparent'
          e.currentTarget.style.color = T.dim
        }}
        title="New pipeline tab"
      >
        <Plus size={10} />
      </button>

      {/* Context menu */}
      {contextMenu && (
        <div
          style={{
            position: 'fixed',
            left: contextMenu.x,
            top: contextMenu.y,
            background: T.surface2,
            border: `1px solid ${T.borderHi}`,
            boxShadow: `0 4px 12px ${T.shadow}`,
            zIndex: 999,
            minWidth: 140,
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <ContextMenuItem
            icon={<Pencil size={10} />}
            label="Rename"
            onClick={() => handleStartRename(contextMenu.tabId)}
          />
          <ContextMenuItem
            icon={<Copy size={10} />}
            label="Duplicate"
            onClick={() => { duplicateTab(contextMenu.tabId); setContextMenu(null) }}
          />
          {tabs.length > 1 && (
            <ContextMenuItem
              icon={<X size={10} />}
              label="Close"
              color={T.red}
              onClick={() => { removeTab(contextMenu.tabId); setContextMenu(null) }}
            />
          )}
        </div>
      )}
    </div>
  )
}

function ContextMenuItem({ icon, label, onClick, color }: {
  icon: React.ReactNode
  label: string
  onClick: () => void
  color?: string
}) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        width: '100%',
        padding: '6px 12px',
        background: 'none',
        border: 'none',
        color: color || T.sec,
        fontFamily: F,
        fontSize: FS.xs,
        cursor: 'pointer',
        textAlign: 'left',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = T.surface4 }}
      onMouseLeave={(e) => { e.currentTarget.style.background = 'none' }}
    >
      {icon}
      {label}
    </button>
  )
}
