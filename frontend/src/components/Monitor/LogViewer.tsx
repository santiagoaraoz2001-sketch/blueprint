/**
 * LogViewer — terminal-like panel for live log streaming.
 *
 * Renders log lines from SSE 'node_log' events via monitorStore.
 * Each line: timestamp (gray HH:MM:SS), node name (teal badge),
 * severity badge, message.
 *
 * Features:
 *  - Node filter dropdown
 *  - Severity toggle checkboxes
 *  - Text search input
 *  - Auto-scroll to bottom during execution
 *  - Pauses auto-scroll when user scrolls up
 *  - "Jump to bottom" button when paused
 *  - Virtual scrolling for up to 5000 lines
 *  - Font-scale-aware line height (responds to user font size setting)
 */
import { useState, useRef, useEffect, useMemo, useCallback } from 'react'
import { T, F, FS, FCODE } from '@/lib/design-tokens'
import { useMonitorStore, type LogSeverity } from '@/stores/monitorStore'
import { useSettingsStore, FONT_SIZE_SCALES } from '@/stores/settingsStore'
import { Search, ChevronDown, ArrowDown } from 'lucide-react'

// ── Scale-aware line height ────────────────────────────────────────────
//
// The base line height is calibrated for the default font size (11px code
// font → 22px line). When the user changes their font size scale (compact,
// default, comfortable, large), the line height scales proportionally so
// that virtual-scrolling position math stays accurate.
//
// Using a hook rather than a constant ensures React re-renders when the
// setting changes, and the virtual scroll container recalculates offsets.
const BASE_LINE_HEIGHT = 22
const BASE_FONT_SIZE = 11
const BASE_TIMESTAMP_SIZE = 10
const BASE_BADGE_SIZE = 9
const OVERSCAN = 10

function useScaledLineHeight() {
  const fontSize = useSettingsStore((s) => s.fontSize)
  const scale = FONT_SIZE_SCALES[fontSize] ?? 1.0
  return {
    lineHeight: Math.round(BASE_LINE_HEIGHT * scale),
    codeFontSize: Math.round(BASE_FONT_SIZE * scale * 100) / 100,
    timestampFontSize: Math.round(BASE_TIMESTAMP_SIZE * scale * 100) / 100,
    badgeFontSize: Math.round(BASE_BADGE_SIZE * scale * 100) / 100,
    scale,
  }
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map((n) => String(n).padStart(2, '0'))
    .join(':')
}

function severityColor(severity: LogSeverity): string {
  switch (severity) {
    case 'error': return T.red
    case 'warn':  return T.amber
    case 'debug': return T.dim
    default:      return T.text
  }
}

function severityBgColor(severity: LogSeverity): string {
  switch (severity) {
    case 'error': return `${T.red}15`
    case 'warn':  return `${T.amber}10`
    default:      return 'transparent'
  }
}

function SeverityBadge({ severity, fontSize }: { severity: LogSeverity; fontSize: number }) {
  const colors: Record<LogSeverity, string> = {
    debug: T.dim,
    info: T.blue,
    warn: T.amber,
    error: T.red,
  }
  return (
    <span
      style={{
        fontFamily: F,
        fontSize,
        color: colors[severity],
        padding: '0 4px',
        borderRadius: 2,
        background: `${colors[severity]}18`,
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        flexShrink: 0,
      }}
    >
      {severity}
    </span>
  )
}

function NodeBadge({ name, fontSize }: { name: string; fontSize: number }) {
  return (
    <span
      style={{
        fontFamily: F,
        fontSize,
        color: '#00BFA5',
        padding: '0 5px',
        borderRadius: 2,
        background: '#00BFA518',
        maxWidth: 100,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
        flexShrink: 0,
      }}
    >
      {name}
    </span>
  )
}

