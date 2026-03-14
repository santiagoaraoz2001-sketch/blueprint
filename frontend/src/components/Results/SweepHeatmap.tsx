import { useState, useMemo, useEffect } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useSweepStore, type HeatmapData } from '@/stores/sweepStore'
import { Trophy, RefreshCw } from 'lucide-react'

interface SweepHeatmapProps {
  sweepId: string
}

/** Color interpolation: green (good/low) → yellow → red (bad/high) */
function metricColor(value: number, min: number, max: number): string {
  if (max === min) return '#22c55e'
  const t = (value - min) / (max - min)
  // Green → Yellow → Red
  if (t < 0.5) {
    const r = Math.round(34 + (234 - 34) * (t * 2))
    const g = Math.round(197 + (179 - 197) * (t * 2))
    const b = Math.round(94 + (8 - 94) * (t * 2))
    return `rgb(${r},${g},${b})`
  } else {
    const t2 = (t - 0.5) * 2
    const r = Math.round(234 + (255 - 234) * t2)
    const g = Math.round(179 + (67 - 179) * t2)
    const b = Math.round(8 + (61 - 8) * t2)
    return `rgb(${r},${g},${b})`
  }
}

function formatValue(v: any): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') {
    if (Math.abs(v) < 0.001 || Math.abs(v) > 10000) return v.toExponential(2)
    return v.toFixed(4)
  }
  return String(v)
}

