import { useRef, useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore } from '@/stores/metricsStore'
import { useRunMonitor } from '@/hooks/useRunMonitor'
import { useUIStore } from '@/stores/uiStore'
import StatusBadge from '@/components/shared/StatusBadge'
import StatsBar from './StatsBar'
import { LineChart, Line, ResponsiveContainer } from 'recharts'
import { Activity, Square, ChevronDown, ChevronRight } from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────

interface RunSummary {
  id: string
  name: string
  pipelineId?: string
  status: 'running' | 'complete' | 'failed' | 'cancelled'
  progress: number
  eta: number | null
  errorMessage?: string
  completedAt?: string
  projectId?: string | null
}

interface ActivityFeedProps {
  /** All runs from the backend */
  runs: RunSummary[]
  /** Callback counts for stats bar */
  stats?: {
    blockedCount: number
    computeHours: number
  }
  onBlockedClick?: () => void
}

// ── Mini Sparkline ────────────────────────────────────────────────

function MiniSparkline({ runId }: { runId: string }) {
  const metricsStore = useMetricsStore
  const run = metricsStore((s) => s.runs[runId])
  if (!run) return null

  // Find first block with train/loss data
  const blockWithLoss = Object.values(run.blocks).find((b) => b.metrics['train/loss']?.length > 0)
  if (!blockWithLoss) return null

  const series = blockWithLoss.metrics['train/loss'].slice(-50)
  const data = series.map((p, i) => ({ x: i, v: p.value }))

  return (
    <div style={{ width: 60, height: 24 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <Line type="monotone" dataKey="v" stroke={T.cyan} dot={false} strokeWidth={1} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── Running Experiment Card ───────────────────────────────────────

function RunningCard({ run }: { run: RunSummary }) {
  const { progress, eta } = useRunMonitor(run.id, true)
  const setView = useUIStore((s) => s.setView)

  const displayProgress = progress || run.progress
  const displayEta = eta ?? run.eta

  return (
    <div style={{
      padding: '10px 12px', background: T.surface1, border: `1px solid ${T.borderHi}`,
      marginBottom: 6,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <Activity size={10} color={T.cyan} style={{ animation: 'pulse 2s ease-in-out infinite' }} />
        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.text, fontWeight: 700, flex: 1 }}>
          {run.name}
        </span>
        <MiniSparkline runId={run.id} />
        <StatusBadge status="running" />
      </div>

      {/* Progress bar with animation */}
      <div style={{ marginBottom: 6 }}>
        <div style={{
          height: 4, background: T.surface4, overflow: 'hidden', position: 'relative',
        }}>
          <div style={{
            height: '100%', width: `${displayProgress * 100}%`, background: T.cyan,
            transition: 'width 0.5s ease-in-out', position: 'relative',
          }}>
            {/* Shimmer overlay */}
            <div style={{
              position: 'absolute', inset: 0,
              background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent)',
              animation: 'shimmer 2s infinite',
            }} />
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          {Math.round(displayProgress * 100)}%
        </span>
        {displayEta != null && (
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
            ETA: {displayEta > 60 ? `${(displayEta / 60).toFixed(1)}h` : `${Math.round(displayEta)}m`}
          </span>
        )}
        <div style={{ flex: 1 }} />
        <button
          onClick={() => {
            setView('monitor' as any)
            // Set runId in URL
            window.history.replaceState(null, '', `?runId=${run.id}`)
          }}
          style={{
            padding: '2px 6px', background: `${T.cyan}14`, border: `1px solid ${T.cyan}33`,
            color: T.cyan, fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
          }}
        >
          MONITOR
        </button>
        {run.pipelineId && (
          <button
            onClick={() => {
              useUIStore.getState().setSelectedPipeline(run.pipelineId!)
              setView('editor')
            }}
            style={{
              padding: '2px 6px', background: `${T.blue}14`, border: `1px solid ${T.blue}33`,
              color: T.blue, fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
            }}
          >
            PIPELINE
          </button>
        )}
        <button
          onClick={() => {
            // TODO: wire to stop endpoint
          }}
          style={{
            padding: '2px 6px', background: `${T.red}14`, border: `1px solid ${T.red}33`,
            color: T.red, fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
          }}
        >
          <Square size={7} />
        </button>
      </div>
    </div>
  )
}

// ── Completed/Failed Run Row ──────────────────────────────────────

function CompletedRow({ run }: { run: RunSummary }) {
  const [expanded, setExpanded] = useState(false)
  const isFailed = run.status === 'failed'

  return (
    <div style={{ borderBottom: `1px solid ${T.surface4}` }}>
      <div
        onClick={() => isFailed && run.errorMessage ? setExpanded(!expanded) : null}
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '6px 12px', cursor: isFailed && run.errorMessage ? 'pointer' : 'default',
        }}
      >
        {isFailed && run.errorMessage ? (
          expanded ? <ChevronDown size={10} color={T.dim} /> : <ChevronRight size={10} color={T.dim} />
        ) : (
          <div style={{ width: 10 }} />
        )}
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.text, flex: 1 }}>{run.name}</span>
        {run.completedAt && (
          <span style={{ fontFamily: F, fontSize: 5, color: T.dim }}>
            {new Date(run.completedAt).toLocaleTimeString()}
          </span>
        )}
        <StatusBadge status={run.status} />
      </div>

      {expanded && isFailed && run.errorMessage && (
        <div style={{
          padding: '6px 12px 6px 30px', background: `${T.red}06`,
          borderTop: `1px solid ${T.red}20`,
        }}>
          <pre style={{
            fontFamily: F, fontSize: FS.xxs, color: T.red,
            whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: 0,
            maxHeight: 150, overflow: 'auto',
          }}>
            {run.errorMessage}
          </pre>
        </div>
      )}
    </div>
  )
}

