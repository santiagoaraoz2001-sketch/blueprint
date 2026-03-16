import { useEffect, useRef, useState, useCallback, useMemo, memo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useOutputStore, formatDuration } from '@/stores/outputStore'
import type { OutputEntry, OutputCategory } from '@/stores/outputStore'
import { Copy, Check, Trash2, ArrowDown, Terminal, Cpu, Brain, Zap, Activity } from 'lucide-react'
import toast from 'react-hot-toast'

// ── Category filter tabs ─────────────────────────────────────────────────────

const CATEGORY_FILTERS: { key: OutputCategory | 'all'; label: string }[] = [
  { key: 'all', label: 'ALL' },
  { key: 'inference', label: 'INFERENCE' },
  { key: 'training', label: 'TRAINING' },
  { key: 'agents', label: 'AGENTS' },
  { key: 'merge', label: 'MERGE' },
  { key: 'flow', label: 'FLOW' },
  { key: 'data', label: 'DATA' },
  { key: 'error', label: 'ERRORS' },
  { key: 'system', label: 'SYSTEM' },
]

// ── Main component ───────────────────────────────────────────────────────────

export default function OutputView() {
  const isStreaming = useOutputStore((s) => s.isStreaming)
  const entries = useOutputStore((s) => s.entries)
  const elapsed = useOutputStore((s) => s.elapsed)
  const etaDisplay = useOutputStore((s) => s.etaDisplay)
  const activeRunId = useOutputStore((s) => s.activeRunId)
  const inferenceMetrics = useOutputStore((s) => s.inferenceMetrics)
  const trainingMetrics = useOutputStore((s) => s.trainingMetrics)
  const hardwareMetrics = useOutputStore((s) => s.hardwareMetrics)

  const [filter, setFilter] = useState<OutputCategory | 'all'>('all')
  const [autoScroll, setAutoScroll] = useState(true)
  const [copied, setCopied] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)
  const copiedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Auto-scroll on new entries
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [entries.length, autoScroll])

  // Clean up copied timer on unmount
  useEffect(() => {
    return () => {
      if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current)
    }
  }, [])

  // Detect manual scroll up to pause auto-scroll
  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 40
    setAutoScroll(isAtBottom)
  }, [])

  // Memoize filtered entries to avoid recomputing on every render with large lists
  const filteredEntries = useMemo(() => {
    if (filter === 'all') return entries
    return entries.filter((e) => e.category === filter)
  }, [entries, filter])

  const handleCopyAll = useCallback(async () => {
    const text = useOutputStore.getState().getAllText()
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      toast.success('Copied to clipboard')
      if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current)
      copiedTimerRef.current = setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error('Failed to copy')
    }
  }, [])

  const handleClear = useCallback(() => {
    useOutputStore.getState().clearEntries()
  }, [])

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
      setAutoScroll(true)
    }
  }, [])

  // Show metrics panel if we have training or inference metrics
  const showTrainingPanel = trainingMetrics.loss !== null || trainingMetrics.step > 0
  const showInferencePanel = inferenceMetrics.totalTokens > 0 || inferenceMetrics.latencyMs > 0

  if (!activeRunId && entries.length === 0) {
    return <EmptyState />
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '6px 12px',
          borderBottom: `1px solid ${T.border}`,
          flexShrink: 0,
          background: T.surface1,
        }}
      >
        <Terminal size={12} color={T.cyan} />
        <span style={{ fontFamily: F, fontSize: FS.sm, fontWeight: 700, color: T.text, letterSpacing: '0.06em' }}>
          OUTPUT
        </span>

        {isStreaming && (
          <span style={{
            display: 'flex', alignItems: 'center', gap: 4,
            fontFamily: F, fontSize: FS.xxs, color: T.cyan,
          }}>
            <Activity size={9} style={{ animation: 'pulse 1.5s ease-in-out infinite' }} />
            STREAMING
          </span>
        )}

        {/* Elapsed */}
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          {formatDuration(elapsed)}
        </span>

        {/* ETA */}
        {isStreaming && etaDisplay !== '--' && (
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
            ETA {etaDisplay}
          </span>
        )}

        <div style={{ flex: 1 }} />

        {/* Entry count */}
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          {entries.length.toLocaleString()} events
        </span>

        <button
          onClick={handleCopyAll}
          title="Copy all output text to clipboard"
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '2px 8px', background: `${T.cyan}14`,
            border: `1px solid ${T.cyan}33`, color: T.cyan,
            fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
          }}
        >
          {copied ? <Check size={9} /> : <Copy size={9} />}
          {copied ? 'COPIED' : 'COPY ALL'}
        </button>
        <button
          onClick={handleClear}
          title="Clear all output entries"
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '2px 8px', background: `${T.red}14`,
            border: `1px solid ${T.red}33`, color: T.red,
            fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
          }}
        >
          <Trash2 size={9} />
          CLEAR
        </button>
      </div>

      {/* Category filter tabs */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 0,
          borderBottom: `1px solid ${T.border}`,
          flexShrink: 0,
          background: T.surface0,
          overflowX: 'auto',
        }}
      >
        {CATEGORY_FILTERS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setFilter(key)}
            style={{
              padding: '4px 12px',
              background: filter === key ? `${T.cyan}14` : 'transparent',
              border: 'none',
              borderBottom: filter === key ? `2px solid ${T.cyan}` : '2px solid transparent',
              color: filter === key ? T.cyan : T.dim,
              fontFamily: F,
              fontSize: FS.xxs,
              letterSpacing: '0.1em',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              flexShrink: 0,
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Main content area */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Output stream — left / main */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative' }}>
          <div
            ref={scrollRef}
            onScroll={handleScroll}
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '8px 12px',
              fontFamily: F,
              fontSize: FS.xs,
              lineHeight: 1.6,
            }}
          >
            {filteredEntries.map((entry) => (
              <OutputEntryRow key={entry.id} entry={entry} />
            ))}
            {filteredEntries.length === 0 && (
              <span style={{ color: T.dim, fontSize: FS.xxs }}>
                {entries.length > 0 ? 'No entries match this filter' : 'Waiting for output...'}
              </span>
            )}
          </div>

          {/* Scroll-to-bottom button — positioned relative to the output stream container */}
          {!autoScroll && (
            <button
              onClick={scrollToBottom}
              style={{
                position: 'absolute',
                bottom: 12,
                left: '50%',
                transform: 'translateX(-50%)',
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: '4px 12px',
                background: T.surface3,
                border: `1px solid ${T.borderHi}`,
                color: T.text,
                fontFamily: F,
                fontSize: FS.xxs,
                cursor: 'pointer',
                zIndex: 10,
                boxShadow: T.shadow,
              }}
            >
              <ArrowDown size={10} />
              Scroll to bottom
            </button>
          )}
        </div>

        {/* Right sidebar — metrics panels */}
        <div
          style={{
            width: 240,
            minWidth: 240,
            borderLeft: `1px solid ${T.border}`,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'auto',
            flexShrink: 0,
            background: T.surface0,
          }}
        >
          {/* Hardware metrics — always visible */}
          <MetricsSection title="SYSTEM" icon={<Cpu size={10} color={T.dim} />}>
            <MetricRow label="CPU" value={`${hardwareMetrics.cpuPercent.toFixed(0)}%`} />
            <MetricRow label="RAM" value={`${hardwareMetrics.memGb.toFixed(1)} GB (${hardwareMetrics.memPercent.toFixed(0)}%)`} />
            {hardwareMetrics.gpuPercent !== null && (
              <MetricRow label="GPU" value={`${hardwareMetrics.gpuPercent.toFixed(0)}%`} />
            )}
          </MetricsSection>

          {/* Inference metrics — shown when data present */}
          {showInferencePanel && (
            <MetricsSection title="INFERENCE" icon={<Zap size={10} color={T.cyan} />}>
              <MetricRow label="Latency" value={`${inferenceMetrics.latencyMs.toFixed(0)} ms`} />
              <MetricRow label="Tokens" value={inferenceMetrics.totalTokens.toLocaleString()} />
              <MetricRow label="Tokens/s" value={inferenceMetrics.tokensPerSecond.toLocaleString()} />
            </MetricsSection>
          )}

          {/* Training metrics — shown when data present */}
          {showTrainingPanel && (
            <MetricsSection title="TRAINING" icon={<Brain size={10} color={T.amber} />}>
              {trainingMetrics.loss !== null && (
                <MetricRow label="Loss" value={trainingMetrics.loss.toFixed(4)} color={T.amber} />
              )}
              {trainingMetrics.learningRate !== null && (
                <MetricRow label="LR" value={trainingMetrics.learningRate.toExponential(2)} />
              )}
              {trainingMetrics.totalSteps > 0 && (
                <MetricRow label="Step" value={`${trainingMetrics.step.toLocaleString()} / ${trainingMetrics.totalSteps.toLocaleString()}`} />
              )}
              {trainingMetrics.epoch > 0 && (
                <MetricRow label="Epoch" value={`${trainingMetrics.epoch}`} />
              )}
            </MetricsSection>
          )}
        </div>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
      `}</style>
    </div>
  )
}

// ── Sub-components ───────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        gap: 12,
      }}
    >
      <Terminal size={24} color={T.dim} />
      <span style={{ fontFamily: F, fontSize: FS.sm, color: T.dim }}>
        No output yet
      </span>
      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
        Run a pipeline to see output here
      </span>
    </div>
  )
}

/** Memoized entry row — avoids re-rendering all rows when a new entry is appended */
const OutputEntryRow = memo(function OutputEntryRow({ entry }: { entry: OutputEntry }) {
  const categoryColor = getCategoryColor(entry.category)

  return (
    <div
      style={{
        display: 'flex',
        gap: 8,
        padding: '2px 0',
        borderBottom: entry.entryType === 'text' ? `1px solid ${T.border}` : 'none',
      }}
    >
      {/* Timestamp */}
      <span style={{ color: T.dim, fontSize: FS.xxs, flexShrink: 0, width: 50, textAlign: 'right' }}>
        {formatTimestamp(entry.timestamp)}
      </span>

      {/* Category badge */}
      <span
        style={{
          color: categoryColor,
          fontSize: FS.xxs,
          flexShrink: 0,
          width: 56,
          letterSpacing: '0.05em',
          textTransform: 'uppercase',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {entry.category}
      </span>

      {/* Content */}
      <span
        style={{
          color: entry.entryType === 'log' ? T.sec
            : entry.entryType === 'metric' ? T.amber
            : entry.entryType === 'iteration' ? T.purple
            : T.text,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          flex: 1,
        }}
      >
        {entry.content}
      </span>
    </div>
  )
})

function MetricsSection({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div style={{ borderBottom: `1px solid ${T.border}`, padding: '8px 12px' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          marginBottom: 6,
          fontFamily: F,
          fontSize: FS.xxs,
          color: T.dim,
          letterSpacing: '0.1em',
        }}
      >
        {icon}
        {title}
      </div>
      {children}
    </div>
  )
}

function MetricRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        padding: '2px 0',
        fontFamily: F,
        fontSize: FS.xxs,
      }}
    >
      <span style={{ color: T.dim }}>{label}</span>
      <span style={{ color: color || T.text }}>{value}</span>
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Cache for formatted timestamps to avoid creating Date objects on every render */
const timestampCache = new Map<number, string>()
const MAX_CACHE_SIZE = 15_000

function formatTimestamp(ts: number): string {
  // Round to second granularity for cache efficiency
  const key = Math.floor(ts / 1000) * 1000
  let cached = timestampCache.get(key)
  if (cached) return cached
  cached = new Date(key).toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
  // Evict oldest entries if cache grows too large
  if (timestampCache.size >= MAX_CACHE_SIZE) {
    const firstKey = timestampCache.keys().next().value
    if (firstKey !== undefined) timestampCache.delete(firstKey)
  }
  timestampCache.set(key, cached)
  return cached
}

function getCategoryColor(category: OutputCategory): string {
  switch (category) {
    case 'inference': return T.cyan
    case 'training': return T.amber
    case 'agents': return T.purple
    case 'merge': return T.blue
    case 'flow': return T.green
    case 'error': return T.red
    case 'system': return T.dim
    default: return T.sec
  }
}
