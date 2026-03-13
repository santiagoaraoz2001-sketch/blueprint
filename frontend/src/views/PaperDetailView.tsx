import { useState, useEffect, useCallback } from 'react'
import { T, F, FD, FS, STATUS_COLORS } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { useProjectStore } from '@/stores/projectStore'
import { usePipelineStore } from '@/stores/pipelineStore'
import { api } from '@/api/client'
import { useSettingsStore } from '@/stores/settingsStore'
import { DEMO_RUNS } from '@/lib/demo-data'
import StatusBadge from '@/components/shared/StatusBadge'
import EmptyState from '@/components/shared/EmptyState'
import {
  ArrowLeft, FileText, GitBranch, Eye, Copy,
  Rocket, Activity, GitCompare, Plus, ChevronRight, XCircle, AlertTriangle,
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

export default function PaperDetailView() {
  const selectedPaperProjectId = useUIStore((s) => s.selectedPaperProjectId)
  const setView = useUIStore((s) => s.setView)
  const navigateToMonitor = useUIStore((s) => s.navigateToMonitor)
  const projects = useProjectStore((s) => s.projects)
  const fetchProjects = useProjectStore((s) => s.fetchProjects)
  const demoMode = useSettingsStore((s) => s.demoMode)

  const pipelines = usePipelineStore((s) => s.pipelines)
  const fetchPipelines = usePipelineStore((s) => s.fetchPipelines)
  const loadPipeline = usePipelineStore((s) => s.loadPipeline)
  const duplicatePipeline = usePipelineStore((s) => s.duplicatePipeline)

  const [runs, setRuns] = useState<RunRecord[]>([])

  const project = projects.find((p) => p.id === selectedPaperProjectId)

  const fetchRuns = useCallback(async () => {
    if (demoMode) {
      setRuns(DEMO_RUNS.map((r) => ({
        id: r.id,
        pipeline_id: r.pipeline_id,
        status: r.status,
        started_at: r.started_at,
        completed_at: r.completed_at,
        metrics: r.metrics as Record<string, any>,
      })))
      return
    }
    try {
      const data = await api.get<RunRecord[]>(`/runs?limit=30`)
      setRuns(data)
    } catch { /* silently fail */ }
  }, [demoMode])

  useEffect(() => {
    fetchProjects()
    fetchPipelines()
    fetchRuns()
  }, [fetchProjects, fetchPipelines, fetchRuns])

  const handleBack = () => setView('dashboard')

  const handleCloneRun = async (pipelineId: string) => {
    await duplicatePipeline(pipelineId)
    setView('editor')
  }

  const handleResults = (runId: string) => navigateToMonitor(runId)

  const handleCompareAll = () => {
    const completedRunIds = runs.filter((r) => r.status === 'complete').map((r) => r.id)
    if (completedRunIds.length < 2) {
      toast.error('Need at least 2 completed runs to compare')
      return
    }
    setView('results')
  }

  const handleLaunchNext = async (pipelineId: string) => {
    await duplicatePipeline(pipelineId)
    setView('editor')
    toast.success('Pipeline cloned — ready to configure and launch')
  }

  const handleOpenPipeline = async (id: string) => {
    await loadPipeline(id)
    setView('editor')
  }

  if (!project) {
    return (
      <div style={{ padding: 20 }}>
        <button
          onClick={handleBack}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: 'none', border: 'none', color: T.dim, fontFamily: F, fontSize: FS.md, padding: 0,
          }}
        >
          <ArrowLeft size={12} /> BACK TO DASHBOARD
        </button>
        <EmptyState icon={FileText} title="Project not found" description="The project may have been deleted" />
      </div>
    )
  }

  const accent = STATUS_COLORS[project.status] || T.dim
  const runningRuns = runs.filter((r) => r.status === 'running')
  const completedRuns = runs.filter((r) => r.status === 'complete')
  const failedRuns = runs.filter((r) => r.status === 'failed' || r.status === 'cancelled')

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ padding: '12px 16px', borderBottom: `1px solid ${T.border}` }}>
        <button
          onClick={handleBack}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: 'none', border: 'none', color: T.dim, fontFamily: F, fontSize: FS.xs,
            padding: 0, marginBottom: 8, letterSpacing: '0.08em',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = T.sec)}
          onMouseLeave={(e) => (e.currentTarget.style.color = T.dim)}
        >
          <ArrowLeft size={10} /> BACK TO DASHBOARD
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <FileText size={16} color={accent} />
          <h2 style={{ fontFamily: FD, fontSize: FS.h2, fontWeight: 600, color: T.text, margin: 0, letterSpacing: '0.04em' }}>
            {project.name}
          </h2>
          <StatusBadge status={project.status} size="md" />
          {project.paper_number && (
            <span style={{ fontFamily: F, fontSize: FS.xs, color: accent, fontWeight: 600 }}>{project.paper_number}</span>
          )}
        </div>
        {project.description && (
          <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, margin: '4px 0 0' }}>{project.description}</p>
        )}
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
        {/* Running experiments */}
        {runningRuns.length > 0 && (
          <Section title="RUNNING EXPERIMENTS">
            {runningRuns.map((run) => (
              <RunRow key={run.id} run={run}>
                <ActionBtn label="MONITOR" icon={Activity} color={T.cyan} onClick={() => navigateToMonitor(run.id)} />
              </RunRow>
            ))}
          </Section>
        )}

        {/* Pipelines */}
        <Section title="PIPELINES" action={
          <button
            onClick={() => { usePipelineStore.getState().newPipeline(); setView('editor') }}
            style={{
              padding: '3px 8px', background: `${T.cyan}14`, border: `1px solid ${T.cyan}33`,
              color: T.cyan, fontFamily: F, fontSize: FS.xxs, display: 'flex', alignItems: 'center', gap: 3,
            }}
          >
            <Plus size={8} /> NEW
          </button>
        }>
          {pipelines.length === 0 ? (
            <div style={{ padding: 12, textAlign: 'center', fontFamily: F, fontSize: FS.sm, color: T.dim }}>No pipelines</div>
          ) : pipelines.map((p) => (
            <div key={p.id} className="hover-glow" onClick={() => handleOpenPipeline(p.id)} style={{
              padding: '10px 14px', background: T.surface1, border: `1px solid ${T.border}`,
              cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <GitBranch size={12} color={T.cyan} />
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 600 }}>{p.name}</div>
                <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 2 }}>{p.block_count} blocks</div>
              </div>
              <ActionBtn label="CLONE" icon={Copy} color={T.purple} onClick={(e) => { e.stopPropagation(); handleCloneRun(p.id) }} />
              <ActionBtn label="LAUNCH" icon={Rocket} color={T.green} onClick={(e) => { e.stopPropagation(); handleLaunchNext(p.id) }} />
            </div>
          ))}
        </Section>

        {/* Completed Runs */}
        <Section title="COMPLETED RUNS" action={
          completedRuns.length >= 2 ? (
            <button
              onClick={handleCompareAll}
              style={{
                padding: '3px 8px', background: `${T.blue}14`, border: `1px solid ${T.blue}33`,
                color: T.blue, fontFamily: F, fontSize: FS.xxs, display: 'flex', alignItems: 'center', gap: 3,
              }}
            >
              <GitCompare size={8} /> COMPARE ALL
            </button>
          ) : null
        }>
          {completedRuns.length === 0 ? (
            <div style={{ padding: 12, textAlign: 'center', fontFamily: F, fontSize: FS.sm, color: T.dim }}>No completed runs</div>
          ) : completedRuns.map((run) => (
            <RunRow key={run.id} run={run}>
              <ActionBtn label="RESULTS" icon={Eye} color={T.cyan} onClick={() => handleResults(run.id)} />
              <ActionBtn label="CLONE" icon={Copy} color={T.purple} onClick={() => handleCloneRun(run.pipeline_id)} />
            </RunRow>
          ))}
        </Section>

        {/* Failed / Cancelled Runs */}
        {failedRuns.length > 0 && (
          <Section title="FAILED / CANCELLED">
            {failedRuns.map((run) => {
              const isCancelled = run.status === 'cancelled' || run.error_message === 'Stopped by user'
              const displayStatus = isCancelled ? 'cancelled' : 'failed'
              return (
                <RunRow key={run.id} run={run} overrideStatus={displayStatus}>
                  <ActionBtn label="RESULTS" icon={Eye} color={T.cyan} onClick={() => handleResults(run.id)} />
                  {run.error_message && (
                    <ErrorPreview error={run.error_message} isCancelled={isCancelled} />
                  )}
                </RunRow>
              )
            })}
          </Section>
        )}
      </div>
    </div>
  )
}