export default function SweepHeatmap({ sweepId }: SweepHeatmapProps) {
  const results = useSweepStore((s) => s.results)
  const configs = useSweepStore((s) => s.configs)
  const progress = useSweepStore((s) => s.progress)
  const status = useSweepStore((s) => s.status)
  // Determine available parameters from configs
  const paramNames = useMemo(() => {
    if (!configs.length) return []
    return Object.keys(configs[0])
  }, [configs])

  const [xParam, setXParam] = useState<string>('')
  const [yParam, setYParam] = useState<string>('')

  // Auto-select first two params
  useEffect(() => {
    if (paramNames.length >= 2 && !xParam && !yParam) {
      setXParam(paramNames[0])
      setYParam(paramNames[1])
    } else if (paramNames.length === 1 && !xParam) {
      setXParam(paramNames[0])
    }
  }, [paramNames, xParam, yParam])

  // Build local heatmap data from results
  const heatmap = useMemo((): HeatmapData | null => {
    if (!results.length || !xParam) return null

    const scoredResults = results.filter((r) => r.metric !== null)
    if (!scoredResults.length) return null

    const sortMixed = (a: any, b: any) => {
      const na = Number(a), nb = Number(b)
      if (!isNaN(na) && !isNaN(nb)) return na - nb
      return String(a).localeCompare(String(b))
    }
    const xVals = [...new Set(scoredResults.map((r) => r.config[xParam]))].sort(sortMixed)

    if (!yParam) {
      // 1D: single row heatmap
      const row = xVals.map((x) => {
        const match = scoredResults.find((r) => r.config[xParam] === x)
        return match ? match.metric : null
      })
      const best = scoredResults.reduce((a, b) =>
        (a.metric ?? Infinity) < (b.metric ?? Infinity) ? a : b
      )
      return {
        x_param: xParam,
        y_param: '',
        x_values: xVals,
        y_values: [''],
        grid: [row],
        best,
      }
    }

    const yVals = [...new Set(scoredResults.map((r) => r.config[yParam]))].sort(sortMixed)

    const grid: (number | null)[][] = yVals.map((y) =>
      xVals.map((x) => {
        const match = scoredResults.find(
          (r) => r.config[xParam] === x && r.config[yParam] === y
        )
        return match ? match.metric : null
      })
    )

    const best = scoredResults.reduce((a, b) =>
      (a.metric ?? Infinity) < (b.metric ?? Infinity) ? a : b
    )

    return { x_param: xParam, y_param: yParam, x_values: xVals, y_values: yVals, grid, best }
  }, [results, xParam, yParam])

  // Get metric range for coloring
  const [metricMin, metricMax] = useMemo(() => {
    if (!heatmap) return [0, 1]
    const flat = heatmap.grid.flat().filter((v): v is number => v !== null)
    if (!flat.length) return [0, 1]
    return [Math.min(...flat), Math.max(...flat)]
  }, [heatmap])

  const s = styles

  return (
    <div style={s.container}>
      {/* Header */}
      <div style={s.header}>
        <span style={s.headerTitle}>Sweep Results</span>
        <span style={s.badge}>
          {progress.completed}/{progress.total}
        </span>
        {status === 'running' && (
          <RefreshCw
            size={11}
            color={T.cyan}
            style={{ animation: 'spin 2s linear infinite' }}
          />
        )}
        {status === 'complete' && (
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.green }}>COMPLETE</span>
        )}
      </div>

      {/* Progress bar */}
      {status === 'running' && (
        <div style={s.progressTrack}>
          <div
            style={{
              ...s.progressFill,
              width: `${progress.percent}%`,
            }}
          />
        </div>
      )}

      {/* Axis selectors */}
      {paramNames.length > 1 && (
        <div style={s.axisRow}>
          <div style={s.axisGroup}>
            <label style={s.axisLabel}>X-AXIS</label>
            <select
              value={xParam}
              onChange={(e) => setXParam(e.target.value)}
              style={s.axisSelect}
            >
              {paramNames.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
          <div style={s.axisGroup}>
            <label style={s.axisLabel}>Y-AXIS</label>
            <select
              value={yParam}
              onChange={(e) => setYParam(e.target.value)}
              style={s.axisSelect}
            >
              {paramNames.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {/* Heatmap Grid */}
      {heatmap ? (
        <div style={s.heatmapContainer}>
          <div style={s.gridWrapper}>
            {/* Column headers (x values) */}
            <div style={{ display: 'flex', marginLeft: yParam ? 64 : 0 }}>
              {heatmap.x_values.map((x, xi) => (
                <div key={xi} style={s.colHeader}>
                  {formatValue(x)}
                </div>
              ))}
            </div>

            {/* X-axis label */}
            <div style={{ ...s.axisName, marginLeft: yParam ? 64 : 0, marginBottom: 4 }}>
              {xParam}
            </div>

            {/* Grid rows */}
            {heatmap.grid.map((row, yi) => (
              <div key={yi} style={{ display: 'flex', alignItems: 'center' }}>
                {/* Y-axis label */}
                {yParam && (
                  <div style={s.rowHeader}>{formatValue(heatmap.y_values[yi])}</div>
                )}

                {/* Cells */}
                {row.map((val, xi) => {
                  const isBest =
                    heatmap.best &&
                    heatmap.best.config[xParam] === heatmap.x_values[xi] &&
                    (!yParam || heatmap.best.config[yParam] === heatmap.y_values[yi])

                  return (
                    <div
                      key={xi}
                      title={`${xParam}=${formatValue(heatmap.x_values[xi])}${
                        yParam ? `, ${yParam}=${formatValue(heatmap.y_values[yi])}` : ''
                      }\nMetric: ${val !== null ? formatValue(val) : 'pending'}`}
                      style={{
                        ...s.cell,
                        background:
                          val !== null
                            ? metricColor(val, metricMin, metricMax)
                            : T.surface3,
                        borderColor: isBest ? T.cyan : 'transparent',
                        borderWidth: isBest ? 2 : 1,
                      }}
                    >
                      {val !== null ? (
                        <span style={s.cellValue}>{formatValue(val)}</span>
                      ) : (
                        <span style={{ ...s.cellValue, color: T.dim }}>...</span>
                      )}
                      {isBest && (
                        <Trophy
                          size={10}
                          color={T.cyan}
                          style={{ position: 'absolute', top: 2, right: 2 }}
                        />
                      )}
                    </div>
                  )
                })}
              </div>
            ))}

            {/* Y-axis name */}
            {yParam && (
              <div style={{ ...s.axisName, position: 'absolute', left: 0, top: '50%', transform: 'rotate(-90deg) translateX(-50%)', transformOrigin: '0 0' }}>
                {yParam}
              </div>
            )}
          </div>

          {/* Color legend */}
          <div style={s.legend}>
            <span style={s.legendLabel}>{formatValue(metricMin)}</span>
            <div style={s.legendGradient} />
            <span style={s.legendLabel}>{formatValue(metricMax)}</span>
          </div>
        </div>
      ) : (
        <div style={s.emptyState}>
          <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>
            {status === 'running'
              ? 'Waiting for results...'
              : results.length === 0
                ? 'No results yet'
                : 'Select parameters to view heatmap'}
          </span>
        </div>
      )}

      {/* Best config summary */}
      {heatmap?.best && (
        <div style={s.bestSection}>
          <div style={s.bestHeader}>
            <Trophy size={12} color={T.cyan} />
            <span style={s.bestTitle}>Best Configuration</span>
          </div>
          <div style={s.bestConfig}>
            {Object.entries(heatmap.best.config).map(([key, val]) => (
              <div key={key} style={s.bestRow}>
                <span style={s.bestKey}>{key}</span>
                <span style={s.bestVal}>{formatValue(val)}</span>
              </div>
            ))}
            <div style={{ ...s.bestRow, borderTop: `1px solid ${T.border}`, paddingTop: 4, marginTop: 4 }}>
              <span style={s.bestKey}>metric</span>
              <span style={{ ...s.bestVal, color: T.cyan }}>{formatValue(heatmap.best.metric)}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const styles = {
  container: {
    display: 'flex' as const,
    flexDirection: 'column' as const,
    background: T.surface,
    border: `1px solid ${T.border}`,
    height: '100%',
  },
  header: {
    display: 'flex' as const,
    alignItems: 'center' as const,
    gap: 6,
    padding: '8px 12px',
    borderBottom: `1px solid ${T.border}`,
  },
  headerTitle: {
    fontFamily: F,
    fontSize: FS.sm,
    fontWeight: 700,
    color: T.text,
    letterSpacing: '0.04em',
  },
  badge: {
    fontFamily: F,
    fontSize: FS.xxs,
    color: T.dim,
    background: T.surface3,
    padding: '1px 6px',
    border: `1px solid ${T.border}`,
  },
  progressTrack: {
    height: 2,
    background: T.surface3,
  },
  progressFill: {
    height: 2,
    background: T.cyan,
    transition: 'width 0.3s ease',
  },
  axisRow: {
    display: 'flex' as const,
    gap: 8,
    padding: '8px 12px',
    borderBottom: `1px solid ${T.border}`,
  },
  axisGroup: {
    flex: 1,
  },
  axisLabel: {
    fontFamily: F,
    fontSize: FS.xxs,
    fontWeight: 600,
    color: T.dim,
    letterSpacing: '0.08em',
    display: 'block' as const,
    marginBottom: 2,
  },
  axisSelect: {
    fontFamily: F,
    fontSize: FS.xs,
    color: T.text,
    background: T.surface2,
    border: `1px solid ${T.border}`,
    padding: '3px 6px',
    width: '100%',
    outline: 'none' as const,
  },
  heatmapContainer: {
    flex: 1,
    padding: 12,
    overflow: 'auto' as const,
    display: 'flex' as const,
    flexDirection: 'column' as const,
    alignItems: 'center' as const,
    gap: 8,
  },
  gridWrapper: {
    position: 'relative' as const,
    display: 'inline-block' as const,
  },
  colHeader: {
    width: 64,
    textAlign: 'center' as const,
    fontFamily: F,
    fontSize: FS.xxs,
    color: T.sec,
    padding: '2px 0',
    overflow: 'hidden' as const,
    textOverflow: 'ellipsis' as const,
  },
  axisName: {
    fontFamily: F,
    fontSize: FS.xxs,
    fontWeight: 600,
    color: T.dim,
    textAlign: 'center' as const,
    letterSpacing: '0.06em',
  },
  rowHeader: {
    width: 56,
    textAlign: 'right' as const,
    fontFamily: F,
    fontSize: FS.xxs,
    color: T.sec,
    paddingRight: 8,
    overflow: 'hidden' as const,
    textOverflow: 'ellipsis' as const,
  },
  cell: {
    width: 64,
    height: 48,
    display: 'flex' as const,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
    position: 'relative' as const,
    border: '1px solid transparent',
    cursor: 'pointer' as const,
    transition: 'all 0.15s ease',
  },
  cellValue: {
    fontFamily: F,
    fontSize: FS.xxs,
    fontWeight: 600,
    color: '#1a1a1a',
    textShadow: '0 0 3px rgba(255,255,255,0.6), 0 0 6px rgba(255,255,255,0.3)',
  },
  legend: {
    display: 'flex' as const,
    alignItems: 'center' as const,
    gap: 6,
  },
  legendLabel: {
    fontFamily: F,
    fontSize: FS.xxs,
    color: T.dim,
  },
  legendGradient: {
    width: 100,
    height: 8,
    background: 'linear-gradient(to right, #22c55e, #EAB308, #ff433d)',
    border: `1px solid ${T.border}`,
  },
  emptyState: {
    flex: 1,
    display: 'flex' as const,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
    padding: 24,
  },
  bestSection: {
    borderTop: `1px solid ${T.border}`,
    padding: '8px 12px',
  },
  bestHeader: {
    display: 'flex' as const,
    alignItems: 'center' as const,
    gap: 6,
    marginBottom: 6,
  },
  bestTitle: {
    fontFamily: F,
    fontSize: FS.xs,
    fontWeight: 700,
    color: T.cyan,
    letterSpacing: '0.04em',
  },
  bestConfig: {
    padding: '6px 8px',
    background: T.surface2,
    border: `1px solid ${T.border}`,
  },
  bestRow: {
    display: 'flex' as const,
    justifyContent: 'space-between' as const,
    alignItems: 'center' as const,
    padding: '2px 0',
  },
  bestKey: {
    fontFamily: F,
    fontSize: FS.xxs,
    color: T.dim,
  },
  bestVal: {
    fontFamily: F,
    fontSize: FS.xxs,
    fontWeight: 600,
    color: T.text,
  },
} as const
