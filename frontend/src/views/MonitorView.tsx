import { useState, useEffect, useCallback } from 'react'
import { T, F, FD, FS, STATUS_COLORS } from '@/lib/design-tokens'
import { useRunStore } from '@/stores/runStore'
import { useUIStore } from '@/stores/uiStore'
import { usePipelineStore } from '@/stores/pipelineStore'
import { api } from '@/api/client'
import { useSettingsStore } from '@/stores/settingsStore'
import { DEMO_RUNS } from '@/lib/demo-data'
import StatusBadge from '@/components/shared/StatusBadge'
import EmptyState from '@/components/shared/EmptyState'
import ProgressBar from '@/components/shared/ProgressBar'
import {
  Activity, Square, RotateCcw, ChevronDown,
  Clock, Cpu, AlertTriangle, CheckCircle2, XCircle,
  ChevronRight,
} from 'lucide-react'
import toast from 'react-hot-toast'

interface RunRecord {
  id: string
  pipeline_id: string
  status: string
  started_at: string
  completed_at: string | null
  error_message?: string | null
  metrics: Record<string, any>
}

function formatDuration(start: string, end: string | null): string {
  const s = new Date(start).getTime()
  const e = end ? new Date(end).getTime() : Date.now()
  const diff = Math.floor((e - s) / 1000)
  if (diff < 60) return `${diff}s`
  const m = Math.floor(diff / 60)
  const sec = diff % 60
  return `${m}m ${sec}s`
}

