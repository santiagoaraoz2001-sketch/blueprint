import { useState, useEffect, useMemo, useCallback } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { api } from '@/api/client'
import { useSettingsStore } from '@/stores/settingsStore'
import ConfigDiff from './ConfigDiff'
import { Download } from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'

interface Props {
  initialRunIds?: string[]
}

interface RunData {
  id: string
  name: string
  status: string
  metrics: Record<string, any>
  config_snapshot: Record<string, any>
}

const COMPARE_COLORS = ['#00BFA5', '#F59E0B', '#3B82F6', '#EC4899', '#8B5CF6']

// Demo data for comparison mode
const DEMO_RUNS: RunData[] = [
  {
    id: 'demo-run-1', name: 'LR=2e-4', status: 'complete',
    metrics: {
      'train/loss': Array.from({ length: 50 }, (_, i) => ({ step: i, value: 2.5 * Math.exp(-i * 0.06) + 0.38 })),
      'eval/acc': [{ step: 50, value: 0.71 }],
    },
    config_snapshot: { model: { name: 'llama-3.1-8b' }, training: { learning_rate: 2e-4, batch_size: 8, epochs: 3 }, optimizer: { type: 'adamw', weight_decay: 0.01 } },
  },
  {
    id: 'demo-run-2', name: 'LR=1e-4', status: 'complete',
    metrics: {
      'train/loss': Array.from({ length: 50 }, (_, i) => ({ step: i, value: 2.5 * Math.exp(-i * 0.04) + 0.31 })),
      'eval/acc': [{ step: 50, value: 0.74 }],
    },
    config_snapshot: { model: { name: 'llama-3.1-8b' }, training: { learning_rate: 1e-4, batch_size: 16, epochs: 5 }, optimizer: { type: 'adamw', weight_decay: 0.005 } },
  },
  {
    id: 'demo-run-3', name: 'LR=5e-5', status: 'complete',
    metrics: {
      'train/loss': Array.from({ length: 50 }, (_, i) => ({ step: i, value: 2.5 * Math.exp(-i * 0.03) + 0.28 })),
      'eval/acc': [{ step: 50, value: 0.76 }],
    },
    config_snapshot: { model: { name: 'llama-3.1-8b' }, training: { learning_rate: 5e-5, batch_size: 16, epochs: 10 }, optimizer: { type: 'adamw', weight_decay: 0.01 } },
  },
]

