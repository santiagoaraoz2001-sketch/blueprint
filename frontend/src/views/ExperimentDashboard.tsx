import { useEffect, useState, useCallback, useRef } from 'react'
import { Star } from 'lucide-react'
import { T, F, FCODE, FS, GLOW } from '@/lib/design-tokens'
import { STATUS_COLORS } from '@/lib/design-tokens'
import { useDashboardStore } from '@/stores/dashboardStore'
import { ComparisonMatrix } from '@/components/Dashboard/ComparisonMatrix'
import { MetricOverlay } from '@/components/Dashboard/MetricOverlay'
import { SequentialRunModal } from '@/components/Dashboard/SequentialRunModal'
import { useSSE } from '@/hooks/useSSE'

interface ExperimentDashboardProps {
  projectId: string
}

export function ExperimentDashboard({ projectId }: ExperimentDashboardProps) {
  const {
    dashboard,
    matrix,
    metricsLog,
    selectedRunIds,
    loading,
    error,
    fetchDashboard,
    fetchComparisonMatrix,
    fetchMetricsLogs,
    toggleRunSelection,
    setSelectedRunIds,
    toggleStar,
    startSequentialRun,
    reset,
  } = useDashboardStore()

  const [showSequentialModal, setShowSequentialModal] = useState(false)
  const [expandedPipelines, setExpandedPipelines] = useState<Set<string>>(new Set())
  const [pulsingExperiments, setPulsingExperiments] = useState<Set<string>>(new Set())
  const prevDashboardRef = useRef(dashboard)

  // Fetch dashboard on mount
  useEffect(() => {
    fetchDashboard(projectId)
    return () => reset()
  }, [projectId, fetchDashboard, reset])

  // Auto-expand all experiments on first load
  useEffect(() => {
    if (dashboard && prevDashboardRef.current === null) {
      setExpandedPipelines(new Set(dashboard.experiments.map((e) => e.pipeline_id)))
    }
    prevDashboardRef.current = dashboard
  }, [dashboard])

  // Fetch comparison matrix and metrics logs when selection changes
  useEffect(() => {
    if (selectedRunIds.length >= 2) {
      fetchComparisonMatrix(projectId, selectedRunIds)
      fetchMetricsLogs(selectedRunIds)
    }
  }, [projectId, selectedRunIds, fetchComparisonMatrix, fetchMetricsLogs])

  // Live SSE updates
  const handleSSEEvent = useCallback(
    (event: string, data: any) => {
      if (event === 'run_completed' || event === 'run_failed' || event === 'sequence_progress') {
        // Refresh dashboard
        fetchDashboard(projectId)

        // Pulse animation on updated experiment
        if (data.pipeline_id) {
          setPulsingExperiments((prev) => new Set(prev).add(data.pipeline_id))
          setTimeout(() => {
            setPulsingExperiments((prev) => {
              const next = new Set(prev)
              next.delete(data.pipeline_id)
              return next
            })
          }, 2000)
        }
      }
    },
    [projectId, fetchDashboard]
  )

  useSSE(`/api/projects/${projectId}/events`, {
    onEvent: handleSSEEvent,
    enabled: !!projectId,
  })

  const toggleExpanded = (pipelineId: string) => {
    setExpandedPipelines((prev) => {
      const next = new Set(prev)
      next.has(pipelineId) ? next.delete(pipelineId) : next.add(pipelineId)
      return next
    })
  }

  const handleSequentialStart = useCallback(
    (pipelineIds: string[]) => {
      startSequentialRun(projectId, pipelineIds)
      setShowSequentialModal(false)
    },
    [projectId, startSequentialRun]
  )

  const handleChangeKeys = useCallback(
    (configKeys: string[], metricKeys: string[]) => {
      fetchComparisonMatrix(projectId, selectedRunIds, configKeys, metricKeys)
    },
    [projectId, selectedRunIds, fetchComparisonMatrix]
  )

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`
    const s = Math.floor(ms / 1000)
    if (s < 60) return `${s}s`
    const m = Math.floor(s / 60)
    return `${m}m ${s % 60}s`
  }

  if (loading && !dashboard) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: T.dim, fontFamily: F }}>
        Loading dashboard...
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: T.red, fontFamily: F }}>
        {error}
      </div>
    )
  }

  if (!dashboard) return null

  const { project, experiments, active_sequences } = dashboard

  return (
    <div style={{ display: 'flex', height: '100%', fontFamily: F, color: T.text }}>
      {/* LEFT SIDEBAR (280px) */}
      <div
        style={{
          width: 280,
          minWidth: 280,
          background: T.surface1,
          borderRight: `1px solid ${T.border}`,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <div style={{ padding: '12px 16px', borderBottom: `1px solid ${T.border}` }}>
          <div style={{ fontSize: FS.xs, fontWeight: 600, color: T.dim, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Experiments
          </div>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
          {experiments.map((exp) => {
            const isExpanded = expandedPipelines.has(exp.pipeline_id)
            const isPulsing = pulsingExperiments.has(exp.pipeline_id)
            const diffCount = Object.keys(exp.config_diff_from_source || {}).length
            return (
              <div key={exp.pipeline_id}>
                {/* Pipeline Node */}
                <div
                  onClick={() => toggleExpanded(exp.pipeline_id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '8px 16px',
                    cursor: 'pointer',
                    transition: 'background 0.15s, box-shadow 0.5s',
                    background: isPulsing ? `${T.cyan}12` : 'transparent',
                    boxShadow: isPulsing ? GLOW.soft(T.cyan) : 'none',
                  }}
                >
                  <span style={{ fontSize: FS.xxs, color: T.dim, width: 12, textAlign: 'center' }}>
                    {isExpanded ? '▼' : '▶'}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: FS.sm,
                      fontWeight: 600,
                      color: T.text,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>
                      {exp.pipeline_name}
                    </div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 2 }}>
                      {diffCount > 0 && (
                        <span style={{
                          fontSize: FS.xxs,
                          fontFamily: FCODE,
                          color: T.amber,
                          background: `${T.amber}18`,
                          padding: '1px 6px',
                          borderRadius: 4,
                        }}>
                          {diffCount} change{diffCount !== 1 ? 's' : ''}
                        </span>
                      )}
                      <span style={{ fontSize: FS.xxs, color: T.dim }}>
                        {exp.runs.length} run{exp.runs.length !== 1 ? 's' : ''}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Run Children */}
                {isExpanded && (
                  <div style={{ paddingLeft: 32 }}>
                    {exp.runs.map((run) => {
                      const isSelected = selectedRunIds.includes(run.run_id)
                      const statusColor = STATUS_COLORS[run.status] || T.dim
                      return (
                        <label
                          key={run.run_id}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            padding: '4px 12px 4px 4px',
                            cursor: 'pointer',
                            borderRadius: 4,
                            background: isSelected ? `${T.cyan}10` : 'transparent',
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleRunSelection(run.run_id)}
                            style={{ accentColor: T.cyan }}
                          />
                          <span
                            style={{
                              width: 8,
                              height: 8,
                              borderRadius: '50%',
                              background: statusColor,
                              flexShrink: 0,
                            }}
                          />
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{
                              fontSize: FS.xxs,
                              fontFamily: FCODE,
                              color: T.sec,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}>
                              {run.run_id.slice(0, 8)}
                            </div>
                          </div>
                          <button
                            onClick={(e) => {
                              e.preventDefault()
                              e.stopPropagation()
                              toggleStar(run.run_id, projectId)
                            }}
                            style={{
                              background: 'none',
                              border: 'none',
                              padding: 2,
                              cursor: 'pointer',
                              color: run.starred ? T.amber : T.dim,
                              flexShrink: 0,
                              display: 'flex',
                              alignItems: 'center',
                            }}
                          >
                            <Star size={10} fill={run.starred ? T.amber : 'none'} />
                          </button>
                          <span style={{ fontSize: FS.xxs, color: T.dim, fontFamily: FCODE }}>
                            {run.duration_ms > 0 ? formatDuration(run.duration_ms) : '—'}
                          </span>
                        </label>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
          {experiments.length === 0 && (
            <div style={{ padding: '24px 16px', color: T.dim, fontSize: FS.xs, textAlign: 'center' }}>
              No experiments yet
            </div>
          )}
        </div>
      </div>

      {/* CENTER PANEL */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* TOP BAR */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 16,
            padding: '12px 20px',
            borderBottom: `1px solid ${T.border}`,
            background: T.surface0,
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 20, fontWeight: 700, color: T.text }}>
              {project.name}
            </div>
            {project.hypothesis && (
              <div style={{ fontSize: 14, fontStyle: 'italic', color: T.dim, marginTop: 2 }}>
                {project.hypothesis}
              </div>
            )}
          </div>
          <span
            style={{
              padding: '4px 10px',
              borderRadius: 4,
              fontSize: FS.xxs,
              fontWeight: 600,
              color: STATUS_COLORS[project.status] || T.dim,
              background: `${STATUS_COLORS[project.status] || T.dim}18`,
              textTransform: 'capitalize',
            }}
          >
            {project.status}
          </span>
          <button
            onClick={() => setShowSequentialModal(true)}
            disabled={experiments.length < 2}
            style={{
              padding: '6px 14px',
              background: experiments.length >= 2 ? T.cyan : T.surface4,
              color: experiments.length >= 2 ? '#000' : T.dim,
              border: 'none',
              borderRadius: 6,
              fontFamily: F,
              fontSize: FS.xs,
              fontWeight: 600,
              cursor: experiments.length >= 2 ? 'pointer' : 'not-allowed',
            }}
          >
            Sequential Run
          </button>
        </div>

        {/* Sequence Progress Bar */}
        {active_sequences.length > 0 && (
          <div
            style={{
              padding: '8px 20px',
              background: `${T.cyan}10`,
              borderBottom: `1px solid ${T.border}`,
              display: 'flex',
              alignItems: 'center',
              gap: 12,
            }}
          >
            {active_sequences.map((seq) => (
              <div key={seq.sequence_id} style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
                <div
                  style={{
                    height: 4,
                    flex: 1,
                    background: T.surface4,
                    borderRadius: 2,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${(seq.current_index / seq.total) * 100}%`,
                      background: T.cyan,
                      borderRadius: 2,
                      transition: 'width 0.5s ease',
                    }}
                  />
                </div>
                <span style={{ fontSize: FS.xxs, fontFamily: F, color: T.sec, whiteSpace: 'nowrap' }}>
                  Running {seq.current_index + 1}/{seq.total}: {seq.current_pipeline_name || '...'}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Content Area */}
        <div style={{ flex: 1, overflow: 'auto', padding: 20 }}>
          {selectedRunIds.length < 2 ? (
            <div style={{ textAlign: 'center', padding: 40, color: T.dim, fontSize: FS.sm }}>
              Select 2 or more runs from the sidebar to compare
            </div>
          ) : (
            <>
              {/* Comparison Matrix */}
              {matrix && (
                <div style={{ marginBottom: 24 }}>
                  <div style={{ fontSize: FS.md, fontWeight: 600, color: T.text, marginBottom: 12 }}>
                    Comparison Matrix
                  </div>
                  <div style={{
                    background: T.surface1,
                    borderRadius: 8,
                    border: `1px solid ${T.border}`,
                    padding: 16,
                    overflow: 'hidden',
                  }}>
                    <ComparisonMatrix data={matrix} onChangeKeys={handleChangeKeys} />
                  </div>
                </div>
              )}

              {/* Metric Overlay Charts */}
              <div>
                <div style={{ fontSize: FS.md, fontWeight: 600, color: T.text, marginBottom: 12 }}>
                  Metric Charts
                </div>
                <MetricOverlay
                  experiments={experiments}
                  selectedRunIds={selectedRunIds}
                  metricsLog={metricsLog}
                />
              </div>
            </>
          )}
        </div>
      </div>

      {/* Sequential Run Modal */}
      {showSequentialModal && (
        <SequentialRunModal
          experiments={experiments}
          onStart={handleSequentialStart}
          onClose={() => setShowSequentialModal(false)}
        />
      )}
    </div>
  )
}