export default function LogViewer() {
  const logs = useMonitorStore((s) => s.logs)
  const blocks = useMonitorStore((s) => s.blocks)
  const { lineHeight, codeFontSize, timestampFontSize, badgeFontSize } = useScaledLineHeight()

  const [selectedNode, setSelectedNode] = useState<string>('all')
  const [severityFilter, setSeverityFilter] = useState<Record<LogSeverity, boolean>>({
    debug: true,
    info: true,
    warn: true,
    error: true,
  })
  const [searchText, setSearchText] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const [showNodeDropdown, setShowNodeDropdown] = useState(false)

  const containerRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const isUserScrolling = useRef(false)

  // Unique node IDs for the filter dropdown
  const nodeOptions = useMemo(() => {
    const seen = new Map<string, string>()
    for (const log of logs) {
      if (!seen.has(log.nodeId)) {
        seen.set(log.nodeId, log.nodeName)
      }
    }
    return Array.from(seen.entries()).map(([id, name]) => ({ id, name }))
  }, [logs])

  // Filter logs
  const filteredLogs = useMemo(() => {
    const searchLower = searchText.toLowerCase()
    return logs.filter((log) => {
      if (selectedNode !== 'all' && log.nodeId !== selectedNode) return false
      if (!severityFilter[log.severity]) return false
      if (searchText && !log.message.toLowerCase().includes(searchLower) &&
          !log.nodeName.toLowerCase().includes(searchLower)) return false
      return true
    })
  }, [logs, selectedNode, severityFilter, searchText])

  // Virtual scrolling state
  const [scrollTop, setScrollTop] = useState(0)
  const totalHeight = filteredLogs.length * lineHeight
  const containerHeight = scrollRef.current?.clientHeight ?? 400

  const visibleStart = Math.max(0, Math.floor(scrollTop / lineHeight) - OVERSCAN)
  const visibleEnd = Math.min(
    filteredLogs.length,
    Math.ceil((scrollTop + containerHeight) / lineHeight) + OVERSCAN
  )
  const visibleLogs = filteredLogs.slice(visibleStart, visibleEnd)

  // Auto-scroll to bottom
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [filteredLogs.length, autoScroll])

  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    setScrollTop(el.scrollTop)

    // Detect user scrolling up (not auto-scroll triggered)
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < lineHeight * 2
    if (!isAtBottom && !isUserScrolling.current) {
      setAutoScroll(false)
    }
    if (isAtBottom) {
      setAutoScroll(true)
    }
    isUserScrolling.current = false
  }, [lineHeight])

  const jumpToBottom = useCallback(() => {
    setAutoScroll(true)
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [])

  const toggleSeverity = useCallback((level: LogSeverity) => {
    setSeverityFilter((prev) => ({ ...prev, [level]: !prev[level] }))
  }, [])

  return (
    <div
      ref={containerRef}
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
        background: T.surface0,
      }}
    >
      {/* Toolbar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '5px 10px',
          borderBottom: `1px solid ${T.border}`,
          flexShrink: 0,
          flexWrap: 'wrap',
        }}
      >
        {/* Node filter dropdown */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setShowNodeDropdown(!showNodeDropdown)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              padding: '2px 8px',
              background: T.surface2,
              border: `1px solid ${T.border}`,
              borderRadius: 3,
              color: T.sec,
              fontFamily: F,
              fontSize: FS.xxs,
              cursor: 'pointer',
            }}
          >
            {selectedNode === 'all' ? 'All Nodes' : (blocks[selectedNode]?.label || selectedNode)}
            <ChevronDown size={10} />
          </button>
          {showNodeDropdown && (
            <div
              style={{
                position: 'absolute',
                top: '100%',
                left: 0,
                marginTop: 2,
                background: T.raised,
                border: `1px solid ${T.borderHi}`,
                borderRadius: 4,
                boxShadow: `0 8px 24px rgba(0,0,0,0.5)`,
                zIndex: 100,
                minWidth: 160,
                maxHeight: 200,
                overflowY: 'auto',
              }}
            >
              <button
                onClick={() => { setSelectedNode('all'); setShowNodeDropdown(false) }}
                style={{
                  display: 'block',
                  width: '100%',
                  padding: '5px 10px',
                  background: selectedNode === 'all' ? `${T.cyan}15` : 'transparent',
                  border: 'none',
                  color: T.text,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  textAlign: 'left',
                  cursor: 'pointer',
                }}
              >
                All Nodes
              </button>
              {nodeOptions.map((opt) => (
                <button
                  key={opt.id}
                  onClick={() => { setSelectedNode(opt.id); setShowNodeDropdown(false) }}
                  style={{
                    display: 'block',
                    width: '100%',
                    padding: '5px 10px',
                    background: selectedNode === opt.id ? `${T.cyan}15` : 'transparent',
                    border: 'none',
                    color: T.text,
                    fontFamily: F,
                    fontSize: FS.xxs,
                    textAlign: 'left',
                    cursor: 'pointer',
                  }}
                >
                  {opt.name}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Severity toggles */}
        {(['debug', 'info', 'warn', 'error'] as LogSeverity[]).map((level) => (
          <label
            key={level}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 3,
              cursor: 'pointer',
              opacity: severityFilter[level] ? 1 : 0.4,
            }}
          >
            <input
              type="checkbox"
              checked={severityFilter[level]}
              onChange={() => toggleSeverity(level)}
              style={{ width: 10, height: 10, accentColor: severityColor(level) }}
            />
            <span style={{ fontFamily: F, fontSize: badgeFontSize, color: severityColor(level), textTransform: 'uppercase' }}>
              {level}
            </span>
          </label>
        ))}

        <div style={{ flex: 1 }} />

        {/* Text search */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            padding: '2px 6px',
            background: T.surface2,
            border: `1px solid ${T.border}`,
            borderRadius: 3,
          }}
        >
          <Search size={9} color={T.dim} />
          <input
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="Search logs..."
            style={{
              background: 'none',
              border: 'none',
              outline: 'none',
              fontFamily: F,
              fontSize: FS.xxs,
              color: T.text,
              width: 100,
            }}
          />
        </div>

        {/* Log count */}
        <span style={{ fontFamily: FCODE, fontSize: FS.xxs, color: T.dim }}>
          {filteredLogs.length}/{logs.length}
        </span>
      </div>

      {/* Log output area with virtual scrolling */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        style={{
          flex: 1,
          overflowY: 'auto',
          position: 'relative',
        }}
      >
        {filteredLogs.length === 0 ? (
          <div
            style={{
              fontFamily: F,
              fontSize: FS.xs,
              color: T.dim,
              textAlign: 'center',
              padding: 40,
            }}
          >
            {logs.length === 0 ? 'Waiting for log output...' : 'No matching logs'}
          </div>
        ) : (
          <div style={{ height: totalHeight, position: 'relative' }}>
            <div
              style={{
                position: 'absolute',
                top: visibleStart * lineHeight,
                left: 0,
                right: 0,
              }}
            >
              {visibleLogs.map((line, i) => (
                <div
                  key={visibleStart + i}
                  style={{
                    height: lineHeight,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '0 10px',
                    fontFamily: FCODE,
                    fontSize: codeFontSize,
                    lineHeight: `${lineHeight}px`,
                    background: severityBgColor(line.severity),
                    borderBottom: `0.5px solid ${T.border}22`,
                  }}
                >
                  {/* Timestamp */}
                  <span style={{ color: T.dim, flexShrink: 0, fontSize: timestampFontSize }}>
                    {formatTime(line.timestamp)}
                  </span>
                  {/* Node badge */}
                  <NodeBadge name={line.nodeName} fontSize={badgeFontSize} />
                  {/* Severity */}
                  <SeverityBadge severity={line.severity} fontSize={badgeFontSize} />
                  {/* Message */}
                  <span
                    style={{
                      color: severityColor(line.severity),
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      flex: 1,
                      minWidth: 0,
                    }}
                    title={line.message}
                  >
                    {line.message}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Jump to bottom button */}
      {!autoScroll && filteredLogs.length > 0 && (
        <button
          onClick={jumpToBottom}
          style={{
            position: 'absolute',
            bottom: 12,
            right: 20,
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            padding: '4px 10px',
            background: T.raised,
            border: `1px solid ${T.borderHi}`,
            borderRadius: 12,
            color: T.cyan,
            fontFamily: F,
            fontSize: FS.xxs,
            cursor: 'pointer',
            boxShadow: `0 4px 12px rgba(0,0,0,0.4)`,
            zIndex: 10,
          }}
        >
          <ArrowDown size={10} />
          Jump to bottom
        </button>
      )}
    </div>
  )
}
