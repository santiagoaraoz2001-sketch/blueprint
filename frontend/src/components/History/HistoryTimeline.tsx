import { useMemo, useCallback } from 'react'
import { T, F, FS, DEPTH } from '@/lib/design-tokens'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useShallow } from 'zustand/react/shallow'
import type { HistoryEntry } from '@/lib/history'
import {
  Plus, Minus, Move, Settings, Link, Unlink,
  Layers, Pencil, X, History, ChevronRight,
} from 'lucide-react'

const ICON_MAP: Record<HistoryEntry['type'], React.ReactNode> = {
  add: <Plus size={12} />,
  remove: <Minus size={12} />,
  move: <Move size={12} />,
  config: <Settings size={12} />,
  connect: <Link size={12} />,
  disconnect: <Unlink size={12} />,
  bulk: <Layers size={12} />,
  unknown: <Pencil size={12} />,
}

const COLOR_MAP: Record<HistoryEntry['type'], string> = {
  add: '#3EF07A',
  remove: '#FF5E72',
  move: '#5B96FF',
  config: '#FFBE45',
  connect: '#2FFCC8',
  disconnect: '#FF8C4A',
  bulk: '#A87EFF',
  unknown: '#7A8799',
}

function relativeTime(timestamp: string): string {
  const now = Date.now()
  const then = new Date(timestamp).getTime()
  const diffSec = Math.floor((now - then) / 1000)

  if (diffSec < 5) return 'just now'
  if (diffSec < 60) return `${diffSec}s ago`
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour}h ago`
  return `${Math.floor(diffHour / 24)}d ago`
}

interface Props {
  visible: boolean
  onClose: () => void
}

export default function HistoryTimeline({ visible, onClose }: Props) {
  const { past, future } = usePipelineStore(useShallow((s) => ({
    past: s.past,
    future: s.future,
  })))
  const undo = usePipelineStore((s) => s.undo)

  // Build timeline: past entries (oldest to newest) + "Current" marker + future entries
  const entries = useMemo(() => {
    const items: {
      entry: HistoryEntry | null
      isCurrent: boolean
      stepsBack: number
    }[] = []

    // Past entries (most recent first)
    for (let i = past.length - 1; i >= 0; i--) {
      items.push({
        entry: past[i],
        isCurrent: false,
        stepsBack: past.length - i,
      })
    }

    return items
  }, [past])

  const handleJump = useCallback((stepsBack: number) => {
    // Apply sequential undos to reach the target state
    for (let i = 0; i < stepsBack; i++) {
      undo()
    }
  }, [undo])

  if (!visible) return null

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        right: 0,
        bottom: 0,
        width: 280,
        background: T.surface1,
        borderLeft: `1px solid ${T.border}`,
        boxShadow: DEPTH.card,
        display: 'flex',
        flexDirection: 'column',
        zIndex: 50,
      }}
    >
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '10px 12px',
        borderBottom: `1px solid ${T.border}`,
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <History size={14} color={T.cyan} />
          <span style={{
            fontFamily: F,
            fontSize: FS.sm,
            fontWeight: 700,
            color: T.text,
            letterSpacing: '0.06em',
          }}>
            HISTORY
          </span>
          <span style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.dim,
          }}>
            {past.length} entries
          </span>
        </div>
        <button
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            color: T.dim,
            cursor: 'pointer',
            padding: 2,
            display: 'flex',
          }}
        >
          <X size={14} />
        </button>
      </div>

      {/* Timeline */}
      <div style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
        {/* Current state marker */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '6px 12px',
          borderLeft: `2px solid ${T.cyan}`,
          background: `${T.cyan}08`,
        }}>
          <ChevronRight size={12} color={T.cyan} />
          <span style={{
            fontFamily: F,
            fontSize: FS.sm,
            fontWeight: 700,
            color: T.cyan,
          }}>
            Current State
          </span>
          {future.length > 0 && (
            <span style={{
              fontFamily: F,
              fontSize: FS.xxs,
              color: T.dim,
              marginLeft: 'auto',
            }}>
              {future.length} redo{future.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>

        {/* Past entries (most recent first) */}
        {entries.map((item, i) => {
          const e = item.entry!
          const iconColor = COLOR_MAP[e.type] || T.dim
          return (
            <div
              key={`past-${i}`}
              onClick={() => handleJump(item.stepsBack)}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 8,
                padding: '6px 12px',
                borderLeft: '2px solid transparent',
                cursor: 'pointer',
                transition: 'background 0.1s',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = T.surface3 }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
            >
              {/* Timeline dot + line */}
              <div style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                flexShrink: 0,
                paddingTop: 2,
              }}>
                <div style={{
                  width: 22,
                  height: 22,
                  borderRadius: '50%',
                  background: `${iconColor}18`,
                  border: `1px solid ${iconColor}40`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: iconColor,
                }}>
                  {ICON_MAP[e.type]}
                </div>
                {i < entries.length - 1 && (
                  <div style={{
                    width: 1,
                    height: 12,
                    background: T.border,
                    marginTop: 2,
                  }} />
                )}
              </div>

              {/* Content */}
              <div style={{ flex: 1, minWidth: 0, paddingTop: 2 }}>
                <div style={{
                  fontFamily: F,
                  fontSize: FS.sm,
                  color: T.sec,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}>
                  {e.description}
                </div>
                <div style={{
                  fontFamily: F,
                  fontSize: FS.xxs,
                  color: T.dim,
                  marginTop: 1,
                }}>
                  {relativeTime(e.timestamp)}
                </div>
              </div>
            </div>
          )
        })}

        {entries.length === 0 && (
          <div style={{
            padding: '24px 12px',
            textAlign: 'center',
          }}>
            <span style={{ fontFamily: F, fontSize: FS.sm, color: T.dim }}>
              No history yet. Start editing to build history.
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
