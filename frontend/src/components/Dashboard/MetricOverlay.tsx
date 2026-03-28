import { useState, useMemo } from 'react'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { T, F, FCODE, FS } from '@/lib/design-tokens'
import type { DashboardRunData, DashboardExperiment, ComparisonMatrixData } from '@/stores/dashboardStore'

// 6-color palette per spec
const CHART_COLORS = [
  '#00BFA5', // teal
  '#FF7043', // coral
  '#AB47BC', // purple
  '#FFB74D', // amber
  '#26C6DA', // cyan
  '#EC407A', // pink
]

type ChartType = 'line' | 'bar' | 'table'

interface MetricOverlayProps {
  experiments: DashboardExperiment[]
  selectedRunIds: string[]
  metricsLog?: Record<string, { step: number; [key: string]: number }[]>
}

interface SelectedRunInfo {
  run: DashboardRunData
  experiment: DashboardExperiment
  color: string
  label: string
}

export function MetricOverlay({ experiments, selectedRunIds, metricsLog }: MetricOverlayProps) {
  const [chartType, setChartType] = useState<ChartType>('bar')

  // Build selected runs with metadata
  const selectedRuns = useMemo<SelectedRunInfo[]>(() => {
    const result: SelectedRunInfo[] = []
    let colorIdx = 0
    for (const exp of experiments) {
      for (const run of exp.runs) {
        if (selectedRunIds.includes(run.run_id)) {
          // Build a label with key config diff
          const diffKeys = Object.keys(exp.config_diff_from_source || {}).slice(0, 2)
          const diffStr = diffKeys
            .map((k) => {
              const val = exp.config_diff_from_source[k]?.new
              const shortKey = k.split('.').pop() || k
              return `${shortKey}=${val}`
            })
            .join(', ')
          const label = diffStr ? `${exp.pipeline_name} (${diffStr})` : exp.pipeline_name
          result.push({
            run,
            experiment: exp,
            color: CHART_COLORS[colorIdx % CHART_COLORS.length],
            label,
          })
          colorIdx++
        }
      }
    }
    return result
  }, [experiments, selectedRunIds])

  // Collect all numeric metric keys from selected runs
  const numericMetricKeys = useMemo(() => {
    const keys = new Set<string>()
    for (const { run } of selectedRuns) {
      for (const [k, v] of Object.entries(run.metrics || {})) {
        if (typeof v === 'number') keys.add(k)
      }
    }
    return Array.from(keys).sort()
  }, [selectedRuns])

  // Check if we have time-series data
  const hasTimeSeries = metricsLog && Object.keys(metricsLog).some(
    (runId) => selectedRunIds.includes(runId) && (metricsLog[runId]?.length ?? 0) > 1
  )

  if (selectedRuns.length === 0) {
    return (
      <div style={{ padding: 24, color: T.dim, fontFamily: F, fontSize: FS.sm, textAlign: 'center' }}>
        Select runs to see metric comparisons
      </div>
    )
  }

  if (numericMetricKeys.length === 0) {
    return (
      <div style={{ padding: 24, color: T.dim, fontFamily: F, fontSize: FS.sm, textAlign: 'center' }}>
        No numeric metrics available for selected runs
      </div>
    )
  }

  return (
    <div>
      {/* Chart Type Toggle */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 12 }}>
        {(['line', 'bar', 'table'] as ChartType[]).map((ct) => (
          <button
            key={ct}
            onClick={() => setChartType(ct)}
            style={{
              padding: '4px 12px',
              fontSize: FS.xxs,
              fontFamily: F,
              fontWeight: chartType === ct ? 600 : 400,
              color: chartType === ct ? '#000' : T.sec,
              background: chartType === ct ? T.cyan : T.surface3,
              border: `1px solid ${chartType === ct ? T.cyan : T.border}`,
              borderRadius: 4,
              cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {ct}
          </button>
        ))}
      </div>

      {chartType === 'table' && (
        <MetricTable runs={selectedRuns} metricKeys={numericMetricKeys} />
      )}

      {chartType === 'bar' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {numericMetricKeys.map((metricKey) => (
            <ScalarBarChart
              key={metricKey}
              metricKey={metricKey}
              runs={selectedRuns}
            />
          ))}
        </div>
      )}

      {chartType === 'line' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {hasTimeSeries ? (
            numericMetricKeys.map((metricKey) => (
              <TimeSeriesChart
                key={metricKey}
                metricKey={metricKey}
                runs={selectedRuns}
                metricsLog={metricsLog!}
              />
            ))
          ) : (
            <div style={{ padding: 16, color: T.dim, fontFamily: F, fontSize: FS.xs, textAlign: 'center' }}>
              No time-series data available. Showing bar chart instead.
              <div style={{ marginTop: 8 }}>
                {numericMetricKeys.map((metricKey) => (
                  <ScalarBarChart key={metricKey} metricKey={metricKey} runs={selectedRuns} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Scalar Bar Chart ────────────────────────────────────────────────

function ScalarBarChart({ metricKey, runs }: { metricKey: string; runs: SelectedRunInfo[] }) {
  const chartData = runs.map((r) => ({
    name: r.label.length > 25 ? r.label.slice(0, 22) + '...' : r.label,
    value: typeof r.run.metrics[metricKey] === 'number' ? r.run.metrics[metricKey] as number : 0,
    fill: r.color,
  }))

  return (
    <div style={{
      background: T.surface1,
      borderRadius: 8,
      border: `1px solid ${T.border}`,
      padding: 16,
    }}>
      <div style={{ fontSize: FS.xs, fontFamily: FCODE, color: T.sec, marginBottom: 8 }}>
        {metricKey}
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={T.border} />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 10, fill: T.dim, fontFamily: F }}
            axisLine={{ stroke: T.border }}
          />
          <YAxis
            tick={{ fontSize: 10, fill: T.dim, fontFamily: FCODE }}
            axisLine={{ stroke: T.border }}
          />
          <Tooltip
            contentStyle={{
              background: T.raised,
              border: `1px solid ${T.border}`,
              borderRadius: 6,
              fontFamily: FCODE,
              fontSize: 11,
              color: T.text,
            }}
          />
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            {chartData.map((entry, idx) => (
              <Bar key={idx} dataKey="value" fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── Time Series Line Chart ──────────────────────────────────────────

function TimeSeriesChart({
  metricKey,
  runs,
  metricsLog,
}: {
  metricKey: string
  runs: SelectedRunInfo[]
  metricsLog: Record<string, { step: number; [key: string]: number }[]>
}) {
  // Merge all series data by step
  const mergedData = useMemo(() => {
    const stepMap = new Map<number, Record<string, number>>()
    for (const run of runs) {
      const log = metricsLog[run.run.run_id] || []
      for (const entry of log) {
        if (metricKey in entry) {
          const existing = stepMap.get(entry.step) || { step: entry.step }
          existing[run.run.run_id] = entry[metricKey]
          stepMap.set(entry.step, existing)
        }
      }
    }
    return Array.from(stepMap.values()).sort((a, b) => a.step - b.step)
  }, [metricKey, runs, metricsLog])

  if (mergedData.length === 0) return null

  return (
    <div style={{
      background: T.surface1,
      borderRadius: 8,
      border: `1px solid ${T.border}`,
      padding: 16,
    }}>
      <div style={{ fontSize: FS.xs, fontFamily: FCODE, color: T.sec, marginBottom: 8 }}>
        {metricKey}
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={mergedData} margin={{ top: 8, right: 16, bottom: 8, left: 16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={T.border} />
          <XAxis
            dataKey="step"
            tick={{ fontSize: 10, fill: T.dim, fontFamily: FCODE }}
            axisLine={{ stroke: T.border }}
          />
          <YAxis
            tick={{ fontSize: 10, fill: T.dim, fontFamily: FCODE }}
            axisLine={{ stroke: T.border }}
          />
          <Tooltip
            contentStyle={{
              background: T.raised,
              border: `1px solid ${T.border}`,
              borderRadius: 6,
              fontFamily: FCODE,
              fontSize: 11,
              color: T.text,
            }}
          />
          <Legend
            wrapperStyle={{ fontSize: 10, fontFamily: F }}
          />
          {runs.map((run) => (
            <Line
              key={run.run.run_id}
              type="monotone"
              dataKey={run.run.run_id}
              name={run.label}
              stroke={run.color}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── Metric Table View ───────────────────────────────────────────────

function MetricTable({ runs, metricKeys }: { runs: SelectedRunInfo[]; metricKeys: string[] }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: F, fontSize: FS.xs }}>
        <thead>
          <tr>
            <th style={{ ...headerStyle, position: 'sticky', left: 0, zIndex: 10, background: T.surface2 }}>
              Metric
            </th>
            {runs.map((r) => (
              <th key={r.run.run_id} style={headerStyle}>
                <div style={{ color: r.color, fontWeight: 600 }}>{r.label}</div>
                <div style={{ fontSize: FS.xxs, color: T.dim, fontFamily: FCODE }}>
                  {r.run.run_id.slice(0, 8)}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metricKeys.map((key) => {
            const values = runs.map((r) => r.run.metrics[key])
            const numValues = values.filter((v) => typeof v === 'number') as number[]
            const best = numValues.length > 0 ? Math.max(...numValues) : null
            return (
              <tr key={key}>
                <td style={{ ...cellStyle, position: 'sticky', left: 0, zIndex: 5, background: T.surface1, fontFamily: FCODE }}>
                  {key}
                </td>
                {runs.map((r) => {
                  const val = r.run.metrics[key]
                  const isBest = typeof val === 'number' && val === best && numValues.length > 1
                  return (
                    <td
                      key={r.run.run_id}
                      style={{
                        ...cellStyle,
                        fontFamily: FCODE,
                        fontWeight: isBest ? 700 : 400,
                        color: isBest ? T.cyan : T.text,
                      }}
                    >
                      {val === null || val === undefined
                        ? '—'
                        : typeof val === 'number'
                          ? Number.isInteger(val) ? String(val) : (val as number).toFixed(4)
                          : String(val)}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

const headerStyle: React.CSSProperties = {
  background: T.surface2,
  borderBottom: `1px solid ${T.border}`,
  padding: '8px 12px',
  textAlign: 'left',
  color: T.text,
  fontWeight: 600,
  minWidth: 140,
  whiteSpace: 'nowrap',
}

const cellStyle: React.CSSProperties = {
  borderBottom: `1px solid ${T.border}`,
  padding: '6px 12px',
  fontSize: FS.xxs,
  color: T.text,
}
