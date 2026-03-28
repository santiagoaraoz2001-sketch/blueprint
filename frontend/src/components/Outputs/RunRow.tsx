import { useState } from 'react'
import { T, F, FD, FS } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { usePipelineStore } from '@/stores/pipelineStore'
import {
  ChevronRight,
  ChevronDown,
  GitBranch,
  Activity,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  Ban,
} from 'lucide-react'
import ArtifactBrowser from '@/components/Artifacts/ArtifactBrowser'
import type { RunWithArtifacts } from '@/hooks/useOutputs'

const STATUS_CONFIG: Record<string, { color: string; icon: typeof CheckCircle2; label: string }> = {
  complete:  { color: T.green,  icon: CheckCircle2, label: 'COMPLETE' },
  running:   { color: T.green,  icon: Loader2,      label: 'RUNNING' },
  failed:    { color: T.red,    icon: XCircle,       label: 'FAILED' },
  cancelled: { color: T.amber,  icon: Ban,           label: 'CANCELLED' },
  pending:   { color: T.dim,    icon: Clock,         label: 'PENDING' },
  paused:    { color: T.amber,  icon: Clock,         label: 'PAUSED' },
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '--'
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffH = diffMs / (1000 * 60 * 60)

  if (diffH < 1) return `${Math.round(diffMs / 60000)}m ago`
  if (diffH < 24) return `${Math.round(diffH)}h ago`
  if (diffH < 48) return 'Yesterday'
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

interface RunRowProps {
  run: RunWithArtifacts
  selected: boolean
  onToggleSelect: (id: string) => void
}

export default function RunRow({ run, selected, onToggleSelect }: RunRowProps) {
  const [expanded, setExpanded] = useState(false)
  const cfg = STATUS_CONFIG[run.status] || STATUS_CONFIG.pending
  const StatusIcon = cfg.icon
  const metrics = run.metrics || {}
  const metricKeys = Object.keys(metrics).filter((k) => typeof metrics[k] === 'number')

  const handleOpenPipeline = async () => {
    await usePipelineStore.getState().loadPipeline(run.pipeline_id)
    useUIStore.getState().setView('editor')
  }

  const handleMonitor = () => {
    useUIStore.getState().openMonitor(run.id)
  }

  const btnStyle: React.CSSProperties = {
    padding: '3px 10px',
    background: `${T.cyan}14`,
    border: `1px solid ${T.cyan}33`,
    color: T.cyan,
    fontFamily: F,
    fontSize: FS.xxs,
    letterSpacing: '0.06em',
    textTransform: 'uppercase',
    cursor: 'pointer',
    transition: 'all 0.15s',
  }

  return (
    <div
      style={{
        borderBottom: `1px solid ${T.border}`,
        transition: 'background 0.1s',
      }}
    >
      {/* Collapsed row */}
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '10px 16px',
          cursor: 'pointer',
          background: expanded ? T.surface1 : 'transparent',
        }}
        onMouseEnter={(e) => {
          if (!expanded) e.currentTarget.style.background = `${T.surface1}`
        }}
        onMouseLeave={(e) => {
          if (!expanded) e.currentTarget.style.background = 'transparent'
        }}
      >
        {/* Selection checkbox */}
        <div
          onClick={(e) => { e.stopPropagation(); onToggleSelect(run.id) }}
          style={{
            width: 14,
            height: 14,
            border: `1px solid ${selected ? T.cyan : T.border}`,
            background: selected ? `${T.cyan}22` : 'transparent',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            cursor: 'pointer',
            transition: 'all 0.1s',
          }}
        >
          {selected && <div style={{ width: 6, height: 6, background: T.cyan }} />}
        </div>

        {/* Expand chevron */}
        {expanded
          ? <ChevronDown size={12} color={T.dim} style={{ flexShrink: 0 }} />
          : <ChevronRight size={12} color={T.dim} style={{ flexShrink: 0 }} />
        }

        {/* Status icon */}
        <StatusIcon
          size={12}
          color={cfg.color}
          strokeWidth={1.8}
          style={{
            flexShrink: 0,
            ...(run.status === 'running' ? { animation: 'spin 1s linear infinite' } : {}),
          }}
        />

        {/* Status label */}
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: cfg.color,
            letterSpacing: '0.06em',
            width: 68,
            flexShrink: 0,
          }}
        >
          {cfg.label}
        </span>

        {/* Pipeline name */}
        <span
          style={{
            fontFamily: FD,
            fontSize: FS.sm,
            color: T.text,
            fontWeight: 500,
            flex: 1,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {run.pipeline_name || 'Untitled Pipeline'}
        </span>

        {/* Duration */}
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, flexShrink: 0, minWidth: 48, textAlign: 'right' }}>
          {formatDuration(run.duration_seconds)}
        </span>

        {/* Artifact count */}
        {run.artifacts.length > 0 && (
          <span
            style={{
              fontFamily: F,
              fontSize: FS.xxs,
              color: T.sec,
              padding: '1px 6px',
              background: T.surface3,
              flexShrink: 0,
            }}
          >
            {run.artifacts.length} artifact{run.artifacts.length !== 1 ? 's' : ''}
          </span>
        )}

        {/* Timestamp */}
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.muted, flexShrink: 0, minWidth: 64, textAlign: 'right' }}>
          {formatDate(run.started_at)}
        </span>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div
          style={{
            padding: '0 16px 14px 56px',
            background: T.surface1,
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
          }}
        >
          {/* Artifacts — full browser with grouped view and previews */}
          {run.artifacts.length > 0 && (
            <div>
              <div
                style={{
                  fontFamily: F,
                  fontSize: FS.xxs,
                  color: T.dim,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  marginBottom: 4,
                }}
              >
                ARTIFACTS
              </div>
              <ArtifactBrowser runId={run.id} />
            </div>
          )}

          {/* Metrics */}
          {metricKeys.length > 0 && (
            <div>
              <div
                style={{
                  fontFamily: F,
                  fontSize: FS.xxs,
                  color: T.dim,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  marginBottom: 4,
                }}
              >
                METRICS
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
                {metricKeys.slice(0, 8).map((key) => (
                  <div key={key} style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
                    <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>{key}</span>
                    <span style={{ fontFamily: F, fontSize: FS.xs, color: T.text, fontWeight: 500 }}>
                      {typeof metrics[key] === 'number'
                        ? (metrics[key] as number) % 1 === 0
                          ? String(metrics[key])
                          : (metrics[key] as number).toFixed(4)
                        : String(metrics[key])}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Error */}
          {run.error_message && (
            <div>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  color: T.red,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  marginBottom: 4,
                }}
              >
                <AlertTriangle size={10} />
                ERROR
              </div>
              <pre
                style={{
                  fontFamily: F,
                  fontSize: FS.xxs,
                  color: T.red,
                  background: `${T.red}08`,
                  border: `1px solid ${T.red}22`,
                  padding: '6px 8px',
                  margin: 0,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  maxHeight: 120,
                  overflow: 'auto',
                  opacity: 0.85,
                }}
              >
                {run.error_message}
              </pre>
            </div>
          )}

          {/* Run ID */}
          <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.muted, opacity: 0.6 }}>
            {run.id}
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', gap: 8, paddingTop: 2 }}>
            <button
              onClick={handleOpenPipeline}
              style={btnStyle}
              onMouseEnter={(e) => { e.currentTarget.style.background = `${T.cyan}22`; e.currentTarget.style.borderColor = `${T.cyan}55` }}
              onMouseLeave={(e) => { e.currentTarget.style.background = `${T.cyan}14`; e.currentTarget.style.borderColor = `${T.cyan}33` }}
            >
              <GitBranch size={9} style={{ marginRight: 3, verticalAlign: -1 }} />
              Open Pipeline
            </button>
            <button
              onClick={handleMonitor}
              style={btnStyle}
              onMouseEnter={(e) => { e.currentTarget.style.background = `${T.cyan}22`; e.currentTarget.style.borderColor = `${T.cyan}55` }}
              onMouseLeave={(e) => { e.currentTarget.style.background = `${T.cyan}14`; e.currentTarget.style.borderColor = `${T.cyan}33` }}
            >
              <Activity size={9} style={{ marginRight: 3, verticalAlign: -1 }} />
              Monitor
            </button>
          </div>
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
