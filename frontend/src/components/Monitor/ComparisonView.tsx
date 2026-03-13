import { useState, useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore } from '@/stores/metricsStore'
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, Legend } from 'recharts'
import ConfigDiff from './ConfigDiff'
import { Download, GitCompare } from 'lucide-react'

const COMPARISON_COLORS = ['#00BFA5', '#F59E0B', '#8B5CF6', '#EC4899', '#3B82F6', '#22C55E', '#FB7185', '#38BDF8']

interface ComparisonViewProps {
  runIds?: string[]
}

export default function ComparisonView({ runIds: propRunIds }: ComparisonViewProps) {
  const params = new URLSearchParams(window.location.search)
  const runIds = propRunIds || (params.get('runs')?.split(',') ?? [])
  const runs = useMetricsStore((s) => s.runs)
  const [showDiff, setShowDiff] = useState(false)

  // Collect all metric names across all runs
  const allMetricNames = useMemo(() => {
    const names = new Set<string>()
    for (const id of runIds) {
      const run = runs[id]
      if (!run) continue
      for (const block of Object.values(run.blocks)) {
        for (const name of Object.keys(block.metrics)) {
          if (name !== '__started') names.add(name)
        }
      }
    }
    return Array.from(names).sort()
  }, [runIds, runs])

  // Build comparison table data
  const tableData = useMemo(() => {
    return allMetricNames.map((metric) => {
      const row: Record<string, any> = { metric }
      for (const id of runIds) {
        const run = runs[id]
        if (!run) continue
        for (const block of Object.values(run.blocks)) {
          const series = block.metrics[metric]
          if (series && series.length > 0) {
            row[id] = series[series.length - 1].value
          }
        }
      }
      return row
    })
  }, [allMetricNames, runIds, runs])

  const exportCSV = () => {
    const headers = ['metric', ...runIds.map((id) => runs[id]?.pipelineName || id)]
    const csvRows = [headers.join(',')]
    for (const row of tableData) {
      const vals = [row.metric, ...runIds.map((id) => row[id]?.toFixed(6) ?? '')]
      csvRows.push(vals.join(','))
    }
    const csv = csvRows.join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const date = new Date().toISOString().split('T')[0]
    a.download = `comparison_${runIds.join('_')}_${date}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (runIds.length === 0) {
    return (
      <div style={{ padding: 20, fontFamily: F, fontSize: FS.sm, color: T.dim }}>
        No runs selected for comparison. Select runs from the Research Dashboard.
      </div>
    )
  }

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <GitCompare size={14} color={T.cyan} />
          <span style={{ fontFamily: F, fontSize: FS.md, color: T.text, fontWeight: 700 }}>
            Run Comparison ({runIds.length} runs)
          </span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={() => setShowDiff(!showDiff)}
            style={{
              padding: '3px 8px', background: showDiff ? `${T.purple}14` : 'transparent',
              border: `1px solid ${showDiff ? T.purple : T.border}`,
              color: showDiff ? T.purple : T.dim, fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
            }}
          >
            CONFIG DIFF
          </button>
          <button
            onClick={exportCSV}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '3px 8px', background: `${T.cyan}14`, border: `1px solid ${T.cyan}33`,
              color: T.cyan, fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
            }}
          >
            <Download size={10} />
            EXPORT CSV
          </button>
        </div>
      </div>

      {showDiff && <ConfigDiff runIds={runIds} />}

      {/* Overlaid charts per metric */}
      {allMetricNames.map((metricName) => {
        // Build merged data: steps → { step, run1Value, run2Value, ... }
        const mergedMap = new Map<number, Record<string, any>>()
        runIds.forEach((id) => {
          const run = runs[id]
          if (!run) return
          for (const block of Object.values(run.blocks)) {
            const series = block.metrics[metricName]
            if (!series) continue
            series.forEach((p, i) => {
              const step = p.step ?? i
              if (!mergedMap.has(step)) mergedMap.set(step, { step })
              mergedMap.get(step)![id] = p.value
            })
          }
        })
        const merged = Array.from(mergedMap.values()).sort((a, b) => a.step - b.step)

        if (merged.length === 0) return null

        return (
          <div key={metricName} style={{ marginBottom: 24 }}>
            <div style={{ fontFamily: F, fontSize: FS.xs, color: T.sec, marginBottom: 4 }}>{metricName}</div>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={merged}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1A2332" />
                <XAxis dataKey="step" stroke="#64748B" tick={{ fontSize: 11, fontFamily: 'monospace' }} />
                <YAxis stroke="#64748B" tick={{ fontSize: 11, fontFamily: 'monospace' }} />
                <Tooltip contentStyle={{ background: '#1A2332', border: '1px solid #2D3748', fontFamily: F, fontSize: FS.xxs }} />
                <Legend wrapperStyle={{ fontFamily: F, fontSize: FS.xxs }} />
                {runIds.map((id, idx) => (
                  <Line
                    key={id}
                    type="monotone"
                    dataKey={id}
                    stroke={COMPARISON_COLORS[idx % COMPARISON_COLORS.length]}
                    dot={false}
                    strokeWidth={2}
                    name={runs[id]?.pipelineName || id.substring(0, 8)}
                    connectNulls={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )
      })}

      {/* Summary table */}
      {tableData.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontFamily: F, fontSize: FS.xs, color: T.sec, marginBottom: 6, fontWeight: 600 }}>SUMMARY</div>
          <div style={{ overflow: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: F, fontSize: FS.xxs }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                  <th style={{ padding: '4px 8px', textAlign: 'left', color: T.dim }}>Metric</th>
                  {runIds.map((id, idx) => (
                    <th key={id} style={{ padding: '4px 8px', textAlign: 'right', color: COMPARISON_COLORS[idx % COMPARISON_COLORS.length] }}>
                      {runs[id]?.pipelineName || id.substring(0, 8)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tableData.map((row) => (
                  <tr key={row.metric} style={{ borderBottom: `1px solid ${T.surface4}` }}>
                    <td style={{ padding: '3px 8px', color: T.text }}>{row.metric}</td>
                    {runIds.map((id) => (
                      <td key={id} style={{ padding: '3px 8px', color: T.sec, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                        {row[id] != null ? row[id].toFixed(4) : '—'}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
