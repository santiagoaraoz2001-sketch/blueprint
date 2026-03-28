import { useState, useCallback, useEffect, useMemo } from 'react'
import { T, F, FCODE, FS, MOTION } from '@/lib/design-tokens'
import {
  ChevronLeft,
  ChevronRight,
  Download,
  X,
  Clock,
  Cpu,
  AlertTriangle,
  CheckCircle2,
  SkipForward,
  Database,
  Loader2,
} from 'lucide-react'
import type { ReplayNode, ReplayData, ReplayArtifact, ReplayLoopSummary } from '@/hooks/useReplay'
import { useReplayData, downloadSupportBundle } from '@/hooks/useReplay'

// ── Status colors & helpers ────────────────────────────────────────────

const STATUS_COLOR: Record<string, string> = {
  completed: T.green,
  failed: T.red,
  skipped: T.dim,
  cached: T.amber,
  not_executed: T.dim,
  running: T.cyan,
}

const STATUS_LABEL: Record<string, string> = {
  completed: 'Completed',
  failed: 'Failed',
  skipped: 'Skipped',
  cached: 'Cache Hit',
  not_executed: 'Not Executed',
  running: 'Running',
}

const DECISION_LABEL: Record<string, string> = {
  execute: 'Executed',
  cache_hit: 'Cache Hit',
  skipped: 'Skipped',
}

function formatDuration(ms: number | null): string {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1000) return `${Math.round(ms)}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  const mins = Math.floor(ms / 60000)
  const secs = ((ms % 60000) / 1000).toFixed(0)
  return `${mins}m ${secs}s`
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(i > 1 ? 1 : 0)} ${sizes[i]}`
}

// ── Detail Panel Tabs ──────────────────────────────────────────────────

type DetailTab = 'inputs' | 'outputs' | 'config' | 'timing' | 'decision'

function TabButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '4px 10px',
        fontFamily: F,
        fontSize: FS.xxs,
        color: active ? T.cyan : T.dim,
        background: active ? `${T.cyan}14` : 'transparent',
        border: `1px solid ${active ? T.cyan + '44' : 'transparent'}`,
        cursor: 'pointer',
        transition: `all ${MOTION.fast}`,
        letterSpacing: '0.04em',
        textTransform: 'uppercase',
      }}
    >
      {label}
    </button>
  )
}

// ── Artifact List ──────────────────────────────────────────────────────

