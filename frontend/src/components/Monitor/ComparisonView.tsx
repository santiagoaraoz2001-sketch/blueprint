import { useEffect, useMemo, useCallback } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore, type MetricPoint } from '@/stores/metricsStore'
import { useUIStore } from '@/stores/uiStore'
import { api } from '@/api/client'
import { comparisonToTable } from '@/services/metricsBridge'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts'
import { TableProperties } from 'lucide-react'
import ConfigDiff from './ConfigDiff'
import toast from 'react-hot-toast'

interface ComparisonViewProps {
  runIds: string[]
}

const RUN_COLORS = ['#4af6c3', '#3B82F6', '#f59e0b', '#8B5CF6', '#EC4899', '#22c55e', '#fb8b1e', '#ff433d']

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div style={{ background: T.surface2, border: `1px solid ${T.border}`, padding: '6px 10px', fontFamily: F, fontSize: FS.xxs }}>
      <div style={{ color: T.dim, marginBottom: 2 }}>Step {label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {typeof p.value === 'number' ? p.value.toFixed(6) : p.value}
        </div>
      ))}
    </div>
  )
}

export default function ComparisonView({ runIds }: ComparisonViewProps) {
  const runs = useMetricsStore((s) => s.runs)

  // Load metrics for each run that's not already in the store
  useEffect(() => {
    runIds.forEach(async (id) => {
      if (runs[id]) return
      try {
        const run = await api.get<any>(`/runs/${id}`)
        if (run) {
          useMetricsStore.getState().loadHistoricalRun(id, run)
        }
      } catch {
        // Run might not exist
      }
    })
  }, [runIds])

  // Find common metric names across runs
  const commonMetrics = useMemo(() => {
    const metricsByRun: Record<string, Set<string>> = {}
    runIds.forEach((runId) => {
      const run = runs[runId]
      if (!run) return
      const allNames = new Set<string>()
      Object.values(run.blocks).forEach((block) => {
        Object.keys(block.metrics).forEach((name) => allNames.add(name))
      })
      metricsByRun[runId] = allNames
    })

    // Find metrics present in 2+ runs
    const counts: Record<string, number> = {}
    Object.values(metricsByRun).forEach((names) => {
      names.forEach((name) => {
        counts[name] = (counts[name] || 0) + 1
      })
    })

    return Object.entries(counts)
      .filter(([_, count]) => count >= 2)
      .map(([name]) => name)
  }, [runIds, runs])

  // Build chart data for each common metric
  const chartDataByMetric = useMemo(() => {
    const result: Record<string, any[]> = {}
    commonMetrics.forEach((metricName) => {
      const allSteps = new Set<number>()
      const seriesByRun: Record<string, MetricPoint[]> = {}

      runIds.forEach((runId) => {
        const run = runs[runId]
        if (!run) return
        // Find this metric in any block
        for (const block of Object.values(run.blocks)) {
          const series = block.metrics[metricName]
          if (series && series.length > 0) {
            seriesByRun[runId] = series
            series.forEach((p) => allSteps.add(p.step))
            break
          }
        }
      })

      const steps = [...allSteps].sort((a, b) => a - b)
      result[metricName] = steps.map((step) => {
        const point: Record<string, any> = { step }
        Object.entries(seriesByRun).forEach(([runId, series]) => {
          const match = series.find((p) => p.step === step)
          point[runId] = match ? match.value : undefined
        })
        return point
      })
    })
    return result
  }, [commonMetrics, runIds, runs])

  const loadedCount = runIds.filter((id) => runs[id]).length

  const handleAnalyzeInDataView = useCallback(async () => {
    try {
      const names = runIds.map((id) => runs[id]?.pipelineName || id.slice(0, 8))
      await comparisonToTable(runIds, names)
      useUIStore.getState().setView('data')
    } catch (e: any) {
      toast.error(e.message || 'Failed to export comparison')
    }
  }, [runIds, runs])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'auto', padding: '12px 16px', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
        <span style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 700 }}>Run Comparison</span>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          {loadedCount}/{runIds.length} runs loaded
        </span>
        <div style={{ flex: 1 }} />
        <button
          onClick={handleAnalyzeInDataView}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            padding: '3px 10px',
            background: `${T.cyan}14`,
            border: `1px solid ${T.cyan}33`,
            color: T.cyan,
            fontFamily: F,
            fontSize: FS.xxs,
            letterSpacing: '0.06em',
            cursor: 'pointer',
          }}
        >
          <TableProperties size={10} />
          Analyze in Data View
        </button>
      </div>

      {/* Run legend */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', flexShrink: 0 }}>
        {runIds.map((id, i) => {
          const run = runs[id]
          return (
            <div key={id} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 10, height: 3, background: RUN_COLORS[i % RUN_COLORS.length] }} />
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
                {run?.pipelineName || id.slice(0, 8)}
              </span>
              {run && (
                <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                  ({run.status})
                </span>
              )}
            </div>
          )
        })}
      </div>

      {/* Overlaid metric charts */}
      {commonMetrics.length === 0 && loadedCount > 0 && (
        <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, textAlign: 'center', padding: 20 }}>
          No common metrics found across selected runs
        </div>
      )}

      {commonMetrics.map((metricName) => {
        const data = chartDataByMetric[metricName]
        if (!data || data.length === 0) return null
        return (
          <div key={metricName} style={{ flexShrink: 0 }}>
            <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 6, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
              {metricName}
            </div>
            <div style={{ height: 180 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data}>
                  <CartesianGrid stroke={T.surface3} strokeDasharray="3 3" />
                  <XAxis dataKey="step" stroke={T.dim} tick={{ fontFamily: F, fontSize: FS.xxs, fill: T.dim }} />
                  <YAxis stroke={T.dim} tick={{ fontFamily: F, fontSize: FS.xxs, fill: T.dim }} width={50} />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend
                    wrapperStyle={{ fontFamily: F, fontSize: FS.xxs }}
                    formatter={(value: string) => {
                      const run = runs[value]
                      return run?.pipelineName || value.slice(0, 8)
                    }}
                  />
                  {runIds.map((runId, i) => (
                    <Line
                      key={runId}
                      type="monotone"
                      dataKey={runId}
                      name={runId}
                      stroke={RUN_COLORS[i % RUN_COLORS.length]}
                      strokeWidth={1.5}
                      dot={false}
                      connectNulls={false}
                      isAnimationActive={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )
      })}

      {/* Config diff */}
      <ConfigDiff runIds={runIds} />
    </div>
  )
}