export default function ComparisonView({ initialRunIds }: Props) {
  const [allRuns, setAllRuns] = useState<RunData[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set(initialRunIds || []))
  const [loading, setLoading] = useState(false)
  const isDemoMode = useSettingsStore((s) => s.demoMode)

  // Load available runs
  useEffect(() => {
    async function loadRuns() {
      if (isDemoMode) {
        setAllRuns(DEMO_RUNS)
        if (selectedIds.size === 0) {
          setSelectedIds(new Set(DEMO_RUNS.map(r => r.id)))
        }
        return
      }
      setLoading(true)
      try {
        const data = await api.get<any>('/runs?status=complete&limit=20')
        const runs = (data.runs || data || []).map((r: any) => ({
          id: r.id,
          name: r.name || `Run ${r.id.slice(0, 8)}`,
          status: r.status,
          metrics: r.metrics || {},
          config_snapshot: r.config_snapshot || {},
        }))
        setAllRuns(runs)
        if (selectedIds.size === 0 && runs.length >= 2) {
          setSelectedIds(new Set(runs.slice(0, 2).map((r: RunData) => r.id)))
        }
      } catch {
        // Silently fail
      }
      setLoading(false)
    }
    loadRuns()
  }, [isDemoMode])

  const selectedRuns = allRuns.filter(r => selectedIds.has(r.id))

  // Build shared metrics for overlaid charts
  const sharedMetrics = useMemo(() => {
    const metricNames = new Set<string>()
    selectedRuns.forEach(run => {
      Object.keys(run.metrics).forEach(name => {
        if (Array.isArray(run.metrics[name]) && run.metrics[name].length > 1) {
          metricNames.add(name)
        }
      })
    })
    return Array.from(metricNames)
  }, [selectedRuns])

  // Build comparison table (metric rows x run columns)
  const comparisonMetrics = useMemo(() => {
    const metricNames = new Set<string>()
    selectedRuns.forEach(run => {
      Object.keys(run.metrics).forEach(name => metricNames.add(name))
    })

    return Array.from(metricNames).map(name => {
      const values = selectedRuns.map(run => {
        const series = run.metrics[name]
        if (Array.isArray(series) && series.length > 0) {
          return series[series.length - 1].value as number
        }
        return typeof series === 'number' ? series : null
      })
      return { name, values }
    })
  }, [selectedRuns])

  const toggleRun = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        if (next.size > 1) next.delete(id) // Keep at least 1
      } else {
        if (next.size < 5) next.add(id)
      }
      return next
    })
  }

  const exportCSV = useCallback(() => {
    if (comparisonMetrics.length === 0) return
    const header = ['Metric', ...selectedRuns.map(r => r.name)].join(',')
    const rows = comparisonMetrics.map(m =>
      [m.name, ...m.values.map(v => v !== null ? String(v) : '')].join(',')
    )
    const csv = [header, ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `comparison-${Date.now()}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }, [comparisonMetrics, selectedRuns])

  return (
    <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
      {/* Left: Run selector */}
      <div style={{
        width: 200, borderRight: `1px solid ${T.border}`,
        overflow: 'auto', padding: 8,
      }}>
        <div style={{
          fontFamily: F, fontSize: FS.xxs, fontWeight: 700,
          color: T.dim, letterSpacing: '0.06em', marginBottom: 8,
        }}>
          SELECT RUNS (2-5)
        </div>

        {loading && (
          <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, padding: 8 }}>
            Loading runs...
          </div>
        )}

        {allRuns.map(run => (
          <label
            key={run.id}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '4px 6px', cursor: 'pointer',
              background: selectedIds.has(run.id) ? `${T.cyan}08` : 'transparent',
              borderBottom: `1px solid ${T.border}`,
            }}
          >
            <input
              type="checkbox"
              checked={selectedIds.has(run.id)}
              onChange={() => toggleRun(run.id)}
              style={{ accentColor: T.cyan }}
            />
            <div style={{
              width: 8, height: 8, borderRadius: '50%',
              background: selectedIds.has(run.id)
                ? COMPARE_COLORS[Array.from(selectedIds).indexOf(run.id) % COMPARE_COLORS.length]
                : T.dim,
            }} />
            <span style={{
              fontFamily: F, fontSize: FS.xxs, color: T.sec,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {run.name}
            </span>
          </label>
        ))}
      </div>

      {/* Center: Charts + table + diff */}
      <div style={{ flex: 1, overflow: 'auto', padding: 12 }}>
        {selectedRuns.length < 2 ? (
          <div style={{
            height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: F, fontSize: FS.xs, color: T.dim,
          }}>
            Select at least 2 runs to compare
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Overlaid charts for shared metrics */}
            {sharedMetrics.map(metricName => {
              // Build aligned data by step
              const stepSet = new Set<number>()
              selectedRuns.forEach(run => {
                const series = run.metrics[metricName]
                if (Array.isArray(series)) {
                  series.forEach((pt: any) => stepSet.add(pt.step))
                }
              })
              const steps = Array.from(stepSet).sort((a, b) => a - b)
              const chartData = steps.map(step => {
                const point: any = { step }
                selectedRuns.forEach(run => {
                  const series = run.metrics[metricName]
                  if (Array.isArray(series)) {
                    const match = series.find((pt: any) => pt.step === step)
                    if (match) point[run.id] = match.value
                  }
                })
                return point
              })

              return (
                <div key={metricName} style={{
                  background: T.surface1, border: `1px solid ${T.border}`, padding: 8,
                }}>
                  <div style={{
                    fontFamily: F, fontSize: FS.xxs, fontWeight: 700,
                    color: T.dim, letterSpacing: '0.06em', marginBottom: 4,
                  }}>
                    {metricName.toUpperCase()}
                  </div>
                  <div style={{ height: 200 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData} margin={{ top: 4, right: 12, left: 0, bottom: 4 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1A2332" />
                        <XAxis dataKey="step" stroke={T.dim} tick={{ fill: T.dim, fontSize: 7, fontFamily: F }} />
                        <YAxis stroke={T.dim} tick={{ fill: T.dim, fontSize: 7, fontFamily: F }} width={45} />
                        <Tooltip
                          contentStyle={{
                            background: T.surface2, border: `1px solid ${T.borderHi}`,
                            fontFamily: F, fontSize: 7, color: T.sec, padding: '4px 8px',
                          }}
                        />
                        <Legend
                          wrapperStyle={{ fontFamily: F, fontSize: 7 }}
                        />
                        {selectedRuns.map((run, i) => (
                          <Line
                            key={run.id}
                            type="monotone"
                            dataKey={run.id}
                            name={run.name}
                            stroke={COMPARE_COLORS[i % COMPARE_COLORS.length]}
                            strokeWidth={1.5}
                            dot={false}
                            isAnimationActive={false}
                          />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )
            })}

            {/* Comparison table */}
            {comparisonMetrics.length > 0 && (
              <div style={{
                background: T.surface1, border: `1px solid ${T.border}`, padding: 8,
              }}>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8,
                }}>
                  <span style={{
                    fontFamily: F, fontSize: FS.xxs, fontWeight: 700,
                    color: T.dim, letterSpacing: '0.06em',
                  }}>
                    METRICS COMPARISON
                  </span>
                  <div style={{ flex: 1 }} />
                  <button
                    onClick={exportCSV}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 4,
                      padding: '2px 8px', background: T.surface2, border: `1px solid ${T.border}`,
                      color: T.sec, fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
                    }}
                  >
                    <Download size={9} /> Export CSV
                  </button>
                </div>

                <table style={{
                  width: '100%', borderCollapse: 'collapse',
                  fontFamily: F, fontSize: FS.xxs,
                }}>
                  <thead>
                    <tr>
                      <th style={{
                        padding: '4px 8px', textAlign: 'left',
                        borderBottom: `1px solid ${T.borderHi}`, color: T.dim,
                        fontWeight: 700, letterSpacing: '0.06em',
                      }}>Metric</th>
                      {selectedRuns.map((run, i) => (
                        <th key={run.id} style={{
                          padding: '4px 8px', textAlign: 'right',
                          borderBottom: `1px solid ${T.borderHi}`,
                          color: COMPARE_COLORS[i % COMPARE_COLORS.length],
                          fontWeight: 700, letterSpacing: '0.06em',
                        }}>{run.name}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {comparisonMetrics.map(({ name, values }) => {
                      const numericValues = values.filter((v): v is number => v !== null)
                      const bestIdx = numericValues.length > 0
                        ? (name.toLowerCase().includes('loss')
                          ? values.indexOf(Math.min(...numericValues))
                          : values.indexOf(Math.max(...numericValues)))
                        : -1
                      const worstIdx = numericValues.length > 0
                        ? (name.toLowerCase().includes('loss')
                          ? values.indexOf(Math.max(...numericValues))
                          : values.indexOf(Math.min(...numericValues)))
                        : -1

                      return (
                        <tr key={name} style={{ borderBottom: `1px solid ${T.border}` }}>
                          <td style={{ padding: '3px 8px', color: T.sec }}>{name}</td>
                          {values.map((v, i) => (
                            <td key={i} style={{
                              padding: '3px 8px', textAlign: 'right',
                              color: T.text, fontVariantNumeric: 'tabular-nums',
                              fontWeight: i === bestIdx ? 700 : 400,
                              background: i === bestIdx ? `${T.green}08`
                                : i === worstIdx && numericValues.length > 1 ? `${T.red}06`
                                  : 'transparent',
                            }}>
                              {v !== null ? v.toLocaleString(undefined, { maximumFractionDigits: 6 }) : '—'}
                            </td>
                          ))}
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Config Diff */}
            <div style={{ background: T.surface1, border: `1px solid ${T.border}` }}>
              <ConfigDiff
                configs={selectedRuns.map(r => ({
                  runId: r.id,
                  runName: r.name,
                  config: r.config_snapshot,
                }))}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
