import { useEffect, useRef, useState, useCallback, memo } from 'react'
import { T, F, FS, FD, CATEGORY_COLORS } from '@/lib/design-tokens'
import { useOutputStore, type OutputEntry } from '@/stores/outputStore'
import { useRunStore } from '@/stores/runStore'
import { useUIStore } from '@/stores/uiStore'
import { sseManager } from '@/services/sseManager'
import { api } from '@/api/client'
import {
  Terminal, Trash2, Copy, ArrowDown, Clock,
  Cpu, HardDrive, MonitorDot, Zap, Activity,
  TrendingDown, GraduationCap, Layers, GitBranch,
} from 'lucide-react'

const SYSTEM_POLL_INTERVAL = 5000

// Short labels for category badges — avoids arbitrary truncation
const CATEGORY_LABELS: Record<string, string> = {
  external: 'EXT',
  data: 'DATA',
  model: 'MODEL',
  training: 'TRAIN',
  metrics: 'EVAL',
  embedding: 'EMBED',
  utilities: 'UTIL',
  agents: 'AGENT',
  interventions: 'GATE',
  inference: 'INFER',
  endpoints: 'ENDPT',
}

// ── Helpers ──

function formatTime(ms: number): string {
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${sec.toString().padStart(2, '0')}`
}

function categoryColor(cat: string): string {
  return CATEGORY_COLORS[cat] || T.dim
}

let entryCounter = 0
function makeEntryId(): string {
  return `oe-${++entryCounter}-${Date.now()}`
}

// ── Memoized output entry row ──

const OutputEntryRow = memo(function OutputEntryRow({ entry }: { entry: OutputEntry }) {
  const color = categoryColor(entry.category)
  const time = new Date(entry.timestamp)
  const timeStr = `${time.getHours().toString().padStart(2, '0')}:${time.getMinutes().toString().padStart(2, '0')}:${time.getSeconds().toString().padStart(2, '0')}`
  const badgeLabel = CATEGORY_LABELS[entry.category] || entry.category.toUpperCase()

  return (
    <div style={{
      display: 'flex', gap: 8, padding: '4px 0',
      borderBottom: `1px solid ${T.border}08`,
      alignItems: 'flex-start',
    }}>
      {/* Timestamp */}
      <span style={{
        fontFamily: F, fontSize: FS.xxs, color: T.dim,
        minWidth: 48, flexShrink: 0, paddingTop: 2,
      }}>
        {timeStr}
      </span>

      {/* Category badge */}
      {entry.category && (
        <span style={{
          fontFamily: F, fontSize: '6px', fontWeight: 700,
          padding: '1px 4px', borderRadius: 2,
          background: `${color}18`, color,
          letterSpacing: '0.06em', textTransform: 'uppercase',
          flexShrink: 0, marginTop: 2,
        }}>
          {badgeLabel}
        </span>
      )}

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {entry.entryType === 'iteration' ? (
          <span style={{
            fontFamily: F, fontSize: FS.xs, fontWeight: 700,
            color: T.amber, display: 'inline-flex', alignItems: 'center', gap: 4,
          }}>
            <GitBranch size={9} />
            [{entry.content}]
          </span>
        ) : entry.entryType === 'metric' ? (
          <span style={{
            fontFamily: F, fontSize: FS.xs, color: T.sec,
            display: 'inline-flex', alignItems: 'center', gap: 4,
          }}>
            <MonitorDot size={9} color={T.green} />
            {entry.content}
          </span>
        ) : entry.entryType === 'log' ? (
          <span style={{
            fontFamily: F, fontSize: FS.xs, color: T.dim,
            fontStyle: 'italic',
          }}>
            {entry.content}
          </span>
        ) : (
          <pre style={{
            fontFamily: F, fontSize: FS.xs, color: T.text,
            margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            lineHeight: 1.6,
          }}>
            {entry.content}
          </pre>
        )}
      </div>
    </div>
  )
})

// ── Metrics components ──

const MetricsSection = memo(function MetricsSection({ title, icon, children }: {
  title: string; icon: React.ReactNode; children: React.ReactNode
}) {
  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        fontFamily: F, fontSize: FS.xxs, fontWeight: 900,
        color: T.dim, letterSpacing: '0.12em',
        marginBottom: 8, paddingBottom: 4,
        borderBottom: `1px solid ${T.border}`,
      }}>
        {icon}
        {title}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {children}
      </div>
    </div>
  )
})

const MetricBar = memo(function MetricBar({ label, value, unit, color }: {
  label: string; value: number; unit: string; color: string
}) {
  return (
    <div>
      <div style={{
        display: 'flex', justifyContent: 'space-between', marginBottom: 3,
        fontFamily: F, fontSize: FS.xxs, color: T.sec,
      }}>
        <span>{label}</span>
        <span style={{ color: T.text }}>{value.toFixed(0)}{unit}</span>
      </div>
      <div style={{
        height: 3, background: T.surface3, borderRadius: 2, overflow: 'hidden',
      }}>
        <div style={{
          width: `${Math.min(value, 100)}%`, height: '100%',
          background: color, borderRadius: 2,
          transition: 'width 0.5s ease',
        }} />
      </div>
    </div>
  )
})

const MetricRow = memo(function MetricRow({ label, value, icon }: {
  label: string; value: string; icon?: React.ReactNode
}) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      fontFamily: F, fontSize: FS.xxs,
    }}>
      <span style={{ color: T.dim, display: 'flex', alignItems: 'center', gap: 4 }}>
        {icon}
        {label}
      </span>
      <span style={{ color: T.text, fontWeight: 600 }}>{value}</span>
    </div>
  )
})

// ── Empty state ──

function EmptyState({ onNavigate }: { onNavigate: () => void }) {
  return (
    <div style={{
      height: '100%', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', gap: 16,
      padding: 40,
    }}>
      <Terminal size={40} color={T.dim} strokeWidth={1} />
      <div style={{
        fontFamily: F, fontSize: FS.md, color: T.sec,
        textAlign: 'center', lineHeight: 1.8,
      }}>
        No pipeline output yet.
      </div>
      <div style={{
        fontFamily: F, fontSize: FS.xs, color: T.dim,
        textAlign: 'center', lineHeight: 1.8, maxWidth: 400,
      }}>
        Run a pipeline from the Pipeline Editor to see real-time output, metrics, and results here.
      </div>
      <button
        onClick={onNavigate}
        style={{
          marginTop: 8, padding: '8px 20px',
          background: `${T.cyan}15`, border: `1px solid ${T.cyan}30`,
          borderRadius: 6, color: T.cyan, fontFamily: F,
          fontSize: FS.sm, cursor: 'pointer', fontWeight: 700,
          letterSpacing: '0.04em',
        }}
      >
        Open Pipeline Editor &rarr;
      </button>
    </div>
  )
}

// ── Shared styles ──

function headerBtnStyle(): React.CSSProperties {
  return {
    display: 'flex', alignItems: 'center', gap: 4,
    padding: '5px 10px', background: T.surface3,
    border: `1px solid ${T.border}`, borderRadius: 4,
    color: T.dim, fontFamily: F, fontSize: FS.xs,
    cursor: 'pointer',
  }
}

// ── Main View ──

export default function OutputView() {
  // Use individual selectors to avoid re-rendering on unrelated state changes
  const entries = useOutputStore((s) => s.entries)
  const activeRunId = useOutputStore((s) => s.activeRunId)
  const isStreaming = useOutputStore((s) => s.isStreaming)
  const activeCategory = useOutputStore((s) => s.activeCategory)
  const hardwareMetrics = useOutputStore((s) => s.hardwareMetrics)
  const inferenceMetrics = useOutputStore((s) => s.inferenceMetrics)
  const trainingMetrics = useOutputStore((s) => s.trainingMetrics)
  const eta = useOutputStore((s) => s.eta)
  const elapsed = useOutputStore((s) => s.elapsed)

  const latestRunId = useRunStore((s) => s.activeRunId)
  const runStatus = useRunStore((s) => s.status)
  const runProgress = useRunStore((s) => s.overallProgress)
  const activeBlockNodeId = useRunStore((s) => {
    const statuses = s.nodeStatuses
    for (const [, ns] of Object.entries(statuses)) {
      if (ns.status === 'running') return ns.nodeId
    }
    return null
  })
  const setView = useUIStore((s) => s.setView)

  const scrollRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [copied, setCopied] = useState(false)
  const elapsedRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const startTimeRef = useRef<number | null>(null)
  // Track the current SSE subscription to avoid double-subscribe
  const subscribedRunIdRef = useRef<string | null>(null)

  // Subscribe to the latest run via SSE
  useEffect(() => {
    const runId = activeRunId || latestRunId
    if (!runId) return

    // Avoid re-subscribing to the same run
    if (subscribedRunIdRef.current === runId) return
    subscribedRunIdRef.current = runId

    // Use getState() to call actions without adding them to dependencies
    const store = useOutputStore.getState()
    if (runId !== activeRunId) {
      store.setActiveRun(runId)
    }
    store.setStreaming(true)
    startTimeRef.current = Date.now()

    const unsubscribe = sseManager.subscribe(runId, (event, data) => {
      if (event.startsWith('__sse_')) return

      const { addEntry, updateInferenceMetrics, updateTrainingMetrics,
              updateHardwareMetrics, setActiveCategory, setEta, setStreaming } = useOutputStore.getState()

      switch (event) {
        case 'node_output':
          addEntry({
            id: makeEntryId(),
            timestamp: Date.now(),
            nodeId: data.node_id || '',
            blockType: data.block_type || '',
            category: data.category || 'data',
            entryType: 'text',
            content: typeof data.outputs === 'string'
              ? data.outputs
              : JSON.stringify(data.outputs, null, 2),
            metadata: data,
          })
          break

        case 'node_log':
          addEntry({
            id: makeEntryId(),
            timestamp: Date.now(),
            nodeId: data.node_id || '',
            blockType: data.block_type || '',
            category: data.category || 'data',
            entryType: 'log',
            content: data.message || data.log || '',
            metadata: data,
          })
          break

        case 'metric':
          if (data.category === 'inference') {
            updateInferenceMetrics(data)
          } else if (data.category === 'training') {
            updateTrainingMetrics(data)
          }
          addEntry({
            id: makeEntryId(),
            timestamp: Date.now(),
            nodeId: data.node_id || '',
            blockType: data.block_type || '',
            category: data.category || '',
            entryType: 'metric',
            content: `${data.name || 'metric'}: ${data.value ?? ''}`,
            metadata: data,
          })
          break

        case 'system_metric':
          updateHardwareMetrics({
            cpuPercent: data.cpu ?? data.cpuPercent ?? 0,
            memPercent: data.mem_percent ?? data.memPercent ?? 0,
            memGb: data.mem_gb ?? data.memGb ?? 0,
            gpuPercent: data.gpu ?? data.gpuPercent ?? null,
          })
          break

        case 'node_started':
          setActiveCategory(data.category || null)
          addEntry({
            id: makeEntryId(),
            timestamp: Date.now(),
            nodeId: data.node_id || '',
            blockType: data.block_type || '',
            category: data.category || '',
            entryType: 'log',
            content: `Started: ${data.label || data.block_type || data.node_id}`,
            metadata: data,
          })
          break

        case 'node_completed':
          addEntry({
            id: makeEntryId(),
            timestamp: Date.now(),
            nodeId: data.node_id || '',
            blockType: data.block_type || '',
            category: data.category || '',
            entryType: 'log',
            content: `Completed: ${data.label || data.block_type || data.node_id}`,
            metadata: data,
          })
          break

        case 'node_iteration':
          addEntry({
            id: makeEntryId(),
            timestamp: Date.now(),
            nodeId: data.node_id || '',
            blockType: data.block_type || '',
            category: data.category || '',
            entryType: 'iteration',
            content: `Iteration ${data.iteration ?? '?'}/${data.total ?? '?'}`,
            metadata: data,
          })
          break

        case 'node_progress':
          if (data.eta != null) setEta(data.eta)
          break

        case 'run_completed':
        case 'run_failed':
        case 'run_cancelled':
          setStreaming(false)
          subscribedRunIdRef.current = null
          addEntry({
            id: makeEntryId(),
            timestamp: Date.now(),
            nodeId: '',
            blockType: '',
            category: '',
            entryType: 'log',
            content: event === 'run_completed'
              ? 'Pipeline completed successfully.'
              : event === 'run_failed'
                ? `Pipeline failed: ${data.error || 'Unknown error'}`
                : 'Pipeline cancelled.',
          })
          break
      }
    })

    return () => {
      unsubscribe()
      subscribedRunIdRef.current = null
    }
  }, [activeRunId, latestRunId])

  // Elapsed timer
  useEffect(() => {
    if (isStreaming) {
      startTimeRef.current = startTimeRef.current || Date.now()
      elapsedRef.current = setInterval(() => {
        if (startTimeRef.current) {
          useOutputStore.getState().setElapsed(Date.now() - startTimeRef.current)
        }
      }, 1000)
    } else if (elapsedRef.current) {
      clearInterval(elapsedRef.current)
      elapsedRef.current = null
    }
    return () => {
      if (elapsedRef.current) {
        clearInterval(elapsedRef.current)
        elapsedRef.current = null
      }
    }
  }, [isStreaming])

  // Poll hardware metrics
  useEffect(() => {
    if (!isStreaming) return
    const poll = async () => {
      try {
        const hw = await api.get<any>('/system/hardware')
        if (!hw) return
        useOutputStore.getState().updateHardwareMetrics({
          cpuPercent: hw.cpu?.percent ?? 0,
          memGb: hw.ram?.used_gb ?? 0,
          memPercent: hw.ram?.percent ?? 0,
          gpuPercent: hw.gpus?.[0]?.utilization ?? null,
        })
      } catch { /* non-critical */ }
    }
    poll()
    const timer = setInterval(poll, SYSTEM_POLL_INTERVAL)
    return () => clearInterval(timer)
  }, [isStreaming])

  // Auto-scroll — use requestAnimationFrame for smooth scrolling
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      requestAnimationFrame(() => {
        if (scrollRef.current) {
          scrollRef.current.scrollTop = scrollRef.current.scrollHeight
        }
      })
    }
  }, [entries.length, autoScroll])

  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    const atBottom = scrollHeight - scrollTop - clientHeight < 60
    setAutoScroll(atBottom)
  }, [])

  const jumpToLatest = useCallback(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
      setAutoScroll(true)
    }
  }, [])

  const copyAll = useCallback(() => {
    const allEntries = useOutputStore.getState().entries
    const text = allEntries
      .filter((e) => e.entryType === 'text' || e.entryType === 'log')
      .map((e) => e.content)
      .join('\n')
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [])

  const handleClear = useCallback(() => {
    useOutputStore.getState().clear()
    startTimeRef.current = null
    subscribedRunIdRef.current = null
  }, [])

  // Empty state
  if (!activeRunId && !latestRunId && entries.length === 0) {
    return <EmptyState onNavigate={() => setView('editor')} />
  }

  const progress = runProgress ?? 0
  const statusLabel = runStatus === 'running' ? 'Running'
    : runStatus === 'complete' ? 'Complete'
    : runStatus === 'failed' ? 'Failed'
    : runStatus === 'cancelled' ? 'Cancelled'
    : isStreaming ? 'Running' : 'Idle'

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12,
        borderBottom: `1px solid ${T.border}`, flexShrink: 0,
      }}>
        <Terminal size={18} color={T.cyan} />
        <h2 style={{
          fontFamily: FD, fontSize: FS.xl * 1.5, fontWeight: 600,
          color: T.text, margin: 0, letterSpacing: '0.04em',
        }}>
          OUTPUT
        </h2>
        <div style={{ flex: 1 }} />

        {/* Elapsed / ETA */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          fontFamily: F, fontSize: FS.xs, color: T.dim,
        }}>
          <Clock size={10} />
          <span>{formatTime(elapsed)}</span>
          {eta != null && <span style={{ color: T.sec }}>/ ~{formatTime(eta)}</span>}
        </div>

        <button onClick={copyAll} style={headerBtnStyle()} title="Copy all output">
          <Copy size={10} />
          {copied ? 'COPIED' : 'COPY ALL'}
        </button>
        <button onClick={handleClear} style={headerBtnStyle()} title="Clear output">
          <Trash2 size={10} />
          CLEAR
        </button>
      </div>

      {/* Main content */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Left: Output stream */}
        <div style={{ flex: 3, display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative' }}>
          <div
            ref={scrollRef}
            onScroll={handleScroll}
            style={{
              flex: 1, overflow: 'auto', padding: '12px 16px',
              fontFamily: F, fontSize: FS.sm, color: T.text,
            }}
          >
            {entries.map((entry) => (
              <OutputEntryRow key={entry.id} entry={entry} />
            ))}
          </div>

          {/* Jump to latest — positioned relative to the output stream container */}
          {!autoScroll && (
            <button
              onClick={jumpToLatest}
              style={{
                position: 'absolute', bottom: 16, left: '50%',
                transform: 'translateX(-50%)',
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '6px 14px', background: T.surface3,
                border: `1px solid ${T.border}`, borderRadius: 20,
                color: T.cyan, fontFamily: F, fontSize: FS.xs,
                cursor: 'pointer', zIndex: 10,
                boxShadow: `0 2px 8px ${T.shadow}`,
              }}
            >
              <ArrowDown size={10} />
              Jump to latest
            </button>
          )}
        </div>

        {/* Right: Metrics panel */}
        <div style={{
          flex: 1, minWidth: 180, maxWidth: 220,
          borderLeft: `1px solid ${T.border}`, overflow: 'auto',
          padding: '12px', display: 'flex', flexDirection: 'column', gap: 16,
          background: T.surface0,
        }}>
          {/* Hardware */}
          <MetricsSection title="HARDWARE" icon={<Cpu size={10} />}>
            <MetricBar label="CPU" value={hardwareMetrics.cpuPercent} unit="%" color={T.cyan} />
            <MetricRow label="MEM" value={`${hardwareMetrics.memGb.toFixed(1)}G`} icon={<HardDrive size={9} />} />
            {hardwareMetrics.gpuPercent != null && (
              <MetricBar label="GPU" value={hardwareMetrics.gpuPercent} unit="%" color={T.purple} />
            )}
          </MetricsSection>

          {/* Inference metrics */}
          {(activeCategory === 'inference' || inferenceMetrics.totalTokens > 0) && (
            <MetricsSection title="INFERENCE" icon={<Zap size={10} />}>
              <MetricRow label="tok/s" value={inferenceMetrics.tokensPerSecond.toFixed(0)} icon={<Activity size={9} />} />
              <MetricRow label="total" value={inferenceMetrics.totalTokens.toLocaleString()} />
              {inferenceMetrics.contextWindow > 0 && (
                <MetricRow label="ctx" value={inferenceMetrics.contextWindow.toLocaleString()} />
              )}
              <MetricRow label="lat" value={`${inferenceMetrics.latencyMs.toFixed(0)}ms`} />
            </MetricsSection>
          )}

          {/* Training metrics */}
          {(activeCategory === 'training' || trainingMetrics.step > 0) && (
            <MetricsSection title="TRAINING" icon={<TrendingDown size={10} />}>
              <MetricRow label="loss" value={trainingMetrics.loss.toFixed(4)} />
              <MetricRow label="lr" value={trainingMetrics.learningRate.toExponential(1)} />
              <MetricRow label="epoch" value={trainingMetrics.epoch.toString()} icon={<GraduationCap size={9} />} />
              <MetricRow label="step" value={`${trainingMetrics.step}/${trainingMetrics.totalSteps}`} />
            </MetricsSection>
          )}

          {/* Merge/Loop */}
          {activeCategory === 'model' && (
            <MetricsSection title="MERGE" icon={<Layers size={10} />}>
              <MetricBar label="Progress" value={progress * 100} unit="%" color={T.blue} />
            </MetricsSection>
          )}
        </div>
      </div>

      {/* Status bar */}
      <div style={{
        padding: '8px 16px', display: 'flex', alignItems: 'center', gap: 12,
        borderTop: `1px solid ${T.border}`, flexShrink: 0,
        background: T.surface1,
      }}>
        {activeBlockNodeId && (
          <span style={{ fontFamily: F, fontSize: FS.xs, color: T.sec }}>
            {activeBlockNodeId}
          </span>
        )}
        {activeCategory && (
          <span style={{
            fontFamily: F, fontSize: FS.xxs, fontWeight: 700,
            padding: '2px 6px', borderRadius: 3,
            background: `${categoryColor(activeCategory)}20`,
            color: categoryColor(activeCategory),
            letterSpacing: '0.08em', textTransform: 'uppercase',
          }}>
            {activeCategory}
          </span>
        )}
        <div style={{ flex: 1 }} />

        {/* Progress bar */}
        <div style={{
          width: 120, height: 4, background: T.surface3,
          borderRadius: 2, overflow: 'hidden',
        }}>
          <div style={{
            width: `${Math.min(progress * 100, 100)}%`,
            height: '100%',
            background: statusLabel === 'Failed' ? T.red : T.cyan,
            borderRadius: 2,
            transition: 'width 0.3s ease',
          }} />
        </div>

        <span style={{
          fontFamily: F, fontSize: FS.xxs, fontWeight: 700,
          color: statusLabel === 'Running' ? T.amber
            : statusLabel === 'Complete' ? T.green
            : statusLabel === 'Failed' ? T.red
            : statusLabel === 'Cancelled' ? T.amber
            : T.dim,
          letterSpacing: '0.08em', textTransform: 'uppercase',
        }}>
          {statusLabel}
        </span>
      </div>
    </div>
  )
}
