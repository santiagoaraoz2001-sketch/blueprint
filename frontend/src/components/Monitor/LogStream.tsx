import { useState, useRef, useEffect } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore } from '@/stores/metricsStore'
import { ArrowDown, Search } from 'lucide-react'

interface Props {
  compact?: boolean
}

export default function LogStream({ compact = false }: Props) {
  const logs = useMetricsStore((s) => s.logs)
  const [pinToBottom, setPinToBottom] = useState(true)
  const [filter, setFilter] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  // Auto-scroll
  useEffect(() => {
    if (pinToBottom && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs, pinToBottom])

  // Handle scroll to detect manual scrolling
  const handleScroll = () => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 20
    if (!isAtBottom && pinToBottom) setPinToBottom(false)
    if (isAtBottom && !pinToBottom) setPinToBottom(true)
  }

  const filteredLogs = filter
    ? logs.filter(l => l.message.toLowerCase().includes(filter.toLowerCase()) || l.blockId.toLowerCase().includes(filter.toLowerCase()))
    : logs

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: compact ? '3px 8px' : '4px 12px',
        borderBottom: `1px solid ${T.border}`,
        flexShrink: 0,
      }}>
        <span style={{
          fontFamily: F, fontSize: FS.xxs, fontWeight: 900,
          color: T.dim, letterSpacing: '0.1em',
        }}>
          LOGS
        </span>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          ({filteredLogs.length})
        </span>

        <div style={{ flex: 1 }} />

        {/* Search/filter */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 4,
          padding: '1px 6px',
          background: T.surface2, border: `1px solid ${T.border}`,
        }}>
          <Search size={9} color={T.dim} />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter..."
            style={{
              background: 'none', border: 'none', outline: 'none',
              fontFamily: F, fontSize: FS.xxs, color: T.text,
              width: 80,
            }}
          />
        </div>

        {/* Pin to bottom */}
        <button
          onClick={() => {
            setPinToBottom(!pinToBottom)
            if (!pinToBottom && scrollRef.current) {
              scrollRef.current.scrollTop = scrollRef.current.scrollHeight
            }
          }}
          style={{
            display: 'flex', alignItems: 'center', gap: 3,
            padding: '1px 6px',
            background: pinToBottom ? `${T.cyan}15` : T.surface2,
            border: `1px solid ${pinToBottom ? `${T.cyan}40` : T.border}`,
            color: pinToBottom ? T.cyan : T.dim,
            fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
          }}
        >
          <ArrowDown size={8} /> PIN
        </button>
      </div>

      {/* Log entries */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        style={{
          flex: 1, overflow: 'auto', padding: '4px 8px',
          fontFamily: F, fontSize: FS.xxs, lineHeight: 1.6,
        }}
      >
        {filteredLogs.length === 0 ? (
          <div style={{ color: T.dim, padding: 8, textAlign: 'center' }}>
            {logs.length === 0 ? 'Waiting for logs...' : 'No matching logs'}
          </div>
        ) : (
          filteredLogs.map((log, i) => (
            <div
              key={i}
              style={{
                padding: '1px 0',
                background: log.level === 'error' ? `${T.red}10` : log.level === 'warn' ? `${T.amber}08` : 'transparent',
                borderLeft: log.level === 'error' ? `2px solid ${T.red}` : log.level === 'warn' ? `2px solid ${T.amber}` : '2px solid transparent',
                paddingLeft: 4,
              }}
            >
              <span style={{ color: T.dim }}>[{log.timestamp}]</span>
              {log.blockId && (
                <span style={{ color: T.cyan, marginLeft: 4 }}>[{log.blockId}]</span>
              )}
              <span style={{
                color: log.level === 'error' ? T.red : log.level === 'warn' ? T.amber : T.sec,
                marginLeft: 4,
              }}>
                {log.message}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