// ── Main ActivityFeed ─────────────────────────────────────────────

export default function ActivityFeed({ runs, stats, onBlockedClick }: ActivityFeedProps) {
  const runningSectionRef = useRef<HTMLDivElement>(null)
  const completedSectionRef = useRef<HTMLDivElement>(null)

  const runningRuns = runs.filter((r) => r.status === 'running')
  const completedRuns = runs.filter((r) => r.status === 'complete')
  const failedRuns = runs.filter((r) => r.status === 'failed')
  const cancelledRuns = runs.filter((r) => r.status === 'cancelled')
  const recentCompleted = [...completedRuns, ...failedRuns, ...cancelledRuns]
    .sort((a, b) => (b.completedAt || '').localeCompare(a.completedAt || ''))

  const unassignedRuns = runs.filter((r) => !r.projectId)

  return (
    <div>
      {/* Stats bar with clickable cards (GAP 1.3) */}
      <StatsBar
        runningCount={runningRuns.length}
        completedTodayCount={recentCompleted.length}
        blockedCount={stats?.blockedCount ?? 0}
        computeHours={stats?.computeHours ?? 0}
        onRunningClick={() => runningSectionRef.current?.scrollIntoView({ behavior: 'smooth' })}
        onCompletedClick={() => completedSectionRef.current?.scrollIntoView({ behavior: 'smooth' })}
        onBlockedClick={onBlockedClick}
      />

      {/* Running section (GAP 1.1 — SSE-driven via useRunMonitor) */}
      <div ref={runningSectionRef}>
        {runningRuns.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{
              fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.12em',
              textTransform: 'uppercase', marginBottom: 6,
            }}>
              RUNNING ({runningRuns.length})
            </div>
            {runningRuns.map((run) => (
              <RunningCard key={run.id} run={run} />
            ))}
          </div>
        )}
      </div>

      {/* Recently completed section */}
      <div ref={completedSectionRef}>
        {recentCompleted.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{
              fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.12em',
              textTransform: 'uppercase', marginBottom: 6,
            }}>
              RECENTLY COMPLETED ({recentCompleted.length})
            </div>
            {recentCompleted.map((run) => (
              <CompletedRow key={run.id} run={run} />
            ))}
          </div>
        )}
      </div>

      {/* Unassigned runs — this is the DEFAULT state for new users */}
      {unassignedRuns.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{
            fontFamily: F, fontSize: FS.xxs, color: T.amber, letterSpacing: '0.12em',
            textTransform: 'uppercase', marginBottom: 6,
          }}>
            UNASSIGNED RUNS ({unassignedRuns.length})
          </div>
          <div style={{
            fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 6,
          }}>
            These runs are not assigned to any paper. Drag them to a paper to organize.
          </div>
          {unassignedRuns.map((run) => (
            <CompletedRow key={run.id} run={run} />
          ))}
        </div>
      )}

      {runs.length === 0 && (
        <div style={{
          padding: 40, textAlign: 'center', fontFamily: F, fontSize: FS.sm, color: T.dim,
        }}>
          No experiment runs yet. Start a pipeline to see activity here.
        </div>
      )}
    </div>
  )
}