export default function MonitorView() {
  const selectedRunId = useUIStore((s) => s.selectedRunId)
  const setView = useUIStore((s) => s.setView)

  const activeRunId = useRunStore((s) => s.activeRunId)
  const runStatus = useRunStore((s) => s.status)
  const overallProgress = useRunStore((s) => s.overallProgress)
  const nodeStatuses = useRunStore((s) => s.nodeStatuses)
  const logs = useRunStore((s) => s.logs)
  const error = useRunStore((s) => s.error)
  const stopRun = useRunStore((s) => s.stopRun)

  const demoMode = useSettingsStore((s) => s.demoMode)

  const [runs, setRuns] = useState<RunRecord[]>([])
  const [selectedRun, setSelectedRun] = useState<RunRecord | null>(null)
  const [showRunSelector, setShowRunSelector] = useState(false)
  const [showLogs, setShowLogs] = useState(true)

  const fetchRuns = useCallback(async () => {
    if (demoMode) {
      const demoRuns: RunRecord[] = DEMO_RUNS.map((r) => ({
        id: r.id,
        pipeline_id: r.pipeline_id,
        status: r.status,
        started_at: r.started_at,
        completed_at: r.completed_at,
        metrics: r.metrics as Record<string, any>,
      }))
      setRuns(demoRuns)
      if (selectedRunId) {
        setSelectedRun(demoRuns.find((r) => r.id === selectedRunId) || demoRuns[0] || null)
      } else {
        setSelectedRun(demoRuns[0] || null)
      }
      return
    }
    try {
      const data = await api.get<RunRecord[]>('/runs?limit=50')
      setRuns(data)
      if (selectedRunId) {
        setSelectedRun(data.find((r) => r.id === selectedRunId) || data[0] || null)
      } else {
        setSelectedRun(data[0] || null)
      }
    } catch {
      // Use active run state if API fails
    }
  }, [demoMode, selectedRunId])

  useEffect(() => {
    fetchRuns()
  }, [fetchRuns])

  // Determine what to display: active live run or historical run
  const isLiveRun = runStatus === 'running' && activeRunId
  const displayStatus = isLiveRun ? runStatus : (selectedRun?.status || 'idle')
  const displayRunId = isLiveRun ? activeRunId : (selectedRun?.id || null)

  const handleStopRun = async () => {
    await stopRun()
    toast.success('Run cancelled')
  }

  const handleReRun = () => {
    const pipelineId = usePipelineStore.getState().id
    if (pipelineId) {
      useRunStore.getState().startRun(pipelineId)
      toast.success('Re-running pipeline')
    } else {
      toast.error('No pipeline loaded to re-run')
    }
  }

  const statusColor = STATUS_COLORS[displayStatus] || T.dim

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ padding: '12px 16px', borderBottom: `1px solid ${T.border}`, display: 'flex', alignItems: 'center', gap: 12 }}>
        <Activity size={14} color={T.cyan} />
        <h2 style={{ fontFamily: FD, fontSize: FS.h2, fontWeight: 600, color: T.text, margin: 0, letterSpacing: '0.04em' }}>
          MONITOR
        </h2>

        <div style={{ flex: 1 }} />

        {/* Run selector */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setShowRunSelector(!showRunSelector)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '4px 10px', background: T.surface2, border: `1px solid ${T.border}`,
              color: T.sec, fontFamily: F, fontSize: FS.xs,
            }}
          >
            {displayRunId ? `Run: ${displayRunId.slice(0, 12)}` : 'Select Run'}
            <ChevronDown size={10} />
          </button>
          {showRunSelector && (
            <div style={{
              position: 'absolute', top: '100%', right: 0, marginTop: 4,
              background: T.surface3, border: `1px solid ${T.borderHi}`,
              boxShadow: `0 8px 24px ${T.shadowHeavy}`, zIndex: 100,
              maxHeight: 240, overflow: 'auto', minWidth: 260,
            }}>
              {runs.map((run) => (
                <div
                  key={run.id}
                  onClick={() => { setSelectedRun(run); setShowRunSelector(false) }}
                  style={{
                    padding: '8px 12px', cursor: 'pointer',
                    background: run.id === displayRunId ? `${T.cyan}12` : 'transparent',
                    borderBottom: `1px solid ${T.border}`,
                    display: 'flex', alignItems: 'center', gap: 8,
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = T.surface4 }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = run.id === displayRunId ? `${T.cyan}12` : 'transparent' }}
                >
                  <StatusBadge status={run.status} />
                  <span style={{ fontFamily: F, fontSize: FS.xs, color: T.sec }}>{run.id.slice(0, 16)}</span>
                  <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginLeft: 'auto' }}>
                    {new Date(run.started_at).toLocaleDateString()}
                  </span>
                </div>
              ))}
              {runs.length === 0 && (
                <div style={{ padding: 12, textAlign: 'center', fontFamily: F, fontSize: FS.xs, color: T.dim }}>
                  No runs found
                </div>
              )}
            </div>
          )}
        </div>

        {/* Actions */}
        {isLiveRun && (
          <button
            onClick={handleStopRun}
            style={{
              display: 'flex', alignItems: 'center', gap: 4, padding: '4px 10px',
              background: `${T.red}1A`, border: `1px solid ${T.red}50`, color: T.red,
              fontFamily: F, fontSize: FS.xs, fontWeight: 600, letterSpacing: '0.08em',
            }}
          >
            <Square size={10} />
            STOP
          </button>
        )}
        <button
          onClick={handleReRun}
          style={{
            display: 'flex', alignItems: 'center', gap: 4, padding: '4px 10px',
            background: `${T.cyan}1A`, border: `1px solid ${T.cyan}50`, color: T.cyan,
            fontFamily: F, fontSize: FS.xs, fontWeight: 600, letterSpacing: '0.08em',
          }}
        >
          <RotateCcw size={10} />
          RE-RUN
        </button>
      </div>

      {!displayRunId ? (
        <EmptyState
          icon={Activity}
          title="No run selected"
          description="Start a pipeline run or select a past run to monitor"
          action={{ label: 'Go to Pipeline Editor', onClick: () => setView('editor') }}
        />
      ) : (
        <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
          {/* Status banner */}
          <div style={{
            padding: '14px 16px', background: `${statusColor}0A`, border: `1px solid ${statusColor}33`,
            marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12,
          }}>
            {displayStatus === 'running' && <Cpu size={16} color={statusColor} style={{ animation: 'spin 2s linear infinite' }} />}
            {displayStatus === 'complete' && <CheckCircle2 size={16} color={statusColor} />}
            {displayStatus === 'failed' && <XCircle size={16} color={statusColor} />}
            {displayStatus === 'cancelled' && <AlertTriangle size={16} color={statusColor} />}
            {!['running', 'complete', 'failed', 'cancelled'].includes(displayStatus) && <Clock size={16} color={statusColor} />}

            <div style={{ flex: 1 }}>
              <div style={{ fontFamily: FD, fontSize: FS.md, color: T.text, fontWeight: 600 }}>
                Run {displayRunId?.slice(0, 16)}
              </div>
              <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, marginTop: 2 }}>
                {selectedRun && `Started ${new Date(selectedRun.started_at).toLocaleString()}`}
                {selectedRun?.completed_at && ` • Duration: ${formatDuration(selectedRun.started_at, selectedRun.completed_at)}`}
              </div>
            </div>

            <StatusBadge status={displayStatus} size="md" />
          </div>

          {/* Progress bar for live runs */}
          {isLiveRun && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, letterSpacing: '0.08em' }}>PROGRESS</span>
                <span style={{ fontFamily: F, fontSize: FS.xs, color: T.cyan }}>{Math.round(overallProgress * 100)}%</span>
              </div>
              <ProgressBar value={overallProgress * 100} />
            </div>
          )}

          {/* Node statuses for live runs */}
          {isLiveRun && Object.keys(nodeStatuses).length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, letterSpacing: '0.12em', fontWeight: 900 }}>
                NODE STATUS
              </span>
              <div style={{ display: 'grid', gap: 6, marginTop: 8 }}>
                {Object.values(nodeStatuses).map((ns) => (
                  <div key={ns.nodeId} style={{
                    padding: '8px 12px', background: T.surface1, border: `1px solid ${T.border}`,
                    display: 'flex', alignItems: 'center', gap: 8,
                  }}>
                    <StatusBadge status={ns.status} />
                    <span style={{ fontFamily: F, fontSize: FS.sm, color: T.sec }}>{ns.nodeId}</span>
                    {ns.status === 'running' && (
                      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.cyan, marginLeft: 'auto' }}>
                        {Math.round(ns.progress * 100)}%
                      </span>
                    )}
                    {ns.error && (
                      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.red, marginLeft: 'auto' }}>
                        {ns.error.slice(0, 60)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Metrics for completed runs */}
          {selectedRun && selectedRun.metrics && Object.keys(selectedRun.metrics).length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, letterSpacing: '0.12em', fontWeight: 900 }}>
                METRICS
              </span>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 8, marginTop: 8 }}>
                {Object.entries(selectedRun.metrics).map(([key, value]) => (
                  <div key={key} style={{
                    padding: '10px 12px', background: T.surface1, border: `1px solid ${T.border}`,
                  }}>
                    <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                      {key}
                    </div>
                    <div style={{ fontFamily: FD, fontSize: FS.lg, color: T.cyan, fontWeight: 700, marginTop: 4 }}>
                      {typeof value === 'number' ? value.toFixed(4) : String(value)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Error display */}
          {(error || selectedRun?.error_message) && (
            <ErrorTraceback error={error || selectedRun?.error_message || ''} status={displayStatus} />
          )}

          {/* Logs */}
          {(isLiveRun || logs.length > 0) && (
            <div>
              <button
                onClick={() => setShowLogs(!showLogs)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  background: 'none', border: 'none', color: T.dim, fontFamily: F, fontSize: FS.xs,
                  letterSpacing: '0.12em', fontWeight: 900, padding: 0, marginBottom: 8,
                }}
              >
                <ChevronRight size={10} style={{ transform: showLogs ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }} />
                LOGS ({logs.length})
              </button>
              {showLogs && (
                <div style={{
                  background: T.surface0, border: `1px solid ${T.border}`, padding: 12,
                  maxHeight: 300, overflow: 'auto', fontFamily: F, fontSize: FS.xs, color: T.sec,
                  lineHeight: 1.6, whiteSpace: 'pre-wrap',
                }}>
                  {logs.length > 0 ? logs.join('\n') : 'No logs yet...'}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/** Collapsible error traceback component */
function ErrorTraceback({ error, status }: { error: string; status: string }) {
  const [expanded, setExpanded] = useState(false)
  const isCancelled = status === 'cancelled' || error === 'Stopped by user'
  const displayStatus = isCancelled ? 'cancelled' : 'failed'
  const color = STATUS_COLORS[displayStatus] || T.red

  return (
    <div style={{ marginBottom: 16 }}>
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          display: 'flex', alignItems: 'center', gap: 6, width: '100%',
          padding: '10px 12px', background: `${color}0A`, border: `1px solid ${color}33`,
          color, fontFamily: F, fontSize: FS.xs, fontWeight: 600, textAlign: 'left',
        }}
      >
        {isCancelled ? <AlertTriangle size={12} /> : <XCircle size={12} />}
        <StatusBadge status={displayStatus} />
        <span style={{ flex: 1 }}>
          {isCancelled ? 'Run was cancelled by user' : 'Run failed — click to expand traceback'}
        </span>
        <ChevronRight size={10} style={{ transform: expanded ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }} />
      </button>
      {expanded && (
        <div style={{
          padding: 12, background: T.surface0, border: `1px solid ${color}33`, borderTop: 'none',
          fontFamily: F, fontSize: FS.xs, color: T.sec, whiteSpace: 'pre-wrap', lineHeight: 1.6,
          maxHeight: 300, overflow: 'auto',
        }}>
          {error}
        </div>
      )}
    </div>
  )
}
