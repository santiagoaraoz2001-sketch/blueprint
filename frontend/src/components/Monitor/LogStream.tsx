import { useEffect, useRef, useState, useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore, type LogEntry } from '@/stores/metricsStore'
import { Pin, PinOff, Search } from 'lucide-react'

const EMPTY_LOGS: LogEntry[] = []

interface LogStreamProps {
  runId: string
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map((n) => String(n).padStart(2, '0'))
    .join(':')
}

function levelColor(level: string): string {
  switch (level) {
    case 'error': return 'rgba(255,67,61,0.12)'
    case 'warn': return 'rgba(245,158,11,0.08)'
    default: return 'transparent'
  }
}

function levelTextColor(level: string): string {
  switch (level) {
    case 'error': return '#ff433d'
    case 'warn': return '#f59e0b'
    default: return T.sec
  }
}

export default function LogStream({ runId }: LogStreamProps) {
  const logs = useMetricsStore((s) => s.runs[runId]?.logs ?? EMPTY_LOGS)
  const [pinned, setPinned] = useState(true)
  const [filter, setFilter] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)

  const filteredLogs = useMemo(() => {
    if (!filter) return logs
    const lower = filter.toLowerCase()
    return logs.filter(
      (l) =>
        l.message.toLowerCase().includes(lower) ||
        l.nodeId.toLowerCase().includes(lower)
    )
  }, [logs, filter])

  // Auto-scroll when pinned
  useEffect(() => {
    if (pinned && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [filteredLogs.length, pinned])

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '6px 10px',
          borderBottom: `1px solid ${T.border}`,
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.dim,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
          }}
        >
          LOGS
        </span>
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.dim,
          }}
        >
          ({filteredLogs.length})
        </span>
        <div style={{ flex: 1 }} />
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            padding: '2px 6px',
            background: T.surface2,
            border: `1px solid ${T.border}`,
          }}
        >
          <Search size={9} color={T.dim} />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter..."
            style={{
              background: 'none',
              border: 'none',
              outline: 'none',
              fontFamily: F,
              fontSize: FS.xxs,
              color: T.text,
              width: 80,
            }}
          />
        </div>
        <button
          onClick={() => setPinned(!pinned)}
          title={pinned ? 'Unpin from bottom' : 'Pin to bottom'}
          style={{
            background: 'none',
            border: 'none',
            color: pinned ? T.cyan : T.dim,
            cursor: 'pointer',
            padding: 2,
            display: 'flex',
            alignItems: 'center',
          }}
        >
          {pinned ? <Pin size={10} /> : <PinOff size={10} />}
        </button>
      </div>

      {/* Log lines */}
      <div
        ref={containerRef}
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '4px 0',
          background: T.surface0,
        }}
      >
        {filteredLogs.length === 0 ? (
          <div
            style={{
              fontFamily: F,
              fontSize: FS.xs,
              color: T.dim,
              textAlign: 'center',
              padding: 20,
            }}
          >
            {logs.length === 0 ? 'Waiting for log output...' : 'No matching logs'}
          </div>
        ) : (
          filteredLogs.map((entry: LogEntry, i: number) => (
            <div
              key={i}
              style={{
                fontFamily: F,
                fontSize: FS.xxs,
                lineHeight: 1.7,
                padding: '0 10px',
                background: levelColor(entry.level),
                display: 'flex',
                gap: 6,
              }}
            >
              <span style={{ color: T.dim, flexShrink: 0 }}>
                [{formatTime(entry.timestamp)}]
              </span>
              <span
                style={{
                  color: levelTextColor(entry.level),
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-all',
                }}
              >
                {entry.message}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
