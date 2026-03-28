import { useState, useEffect, useCallback } from 'react'
import { T, F, FD, FS } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { api } from '@/api/client'
import ComparisonMatrix from '@/components/Dashboard/ComparisonMatrix'
import ExperimentTimeline from '@/components/Dashboard/ExperimentTimeline'
import { FileDown, FileText, Braces, FlaskConical } from 'lucide-react'
import toast from 'react-hot-toast'

export default function ExperimentDashboard() {
  const projectId = useUIStore((s) => s.selectedProjectId)
  const [project, setProject] = useState<any>(null)
  const [runs, setRuns] = useState<any[]>([])
  const [experiments, setExperiments] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!projectId) return
    setLoading(true)

    Promise.all([
      api.get<any>(`/projects/${projectId}`),
      api.get<any[]>(`/runs?project_id=${projectId}&limit=100`),
    ])
      .then(([proj, runList]) => {
        setProject(proj)
        setRuns(runList || [])
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [projectId])

  const handleExportMarkdown = useCallback(async () => {
    if (!projectId) return
    try {
      const response = await fetch(`/api/projects/${projectId}/export/report`)
      if (!response.ok) throw new Error('Export failed')
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `blueprint-report-${projectId.slice(0, 8)}.md`
      a.click()
      URL.revokeObjectURL(url)
      toast.success('Report downloaded')
    } catch {
      toast.error('Failed to export report')
    }
  }, [projectId])

  const handleExportJSON = useCallback(async () => {
    if (!projectId) return
    try {
      const data = await api.get<any>(`/projects/${projectId}/export/json`)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `blueprint-data-${projectId.slice(0, 8)}.json`
      a.click()
      URL.revokeObjectURL(url)
      toast.success('JSON export downloaded')
    } catch {
      toast.error('Failed to export JSON')
    }
  }, [projectId])

  if (!projectId) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100%', fontFamily: F, fontSize: FS.sm, color: T.dim,
      }}>
        <FlaskConical size={16} style={{ marginRight: 8 }} />
        Select a project to view the experiment dashboard
      </div>
    )
  }

  if (loading) {
    return (
      <div style={{ padding: 20, fontFamily: F, fontSize: FS.sm, color: T.dim }}>
        Loading experiment dashboard...
      </div>
    )
  }

  const runIds = runs
    .filter((r) => r.status === 'complete' || r.status === 'failed')
    .map((r) => r.id)

  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      height: '100%', overflow: 'auto',
      padding: '16px 20px',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16,
        flexShrink: 0,
      }}>
        <div style={{ flex: 1 }}>
          <h1 style={{
            fontFamily: FD, fontSize: FS.xl, fontWeight: 600,
            color: T.text, margin: 0,
          }}>
            {project?.name || 'Experiment Dashboard'}
          </h1>
          {project?.hypothesis && (
            <p style={{
              fontFamily: F, fontSize: FS.xs, color: T.dim,
              margin: '4px 0 0', fontStyle: 'italic',
            }}>
              {project.hypothesis}
            </p>
          )}
        </div>

        {/* Export buttons */}
        <button
          onClick={handleExportMarkdown}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '5px 12px',
            background: `${T.cyan}12`, border: `1px solid ${T.cyan}33`,
            borderRadius: 4, cursor: 'pointer',
            fontFamily: F, fontSize: FS.xxs, color: T.cyan,
            letterSpacing: '0.04em',
          }}
        >
          <FileText size={11} />
          Export Report
        </button>
        <button
          onClick={handleExportJSON}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '5px 12px',
            background: `${T.purple}12`, border: `1px solid ${T.purple}33`,
            borderRadius: 4, cursor: 'pointer',
            fontFamily: F, fontSize: FS.xxs, color: T.purple,
            letterSpacing: '0.04em',
          }}
        >
          <Braces size={11} />
          Export JSON
        </button>
      </div>

      {/* Comparison Matrix */}
      {runIds.length >= 2 ? (
        <div style={{
          background: T.surface, border: `1px solid ${T.border}`,
          borderRadius: 6, padding: 16, marginBottom: 16,
          flexShrink: 0,
        }}>
          <ComparisonMatrix runIds={runIds} projectId={projectId} />
        </div>
      ) : (
        <div style={{
          background: T.surface, border: `1px solid ${T.border}`,
          borderRadius: 6, padding: 20, marginBottom: 16,
          fontFamily: F, fontSize: FS.xs, color: T.dim,
          textAlign: 'center', flexShrink: 0,
        }}>
          Complete at least 2 runs to see the comparison matrix
        </div>
      )}

      {/* Experiment Timeline */}
      <div style={{
        background: T.surface, border: `1px solid ${T.border}`,
        borderRadius: 6, padding: 16,
        flex: 1, minHeight: 200, overflow: 'auto',
      }}>
        <ExperimentTimeline projectId={projectId} experiments={experiments} />
      </div>
    </div>
  )
}
