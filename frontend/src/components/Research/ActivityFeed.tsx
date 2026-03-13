import { useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { useProjectStore } from '@/stores/projectStore'
import { useMetricsStore } from '@/stores/metricsStore'
import type { DashboardStats } from '@/stores/metricsStore'
import PaperBadge from './PaperBadge'
import ProgressBar from '@/components/shared/ProgressBar'
import { runMetricsToTable } from '@/services/metricsBridge'
import {
  Activity,
  CheckCircle2,
  XCircle,
  Play,
  Square,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Link2,
  TableProperties,
} from 'lucide-react'
import toast from 'react-hot-toast'

interface ActivityFeedProps {
  dashboard: DashboardStats
}

function MiniSparkline({ data }: { data: number[] }) {
  if (data.length < 2) return null
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const w = 80
  const h = 20
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w
    const y = h - ((v - min) / range) * h
    return `${x},${y}`
  }).join(' ')

  return (
    <svg width={w} height={h} style={{ flexShrink: 0 }}>
      <polyline
        points={points}
        fill="none"
        stroke={T.cyan}
        strokeWidth={1.2}
        strokeLinejoin="round"
      />
    </svg>
  )
}

function SectionHeader({ title, count }: { title: string; count: number }) {
  return (
    <div
      style={{
        fontFamily: F,
        fontSize: FS.xxs,
        color: T.dim,
        letterSpacing: '0.14em',
        textTransform: 'uppercase',
        padding: '10px 0 6px',
        borderBottom: `1px solid ${T.border}`,
        display: 'flex',
        alignItems: 'center',
        gap: 6,
      }}
    >
      {title}
      {count > 0 && (
        <span style={{ color: T.sec, fontWeight: 600 }}>{count}</span>
      )}
    </div>
  )
}

function formatEta(seconds: number | null): string {
  if (seconds == null) return ''
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  return `${(seconds / 3600).toFixed(1)}h`
}

function formatComputeTime(hours: number): string {
  if (hours < 1) return `${Math.round(hours * 60)}m`
  return `${hours.toFixed(1)}h`
}