function Section({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, letterSpacing: '0.12em', fontWeight: 900 }}>{title}</span>
        {action}
      </div>
      <div style={{ display: 'grid', gap: 6 }}>{children}</div>
    </div>
  )
}

function RunRow({ run, children, overrideStatus }: { run: RunRecord; children: React.ReactNode; overrideStatus?: string }) {
  const status = overrideStatus || run.status
  return (
    <div style={{
      padding: '10px 14px', background: T.surface1, border: `1px solid ${T.border}`,
      display: 'flex', alignItems: 'center', gap: 10,
    }}>
      <StatusBadge status={status} />
      <div style={{ flex: 1 }}>
        <div style={{ fontFamily: F, fontSize: FS.sm, color: T.text }}>{run.id.slice(0, 20)}</div>
        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 2 }}>
          {new Date(run.started_at).toLocaleString()}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>{children}</div>
    </div>
  )
}

function ActionBtn({ label, icon: Icon, color, onClick }: {
  label: string; icon: React.ComponentType<any>; color: string; onClick: (e: React.MouseEvent) => void
}) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '3px 8px', background: `${color}1A`, border: `1px solid ${color}33`,
        color, fontFamily: F, fontSize: FS.xxs, display: 'flex', alignItems: 'center', gap: 3,
      }}
    >
      <Icon size={8} /> {label}
    </button>
  )
}

function ErrorPreview({ error, isCancelled }: { error: string; isCancelled: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const color = isCancelled ? STATUS_COLORS.cancelled : STATUS_COLORS.failed

  return (
    <div>
      <button
        onClick={(e) => { e.stopPropagation(); setExpanded(!expanded) }}
        style={{
          padding: '2px 6px', background: `${color}0A`, border: `1px solid ${color}33`,
          color, fontFamily: F, fontSize: FS.xxs, display: 'flex', alignItems: 'center', gap: 3,
        }}
      >
        {isCancelled ? <AlertTriangle size={8} /> : <XCircle size={8} />}
        <ChevronRight size={8} style={{ transform: expanded ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }} />
      </button>
      {expanded && (
        <div style={{
          position: 'absolute', right: 16, marginTop: 4, zIndex: 50,
          padding: 10, background: T.surface0, border: `1px solid ${color}33`,
          fontFamily: F, fontSize: FS.xxs, color: T.sec, whiteSpace: 'pre-wrap',
          maxWidth: 400, maxHeight: 200, overflow: 'auto', lineHeight: 1.6,
        }}>
          {error}
        </div>
      )}
    </div>
  )
}
