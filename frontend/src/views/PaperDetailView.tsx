import { useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import EditableField from '@/components/Research/EditableField'
import PhaseTimeline, { type PhaseData } from '@/components/Research/PhaseTimeline'
import QuickStats from '@/components/Research/QuickStats'
import ResearchNotes from '@/components/Research/ResearchNotes'
import { ArrowLeft, FileText } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'

export default function PaperDetailView() {
  const setView = useUIStore((s) => s.setView)
  const projectId = useUIStore((s) => s.selectedProjectId)
  const [notes, setNotes] = useState<{ id: string; text: string; createdAt: string }[]>([])

  // Fetch project details
  const { data: project } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => api.get<any>(`/projects/${projectId}`),
    enabled: !!projectId,
  })

  // Fetch runs for this project
  const { data: runs = [] } = useQuery({
    queryKey: ['project-runs', projectId],
    queryFn: () => api.get<any[]>(`/runs?project_id=${projectId}`).catch(() => []),
    enabled: !!projectId,
  })

  if (!projectId || !project) {
    return (
      <div style={{ padding: 20 }}>
        <button
          onClick={() => setView('research' as any)}
          style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 2 }}
        >
          <ArrowLeft size={14} />
        </button>
        <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, marginTop: 8 }}>
          No paper selected.
        </p>
      </div>
    )
  }

  // Build phases from project data (stub — real implementation depends on paper schema)
  const phases: PhaseData[] = (project.phases || []).map((p: any) => ({
    id: p.id || p.phase_id,
    name: p.name,
    status: p.status || 'planned',
    researchQuestion: p.research_question,
    finding: p.finding,
    blockedBy: p.blocked_by,
    totalRuns: p.total_runs || 0,
    completedRuns: p.completed_runs || 0,
    runningRuns: p.running_runs || 0,
    plannedRuns: p.planned_runs || 0,
    runs: (p.runs || []).map((r: any) => ({
      id: r.id,
      name: r.name || r.id.substring(0, 8),
      status: r.status,
      progress: r.progress,
      eta: r.eta,
      metrics: r.metrics,
      errorMessage: r.error_message,
    })),
    bestRun: p.best_run,
  }))

  // If no phases exist, show runs directly
  if (phases.length === 0 && runs.length > 0) {
    const runPhase: PhaseData = {
      id: 'all',
      name: 'All Runs',
      status: 'active',
      totalRuns: runs.length,
      completedRuns: runs.filter((r: any) => r.status === 'complete').length,
      runningRuns: runs.filter((r: any) => r.status === 'running').length,
      plannedRuns: 0,
      runs: runs.map((r: any) => ({
        id: r.id,
        name: r.pipeline_name || r.name || r.id.substring(0, 8),
        status: r.status,
        progress: r.progress,
        eta: r.eta,
        metrics: r.final_metrics,
        errorMessage: r.error_message,
      })),
    }
    phases.push(runPhase)
  }

  const totalRuns = runs.length
  const completedRuns = runs.filter((r: any) => r.status === 'complete').length

  return (
    <div style={{ padding: 20 }}>
      {/* Back nav */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <button
          onClick={() => setView('research' as any)}
          style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 2 }}
        >
          <ArrowLeft size={14} />
        </button>
        <FileText size={14} color={T.cyan} />
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>PAPER DETAIL</span>
      </div>

      {/* Title (editable) */}
      <div style={{ marginBottom: 4 }}>
        <EditableField
          value={project.name}
          onSave={async (name) => {
            await api.put(`/projects/${projectId}`, { name })
          }}
          fontSize={FS.xl * 1.3}
          color={T.text}
          placeholder="Paper title..."
        />
      </div>

      {/* Hypothesis (editable) */}
      <div style={{ marginBottom: 16 }}>
        <EditableField
          value={project.description || ''}
          onSave={async (description) => {
            await api.put(`/projects/${projectId}`, { description })
          }}
          multiline
          fontSize={FS.sm}
          fontStyle="italic"
          color={T.sec}
          placeholder="Research hypothesis..."
        />
      </div>

      {/* Quick stats */}
      <div style={{ marginBottom: 16 }}>
        <QuickStats
          totalRuns={totalRuns}
          completedRuns={completedRuns}
        />
      </div>

      {/* Phase timeline */}
      <div style={{ marginBottom: 24 }}>
        <div style={{
          fontFamily: F, fontSize: FS.xs, color: T.dim, letterSpacing: '0.12em',
          textTransform: 'uppercase', marginBottom: 8,
        }}>
          EXPERIMENT PHASES
        </div>
        <PhaseTimeline
          phases={phases}
          paperId={projectId}
        />
      </div>

      {/* Research notes */}
      <ResearchNotes
        notes={notes}
        onAdd={(text) => {
          setNotes((prev) => [...prev, {
            id: `note-${Date.now()}`,
            text,
            createdAt: new Date().toISOString(),
          }])
        }}
        onRemove={(id) => {
          setNotes((prev) => prev.filter((n) => n.id !== id))
        }}
      />
    </div>
  )
}