export default function ActivityFeed({ dashboard }: ActivityFeedProps) {
  const setView = useUIStore((s) => s.setView)
  const projects = useProjectStore((s) => s.projects)
  const { cancelRun, assignRunToProject } = useMetricsStore()
  const [expandedTracebacks, setExpandedTracebacks] = useState<Set<string>>(new Set())
  const [confirmCancel, setConfirmCancel] = useState<string | null>(null)

  const toggleTraceback = (id: string) => {
    setExpandedTracebacks((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const btnStyle: React.CSSProperties = {
    padding: '3px 8px',
    background: `${T.cyan}14`,
    border: `1px solid ${T.cyan}33`,
    color: T.cyan,
    fontFamily: F,
    fontSize: FS.xxs,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    transition: 'all 0.15s',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {/* RUNNING */}
      <SectionHeader title="Running" count={dashboard.running_runs.length} />
      {dashboard.running_runs.length === 0 && (
        <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, padding: '8px 0' }}>
          No experiments running
        </div>
      )}
      {dashboard.running_runs.map((run) => (
        <div
          key={run.id}
          style={{
            padding: '8px 0',
            borderBottom: `1px solid ${T.border}`,
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <Activity size={12} color={T.cyan} />
            {run.paper_number && (
              <PaperBadge paperNumber={run.paper_number} status="active" />
            )}
            <span style={{ fontFamily: F, fontSize: FS.sm, color: T.text, flex: 1 }}>
              {run.name}
            </span>
            {run.current_block && (
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                {run.current_block}
              </span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ flex: 1 }}>
              <ProgressBar value={run.progress * 100} color={T.cyan} height={3} showLabel label={`${Math.round(run.progress * 100)}%`} />
            </div>
            <MiniSparkline data={run.loss_history} />
            {run.eta != null && (
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                ETA {formatEta(run.eta)}
              </span>
            )}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              onClick={() => setView('results')}
              style={btnStyle}
              onMouseEnter={(e) => { e.currentTarget.style.background = `${T.cyan}22` }}
              onMouseLeave={(e) => { e.currentTarget.style.background = `${T.cyan}14` }}
            >
              <ExternalLink size={9} style={{ marginRight: 3, verticalAlign: 'middle' }} />
              Monitor
            </button>
            {confirmCancel === run.id ? (
              <button
                onClick={() => { cancelRun(run.id); setConfirmCancel(null) }}
                style={{ ...btnStyle, background: `${T.red}22`, borderColor: `${T.red}55`, color: T.red }}
              >
                Confirm Stop
              </button>
            ) : (
              <button
                onClick={() => setConfirmCancel(run.id)}
                style={{ ...btnStyle, borderColor: `${T.red}33`, color: T.red }}
                onMouseEnter={(e) => { e.currentTarget.style.background = `${T.red}14` }}
                onMouseLeave={(e) => { e.currentTarget.style.background = `${T.cyan}14` }}
              >
                <Square size={9} style={{ marginRight: 3, verticalAlign: 'middle' }} />
                Stop
              </button>
            )}
          </div>
        </div>
      ))}

      {/* RECENTLY COMPLETED */}
      <SectionHeader title="Recently Completed" count={dashboard.recent_completed.length} />
      {dashboard.recent_completed.length === 0 && (
        <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, padding: '8px 0' }}>
          No recent completions
        </div>
      )}
      {dashboard.recent_completed.map((run) => {
        const ok = run.status === 'complete'
        return (
          <div
            key={run.id}
            style={{
              padding: '8px 0',
              borderBottom: `1px solid ${T.border}`,
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              {ok
                ? <CheckCircle2 size={12} color={T.green} />
                : <XCircle size={12} color={T.red} />
              }
              {run.paper_number && (
                <PaperBadge paperNumber={run.paper_number} status={ok ? 'complete' : 'blocked'} />
              )}
              <span style={{ fontFamily: F, fontSize: FS.sm, color: T.text, flex: 1 }}>
                {run.name}
              </span>
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                {formatComputeTime(run.compute_time)}
              </span>
            </div>
            {ok && (run.loss != null || run.accuracy != null) && (
              <div style={{ display: 'flex', gap: 12, paddingLeft: 20 }}>
                {run.loss != null && (
                  <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
                    loss: {run.loss.toFixed(3)}
                  </span>
                )}
                {run.accuracy != null && (
                  <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
                    acc: {(run.accuracy * 100).toFixed(1)}%
                  </span>
                )}
              </div>
            )}
            {!ok && run.error && (
              <div style={{ paddingLeft: 20 }}>
                <div
                  style={{
                    fontFamily: F,
                    fontSize: FS.xxs,
                    color: T.red,
                    cursor: run.traceback ? 'pointer' : 'default',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                  }}
                  onClick={() => run.traceback && toggleTraceback(run.id)}
                >
                  {run.traceback && (expandedTracebacks.has(run.id) ? <ChevronDown size={10} /> : <ChevronRight size={10} />)}
                  {run.error}
                </div>
                {run.traceback && expandedTracebacks.has(run.id) && (
                  <pre
                    style={{
                      fontFamily: F,
                      fontSize: FS.xxs,
                      color: T.dim,
                      background: T.surface0,
                      padding: '6px 8px',
                      marginTop: 4,
                      overflow: 'auto',
                      maxHeight: 150,
                      whiteSpace: 'pre-wrap',
                      border: `1px solid ${T.border}`,
                    }}
                  >
                    {run.traceback}
                  </pre>
                )}
              </div>
            )}
            <div style={{ display: 'flex', gap: 6, paddingLeft: 20 }}>
              <button
                onClick={() => setView('results')}
                style={btnStyle}
                onMouseEnter={(e) => { e.currentTarget.style.background = `${T.cyan}22` }}
                onMouseLeave={(e) => { e.currentTarget.style.background = `${T.cyan}14` }}
              >
                Results
              </button>
              {ok && (
                <button
                  onClick={async () => {
                    try {
                      await runMetricsToTable(run.id, run.name)
                      setView('data')
                    } catch (e: any) {
                      toast.error(e.message || 'No metrics available')
                    }
                  }}
                  style={btnStyle}
                  onMouseEnter={(e) => { e.currentTarget.style.background = `${T.cyan}22` }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = `${T.cyan}14` }}
                >
                  <TableProperties size={9} style={{ marginRight: 3, verticalAlign: 'middle' }} />
                  Analyze
                </button>
              )}
            </div>
          </div>
        )
      })}

      {/* UNASSIGNED RUNS */}
      <SectionHeader title="Unassigned Runs" count={dashboard.unassigned_runs.length} />
      {dashboard.unassigned_runs.length === 0 && (
        <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, padding: '8px 0' }}>
          All runs are assigned
        </div>
      )}
      {dashboard.unassigned_runs.map((run) => (
        <div
          key={run.id}
          style={{
            padding: '8px 0',
            borderBottom: `1px solid ${T.border}`,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            flexWrap: 'wrap',
          }}
        >
          <Link2 size={12} color={T.dim} />
          <span style={{ fontFamily: F, fontSize: FS.sm, color: T.text, flex: 1 }}>
            {run.name}
          </span>
          {run.loss != null && (
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
              loss: {run.loss.toFixed(3)}
            </span>
          )}
          {run.accuracy != null && (
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
              acc: {(run.accuracy * 100).toFixed(1)}%
            </span>
          )}
          <select
            defaultValue=""
            onChange={(e) => {
              if (e.target.value) assignRunToProject(run.id, e.target.value)
            }}
            style={{
              padding: '2px 6px',
              background: T.surface2,
              border: `1px solid ${T.border}`,
              color: T.sec,
              fontFamily: F,
              fontSize: FS.xxs,
              cursor: 'pointer',
            }}
          >
            <option value="" disabled>Assign to Paper</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.paper_number || p.name}
              </option>
            ))}
          </select>
        </div>
      ))}

      {/* READY TO RUN */}
      <SectionHeader title="Ready to Run" count={dashboard.ready_to_run.length} />
      {dashboard.ready_to_run.length === 0 && (
        <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, padding: '8px 0' }}>
          No experiments queued
        </div>
      )}
      {dashboard.ready_to_run.map((run) => (
        <div
          key={run.id}
          style={{
            padding: '8px 0',
            borderBottom: `1px solid ${T.border}`,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            flexWrap: 'wrap',
          }}
        >
          <Play size={12} color={T.green} />
          {run.paper_number && (
            <PaperBadge paperNumber={run.paper_number} status="queued" />
          )}
          <span style={{ fontFamily: F, fontSize: FS.sm, color: T.text, flex: 1 }}>
            {run.experiment_name}
          </span>
          {run.estimated_time != null && (
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
              ~{formatComputeTime(run.estimated_time)}
            </span>
          )}
          <button
            onClick={() => setView('editor')}
            style={btnStyle}
            onMouseEnter={(e) => { e.currentTarget.style.background = `${T.cyan}22` }}
            onMouseLeave={(e) => { e.currentTarget.style.background = `${T.cyan}14` }}
          >
            Launch
          </button>
        </div>
      ))}
    </div>
  )
}