function ArtifactList({ artifacts, label }: { artifacts: ReplayArtifact[]; label: string }) {
  if (!artifacts.length) {
    return (
      <div style={{ padding: 12, color: T.dim, fontFamily: F, fontSize: FS.xxs }}>
        No {label.toLowerCase()} for this node.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '8px 0' }}>
      {artifacts.map((art) => (
        <div
          key={art.artifact_id}
          style={{
            background: T.surface1,
            border: `1px solid ${T.border}`,
            padding: '8px 12px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
            <span style={{ fontFamily: FCODE, fontSize: FS.xxs, color: T.cyan }}>
              {art.port_id}
            </span>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
              {art.data_type}
              {art.size_bytes != null && ` · ${formatBytes(art.size_bytes)}`}
            </span>
          </div>
          {art.preview && (
            <div style={{ marginTop: 4 }}>
              <pre style={{
                fontFamily: FCODE,
                fontSize: 10,
                color: T.sec,
                margin: 0,
                maxHeight: 120,
                overflow: 'auto',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}>
                {JSON.stringify(art.preview, null, 2).slice(0, 500)}
              </pre>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Config Table ───────────────────────────────────────────────────────

function ConfigTable({ config, sources }: { config: Record<string, unknown>; sources: Record<string, string> }) {
  const entries = Object.entries(config)
  if (!entries.length) {
    return (
      <div style={{ padding: 12, color: T.dim, fontFamily: F, fontSize: FS.xxs }}>
        No resolved config.
      </div>
    )
  }

  const sourceBadgeColor: Record<string, string> = {
    user: T.cyan,
    workspace: T.purple,
    block_default: T.dim,
  }

  return (
    <div style={{ maxHeight: 400, overflow: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: FCODE, fontSize: 10 }}>
        <thead>
          <tr>
            <th style={{ padding: '4px 8px', textAlign: 'left', color: T.dim, borderBottom: `1px solid ${T.border}`, fontWeight: 500 }}>Key</th>
            <th style={{ padding: '4px 8px', textAlign: 'left', color: T.dim, borderBottom: `1px solid ${T.border}`, fontWeight: 500 }}>Value</th>
            <th style={{ padding: '4px 8px', textAlign: 'left', color: T.dim, borderBottom: `1px solid ${T.border}`, fontWeight: 500 }}>Source</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([key, value]) => {
            const src = sources[key] || '—'
            const srcBase = src.split(':')[0]
            return (
              <tr key={key}>
                <td style={{ padding: '3px 8px', color: T.text, borderBottom: `1px solid ${T.border}08` }}>{key}</td>
                <td style={{ padding: '3px 8px', color: T.sec, borderBottom: `1px solid ${T.border}08`, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {typeof value === 'object' ? JSON.stringify(value) : String(value ?? '')}
                </td>
                <td style={{ padding: '3px 8px', borderBottom: `1px solid ${T.border}08` }}>
                  <span style={{
                    padding: '1px 6px',
                    fontSize: 9,
                    color: sourceBadgeColor[srcBase] || T.sec,
                    background: `${sourceBadgeColor[srcBase] || T.sec}14`,
                    border: `1px solid ${sourceBadgeColor[srcBase] || T.sec}33`,
                  }}>
                    {src}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Timing Panel ───────────────────────────────────────────────────────

function TimingPanel({ node }: { node: ReplayNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '8px 0' }}>
      {[
        { label: 'Started', value: node.started_at ? new Date(node.started_at).toLocaleTimeString() : '—', icon: Clock },
        { label: 'Duration', value: formatDuration(node.duration_ms), icon: Clock },
        { label: 'Memory Peak', value: node.memory_peak_mb != null ? `${node.memory_peak_mb.toFixed(1)} MB` : '—', icon: Cpu },
      ].map(({ label, value, icon: Icon }) => (
        <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
          <Icon size={12} color={T.dim} />
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, minWidth: 80 }}>{label}</span>
          <span style={{ fontFamily: FCODE, fontSize: FS.xs, color: T.text }}>{value}</span>
        </div>
      ))}
    </div>
  )
}

// ── Decision Panel ─────────────────────────────────────────────────────

function DecisionPanel({ node }: { node: ReplayNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '8px 0' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Decision
        </span>
        <span style={{
          padding: '2px 8px',
          fontFamily: F,
          fontSize: FS.xxs,
          color: STATUS_COLOR[node.status] || T.sec,
          background: `${STATUS_COLOR[node.status] || T.sec}14`,
          border: `1px solid ${STATUS_COLOR[node.status] || T.sec}33`,
        }}>
          {DECISION_LABEL[node.decision] || node.decision}
        </span>
      </div>
      {node.decision_reason && (
        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec, lineHeight: 1.5 }}>
          {node.decision_reason}
        </div>
      )}
      {node.iteration != null && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>Iteration</span>
          <span style={{ fontFamily: FCODE, fontSize: FS.xs, color: T.text }}>{node.iteration}</span>
        </div>
      )}
    </div>
  )
}

// ── Error Panel ────────────────────────────────────────────────────────

function ErrorPanel({ error }: { error: ReplayNode['error'] }) {
  if (!error) return null
  return (
    <div style={{
      background: `${T.red}0A`,
      border: `1px solid ${T.red}33`,
      padding: '10px 14px',
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <AlertTriangle size={14} color={T.red} />
        <span style={{ fontFamily: F, fontSize: FS.xs, fontWeight: 600, color: T.red }}>
          {error.title}
        </span>
      </div>
      <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec, lineHeight: 1.5 }}>
        {error.message}
      </div>
      {error.action && (
        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.amber, marginTop: 2 }}>
          Suggested action: {error.action}
        </div>
      )}
    </div>
  )
}

// ── Node Detail Sidebar ────────────────────────────────────────────────

function NodeDetailPanel({
  node,
  onClose,
  onPrev,
  onNext,
  hasPrev,
  hasNext,
  currentIdx,
  total,
}: {
  node: ReplayNode
  onClose: () => void
  onPrev: () => void
  onNext: () => void
  hasPrev: boolean
  hasNext: boolean
  currentIdx: number
  total: number
}) {
  const [tab, setTab] = useState<DetailTab>('outputs')

  // Auto-select error-relevant tab for failed nodes
  useEffect(() => {
    if (node.status === 'failed') setTab('decision')
    else if (node.status === 'not_executed') setTab('decision')
    else setTab('outputs')
  }, [node.node_id, node.status])

  return (
    <div style={{
      width: 380,
      background: T.surface,
      borderLeft: `1px solid ${T.border}`,
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '10px 14px',
        borderBottom: `1px solid ${T.border}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 8,
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{
              width: 20, height: 20,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontFamily: FCODE, fontSize: 10, fontWeight: 700,
              color: T.bg,
              background: STATUS_COLOR[node.status] || T.dim,
              borderRadius: '50%',
              flexShrink: 0,
            }}>
              {node.execution_order + 1}
            </span>
            <span style={{
              fontFamily: FCODE, fontSize: FS.xs, color: T.text, fontWeight: 600,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {node.block_type}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{
              padding: '1px 6px',
              fontFamily: F, fontSize: 9,
              color: STATUS_COLOR[node.status],
              background: `${STATUS_COLOR[node.status]}14`,
              border: `1px solid ${STATUS_COLOR[node.status]}33`,
            }}>
              {STATUS_LABEL[node.status] || node.status}
            </span>
            {node.duration_ms != null && (
              <span style={{ fontFamily: FCODE, fontSize: 9, color: T.dim }}>
                {formatDuration(node.duration_ms)}
              </span>
            )}
          </div>
        </div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.dim, padding: 4 }}>
          <X size={14} />
        </button>
      </div>

      {/* Navigation */}
      <div style={{
        padding: '6px 14px',
        borderBottom: `1px solid ${T.border}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <button
          onClick={onPrev}
          disabled={!hasPrev}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '3px 8px',
            background: hasPrev ? `${T.cyan}14` : 'transparent',
            border: `1px solid ${hasPrev ? T.cyan + '33' : T.border}`,
            color: hasPrev ? T.cyan : T.dim,
            fontFamily: F, fontSize: FS.xxs,
            cursor: hasPrev ? 'pointer' : 'default',
            opacity: hasPrev ? 1 : 0.4,
          }}
        >
          <ChevronLeft size={12} /> Previous
        </button>
        <span style={{ fontFamily: FCODE, fontSize: 9, color: T.dim }}>
          {currentIdx + 1} / {total}
        </span>
        <button
          onClick={onNext}
          disabled={!hasNext}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '3px 8px',
            background: hasNext ? `${T.cyan}14` : 'transparent',
            border: `1px solid ${hasNext ? T.cyan + '33' : T.border}`,
            color: hasNext ? T.cyan : T.dim,
            fontFamily: F, fontSize: FS.xxs,
            cursor: hasNext ? 'pointer' : 'default',
            opacity: hasNext ? 1 : 0.4,
          }}
        >
          Next <ChevronRight size={12} />
        </button>
      </div>

      {/* Error banner for failed nodes */}
      {node.error && (
        <div style={{ padding: '8px 14px' }}>
          <ErrorPanel error={node.error} />
        </div>
      )}

      {/* Not executed banner */}
      {node.status === 'not_executed' && (
        <div style={{
          margin: '8px 14px',
          padding: '8px 12px',
          background: `${T.dim}14`,
          border: `1px solid ${T.border}`,
          fontFamily: F,
          fontSize: FS.xxs,
          color: T.dim,
        }}>
          Not executed — upstream failure
        </div>
      )}

      {/* Tabs */}
      <div style={{
        padding: '6px 14px',
        display: 'flex',
        gap: 4,
        borderBottom: `1px solid ${T.border}`,
        flexWrap: 'wrap',
      }}>
        <TabButton label="Inputs" active={tab === 'inputs'} onClick={() => setTab('inputs')} />
        <TabButton label="Outputs" active={tab === 'outputs'} onClick={() => setTab('outputs')} />
        <TabButton label="Config" active={tab === 'config'} onClick={() => setTab('config')} />
        <TabButton label="Timing" active={tab === 'timing'} onClick={() => setTab('timing')} />
        <TabButton label="Decision" active={tab === 'decision'} onClick={() => setTab('decision')} />
      </div>

      {/* Tab content */}
      <div style={{ flex: 1, overflow: 'auto', padding: '0 14px' }}>
        {tab === 'inputs' && <ArtifactList artifacts={node.input_artifacts} label="Inputs" />}
        {tab === 'outputs' && <ArtifactList artifacts={node.output_artifacts} label="Outputs" />}
        {tab === 'config' && <ConfigTable config={node.resolved_config} sources={node.config_sources} />}
        {tab === 'timing' && <TimingPanel node={node} />}
        {tab === 'decision' && <DecisionPanel node={node} />}
      </div>
    </div>
  )
}

// ── Node List Item ─────────────────────────────────────────────────────

function NodeListItem({
  node,
  isSelected,
  onClick,
}: {
  node: ReplayNode
  isSelected: boolean
  onClick: () => void
}) {
  const color = STATUS_COLOR[node.status] || T.dim
  const StatusIcon = node.status === 'completed' ? CheckCircle2
    : node.status === 'failed' ? AlertTriangle
    : node.status === 'cached' ? Database
    : SkipForward

  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        width: '100%',
        padding: '8px 14px',
        background: isSelected ? `${T.cyan}0A` : 'transparent',
        border: 'none',
        borderLeft: isSelected ? `2px solid ${T.cyan}` : '2px solid transparent',
        borderBottom: `1px solid ${T.border}08`,
        cursor: 'pointer',
        transition: `all ${MOTION.fast}`,
        textAlign: 'left',
      }}
    >
      {/* Execution order badge */}
      <span style={{
        width: 22, height: 22,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: FCODE, fontSize: 10, fontWeight: 700,
        color: T.bg,
        background: color,
        borderRadius: '50%',
        flexShrink: 0,
        boxShadow: isSelected ? `0 0 8px ${T.cyan}44` : 'none',
        animation: isSelected ? 'replay-pulse 2s ease-in-out infinite' : 'none',
      }}>
        {node.execution_order + 1}
      </span>

      {/* Node info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontFamily: FCODE, fontSize: FS.xxs, color: T.text,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {node.block_type}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
          <StatusIcon size={10} color={color} />
          <span style={{ fontFamily: F, fontSize: 9, color }}>
            {STATUS_LABEL[node.status] || node.status}
          </span>
          {node.duration_ms != null && (
            <span style={{ fontFamily: FCODE, fontSize: 9, color: T.dim }}>
              {formatDuration(node.duration_ms)}
            </span>
          )}
        </div>
      </div>
    </button>
  )
}

// ── Iteration Selector ─────────────────────────────────────────────────

function IterationSelector({
  iterations,
  selected,
  onChange,
  label,
}: {
  iterations: number[]
  selected: number
  onChange: (i: number) => void
  label?: string
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px', borderBottom: `1px solid ${T.border}` }}>
      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {label || 'Iteration'}
      </span>
      <select
        value={selected}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{
          fontFamily: FCODE,
          fontSize: FS.xxs,
          color: T.text,
          background: T.surface2,
          border: `1px solid ${T.border}`,
          padding: '2px 6px',
          cursor: 'pointer',
        }}
      >
        {iterations.map((i) => (
          <option key={i} value={i}>#{i + 1}</option>
        ))}
      </select>
    </div>
  )
}

// ── Main Component ─────────────────────────────────────────────────────

export default function RunReplayInspector({
  runId,
  onClose,
}: {
  runId: string
  onClose: () => void
}) {
  const { data, isLoading, error } = useReplayData(runId)
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null)
  const [loopIterationFilter, setLoopIterationFilter] = useState<Record<string, number>>({})

  // Compute filtered node list: for loop body nodes, only show the selected iteration
  const filteredNodes = useMemo(() => {
    if (!data) return []
    return data.nodes.filter((node) => {
      if (node.loop_id && node.iteration != null) {
        const selectedIter = loopIterationFilter[node.loop_id]
        // Default to iteration 0 if no selection
        const filterIter = selectedIter ?? 0
        return node.iteration === filterIter
      }
      return true
    })
  }, [data, loopIterationFilter])

  // Auto-select failure node when entering replay for a failed run
  useEffect(() => {
    if (data && data.status === 'failed') {
      const failIdx = filteredNodes.findIndex((n) => n.status === 'failed')
      if (failIdx >= 0) setSelectedIdx(failIdx)
    }
  }, [data, filteredNodes])

  // Keyboard navigation
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (!filteredNodes.length) return
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedIdx((prev) => {
          if (prev === null) return filteredNodes.length - 1
          return Math.max(0, prev - 1)
        })
      }
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedIdx((prev) => {
          if (prev === null) return 0
          return Math.min(filteredNodes.length - 1, prev + 1)
        })
      }
      if (e.key === 'Escape') {
        if (selectedIdx !== null) setSelectedIdx(null)
        else onClose()
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [filteredNodes, selectedIdx, onClose])

  const selectedNode = selectedIdx !== null ? filteredNodes[selectedIdx] : null
  const hasLoops = data?.loops && data.loops.length > 0

  if (isLoading) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        gap: 8,
        color: T.dim,
      }}>
        <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
        <span style={{ fontFamily: F, fontSize: FS.xs }}>Loading replay data...</span>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        color: T.dim,
        fontFamily: F,
        fontSize: FS.xs,
      }}>
        {error ? `Failed to load replay: ${(error as Error).message}` : 'No replay data available.'}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', height: '100%', background: T.bg }}>
      {/* Pulse animation */}
      <style>{`
        @keyframes replay-pulse {
          0%, 100% { box-shadow: 0 0 0 0 ${T.cyan}44; }
          50% { box-shadow: 0 0 8px 3px ${T.cyan}44; }
        }
      `}</style>

      {/* Left panel: node list */}
      <div style={{
        width: 280,
        display: 'flex',
        flexDirection: 'column',
        borderRight: `1px solid ${T.border}`,
        overflow: 'hidden',
      }}>
        {/* Toolbar */}
        <div style={{
          padding: '10px 14px',
          borderBottom: `1px solid ${T.border}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div>
            <div style={{ fontFamily: F, fontSize: FS.xs, fontWeight: 600, color: T.text }}>
              Replay Inspector
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
              <span style={{
                padding: '1px 6px',
                fontFamily: F,
                fontSize: 9,
                color: STATUS_COLOR[data.status === 'complete' ? 'completed' : data.status] || T.dim,
                background: `${STATUS_COLOR[data.status === 'complete' ? 'completed' : data.status] || T.dim}14`,
                border: `1px solid ${STATUS_COLOR[data.status === 'complete' ? 'completed' : data.status] || T.dim}33`,
              }}>
                {data.status}
              </span>
              <span style={{ fontFamily: FCODE, fontSize: 9, color: T.dim }}>
                {formatDuration(data.duration_ms)}
              </span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 4 }}>
            <button
              onClick={() => downloadSupportBundle(runId)}
              title="Download Support Bundle"
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '4px 8px',
                background: `${T.cyan}14`,
                border: `1px solid ${T.cyan}33`,
                color: T.cyan,
                fontFamily: F,
                fontSize: 9,
                cursor: 'pointer',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
              }}
            >
              <Download size={10} />
              Bundle
            </button>
            <button
              onClick={onClose}
              style={{
                background: 'none', border: `1px solid ${T.border}`,
                color: T.dim, padding: '4px 6px', cursor: 'pointer',
              }}
            >
              <X size={12} />
            </button>
          </div>
        </div>

        {/* Loop iteration selector */}
        {hasLoops && data.loops.map((loop) => (
          <IterationSelector
            key={loop.controller_id}
            iterations={loop.iterations}
            selected={loopIterationFilter[loop.controller_id] ?? 0}
            onChange={(iter) => {
              setLoopIterationFilter((prev) => ({ ...prev, [loop.controller_id]: iter }))
              setSelectedIdx(null)
            }}
            label={`Loop ${loop.controller_id.slice(0, 8)}`}
          />
        ))}

        {/* Node list */}
        <div style={{ flex: 1, overflow: 'auto' }}>
          {filteredNodes.map((node, idx) => (
            <NodeListItem
              key={`${node.node_id}-${node.iteration ?? ''}`}
              node={node}
              isSelected={selectedIdx === idx}
              onClick={() => setSelectedIdx(idx)}
            />
          ))}
        </div>

        {/* Keyboard hint */}
        <div style={{
          padding: '6px 14px',
          borderTop: `1px solid ${T.border}`,
          fontFamily: F,
          fontSize: 9,
          color: T.dim,
          textAlign: 'center',
        }}>
          Arrow keys to navigate · Esc to close
        </div>
      </div>

      {/* Right panel: detail */}
      {selectedNode ? (
        <NodeDetailPanel
          node={selectedNode}
          onClose={() => setSelectedIdx(null)}
          onPrev={() => setSelectedIdx((prev) => prev !== null ? Math.max(0, prev - 1) : 0)}
          onNext={() => setSelectedIdx((prev) => prev !== null ? Math.min(filteredNodes.length - 1, prev + 1) : 0)}
          hasPrev={selectedIdx !== null && selectedIdx > 0}
          hasNext={selectedIdx !== null && selectedIdx < filteredNodes.length - 1}
          currentIdx={selectedIdx ?? 0}
          total={filteredNodes.length}
        />
      ) : (
        <div style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: T.dim,
          fontFamily: F,
          fontSize: FS.xs,
        }}>
          Select a node to inspect
        </div>
      )}
    </div>
  )
}
