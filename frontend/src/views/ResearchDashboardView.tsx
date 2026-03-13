import { useState, useCallback, useEffect } from 'react'
import { T, F, FD, FS, STATUS_COLORS } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { useProjectStore } from '@/stores/projectStore'
import { useRunStore } from '@/stores/runStore'
import { api } from '@/api/client'
import { useSettingsStore } from '@/stores/settingsStore'
import { DEMO_RUNS } from '@/lib/demo-data'
import StatusBadge from '@/components/shared/StatusBadge'
import MetricDisplay from '@/components/shared/MetricDisplay'
import {
  Square, Eye, FileText,
  Activity, UserPlus, Search, RefreshCw,
} from 'lucide-react'
import toast from 'react-hot-toast'

interface RunRecord {
  id: string
  pipeline_id: string
  project_id?: string | null
  status: string
  started_at: string
  completed_at: string | null
  error_message?: string | null
  metrics: Record<string, any>
}

export default function ResearchDashboardView() {
  const navigateToMonitor = useUIStore((s) => s.navigateToMonitor)
  const navigateToPaperDetail = useUIStore((s) => s.navigateToPaperDetail)
  const projects = useProjectStore((s) => s.projects)
  const fetchProjects = useProjectStore((s) => s.fetchProjects)
  const demoMode = useSettingsStore((s) => s.demoMode)

  const [runs, setRuns] = useState<RunRecord[]>([])
  const [search, setSearch] = useState('')

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
      return
    }
    try {
      const data = await api.get<RunRecord[]>('/runs?limit=20')
      setRuns(data)
    } catch { /* silently fail */ }
  }, [demoMode])

  useEffect(() => {
    fetchRuns()
    fetchProjects()
  }, [fetchRuns, fetchProjects])

  const runningRuns = runs.filter((r) => r.status === 'running')
  const completedRuns = runs.filter((r) => r.status === 'complete')
  const failedRuns = runs.filter((r) => r.status === 'failed' || r.status === 'cancelled')

  const filteredProjects = projects.filter(
    (p) =>
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      (p.paper_number || '').toLowerCase().includes(search.toLowerCase())
  )

  const handleMonitor = (runId: string) => navigateToMonitor(runId)
  const handleStop = async (_runId: string) => {
    await useRunStore.getState().stopRun()
    toast.success('Run stopped')
    fetchRuns()
  }
  const handleResults = (runId: string) => navigateToMonitor(runId)
  const handlePaperClick = (projectId: string) => navigateToPaperDetail(projectId)

  const handleAssign = async (runId: string) => {
    // Assign unassigned run to current project
    const projectId = useUIStore.getState().selectedProjectId
    if (!projectId) {
      toast.error('Select a project first')
      return
    }
    try {
      await api.patch(`/runs/${runId}`, { project_id: projectId })
      toast.success('Run assigned to project')
      fetchRuns()
    } catch {
      toast.error('Failed to assign run')
    }
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ padding: '12px 16px', borderBottom: `1px solid ${T.border}` }}>
        <h2 style={{ fontFamily: FD, fontSize: FS.h2, fontWeight: 600, color: T.text, margin: 0, letterSpacing: '0.04em' }}>
          RESEARCH DASHBOARD
        </h2>
        <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, margin: '4px 0 0', letterSpacing: '0.02em' }}>
          Overview of experiments, runs, and project status
        </p>
      </div>

      {/* Stats bar */}
      <div style={{
        display: 'flex', gap: 24, padding: '10px 16px',
        background: T.surface1, borderBottom: `1px solid ${T.border}`,
      }}>
        <MetricDisplay label="RUNNING" value={runningRuns.length} accent={T.amber} />
        <MetricDisplay label="COMPLETED" value={completedRuns.length} accent={T.green} />
        <MetricDisplay label="FAILED" value={failedRuns.length} accent={T.red} />
        <MetricDisplay label="PROJECTS" value={projects.length} accent={T.cyan} />
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
        {/* Active / Running Experiments */}
        {runningRuns.length > 0 && (
          <div style={{ marginBottom: 24 }}>
            <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, letterSpacing: '0.12em', fontWeight: 900 }}>
              ACTIVE EXPERIMENTS
            </span>
            <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
              {runningRuns.map((run) => (
                <RunCard key={run.id} run={run} onMonitor={handleMonitor} onStop={handleStop} />
              ))}
            </div>
          </div>
        )}

        {/* Recent Results */}
        <div style={{ marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, letterSpacing: '0.12em', fontWeight: 900 }}>
              RECENT RESULTS
            </span>
            <button
              onClick={fetchRuns}
              style={{
                display: 'flex', alignItems: 'center', gap: 4, padding: '2px 8px',
                background: 'none', border: `1px solid ${T.border}`, color: T.dim,
                fontFamily: F, fontSize: FS.xxs,
              }}
            >
              <RefreshCw size={8} /> REFRESH
            </button>
          </div>
          {completedRuns.length === 0 && failedRuns.length === 0 ? (
            <div style={{ padding: 16, textAlign: 'center', fontFamily: F, fontSize: FS.sm, color: T.dim }}>
              No completed runs yet
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 8 }}>
              {[...completedRuns, ...failedRuns].slice(0, 10).map((run) => (
                <RunCard key={run.id} run={run} onMonitor={handleResults} onAssign={handleAssign} />
              ))}
            </div>
          )}
        </div>

        {/* Projects sidebar */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, letterSpacing: '0.12em', fontWeight: 900 }}>
              PROJECTS
            </span>
            <div style={{
              flex: 1, display: 'flex', alignItems: 'center', gap: 6,
              padding: '3px 8px', background: T.surface0, border: `1px solid ${T.border}`,
            }}>
              <Search size={8} color={T.dim} />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter..."
                style={{
                  flex: 1, background: 'none', border: 'none', color: T.text,
                  fontFamily: F, fontSize: FS.xxs, outline: 'none',
                }}
              />
            </div>
          </div>
          <div style={{ display: 'grid', gap: 6 }}>
            {filteredProjects.map((project) => (
              <div
                key={project.id}
                onClick={() => handlePaperClick(project.id)}
                className="hover-glow"
                style={{
                  padding: '10px 12px', background: T.surface1, border: `1px solid ${T.border}`,
                  cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8,
                }}
              >
                <FileText size={12} color={T.purple} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 600 }}>{project.name}</div>
                  <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 2 }}>
                    {project.paper_number || 'No paper #'} • {project.status}
                  </div>
                </div>
                <StatusBadge status={project.status} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function RunCard({ run, onMonitor, onStop, onAssign }: {
  run: RunRecord
  onMonitor: (id: string) => void
  onStop?: (id: string) => void
  onAssign?: (id: string) => void
}) {
  const isRunning = run.status === 'running'
  const isFailed = run.status === 'failed'
  const isCancelled = run.status === 'cancelled' || (isFailed && run.error_message === 'Stopped by user')
  const displayStatus = isCancelled ? 'cancelled' : run.status
  const color = STATUS_COLORS[displayStatus] || T.dim

  return (
    <div style={{
      padding: '10px 14px', background: T.surface1, border: `1px solid ${color}33`,
      display: 'flex', alignItems: 'center', gap: 10,
    }}>
      <StatusBadge status={displayStatus} />
      <div style={{ flex: 1 }}>
        <div style={{ fontFamily: F, fontSize: FS.sm, color: T.text }}>{run.id.slice(0, 20)}</div>
        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 2 }}>
          {new Date(run.started_at).toLocaleString()}
        </div>
      </div>

      {/* Error preview for failed/cancelled runs */}
      {(isFailed || isCancelled) && run.error_message && (
        <span style={{ fontFamily: F, fontSize: FS.xxs, color, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {run.error_message.slice(0, 50)}
        </span>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', gap: 4 }}>
        {isRunning && onStop && (
          <button
            onClick={(e) => { e.stopPropagation(); onStop(run.id) }}
            style={{
              padding: '3px 8px', background: `${T.red}1A`, border: `1px solid ${T.red}33`,
              color: T.red, fontFamily: F, fontSize: FS.xxs, display: 'flex', alignItems: 'center', gap: 3,
            }}
          >
            <Square size={8} /> STOP
          </button>
        )}
        {isRunning && (
          <button
            onClick={(e) => { e.stopPropagation(); onMonitor(run.id) }}
            style={{
              padding: '3px 8px', background: `${T.cyan}1A`, border: `1px solid ${T.cyan}33`,
              color: T.cyan, fontFamily: F, fontSize: FS.xxs, display: 'flex', alignItems: 'center', gap: 3,
            }}
          >
            <Activity size={8} /> MONITOR
          </button>
        )}
        {!isRunning && (
          <button
            onClick={(e) => { e.stopPropagation(); onMonitor(run.id) }}
            style={{
              padding: '3px 8px', background: `${T.cyan}1A`, border: `1px solid ${T.cyan}33`,
              color: T.cyan, fontFamily: F, fontSize: FS.xxs, display: 'flex', alignItems: 'center', gap: 3,
            }}
          >
            <Eye size={8} /> RESULTS
          </button>
        )}
        {onAssign && !run.project_id && (
          <button
            onClick={(e) => { e.stopPropagation(); onAssign(run.id) }}
            style={{
              padding: '3px 8px', background: `${T.purple}1A`, border: `1px solid ${T.purple}33`,
              color: T.purple, fontFamily: F, fontSize: FS.xxs, display: 'flex', alignItems: 'center', gap: 3,
            }}
          >
            <UserPlus size={8} /> ASSIGN
          </button>
        )}
      </div>
    </div>
  )
}
