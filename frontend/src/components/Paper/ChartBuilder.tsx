import { useState, useMemo } from 'react'
import { T, F, FD, FS } from '@/lib/design-tokens'
import { usePaperStore } from '@/stores/paperStore'
// ChartConfig type used for reference but not directly imported
import { BarChart3, TrendingUp, ScatterChart, Grid3X3, BoxSelect, Plus, X, GripVertical } from 'lucide-react'

const CHART_TYPES = [
  { type: 'bar' as const, label: 'BAR', icon: BarChart3 },
  { type: 'line' as const, label: 'LINE', icon: TrendingUp },
  { type: 'scatter' as const, label: 'SCATTER', icon: ScatterChart },
  { type: 'heatmap' as const, label: 'HEAT', icon: Grid3X3 },
  { type: 'box' as const, label: 'BOX', icon: BoxSelect },
]

const labelStyle: React.CSSProperties = {
  fontFamily: F,
  fontSize: FS.xxs,
  fontWeight: 900,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  color: T.dim,
  display: 'block',
  marginBottom: 4,
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '5px 8px',
  background: T.surface4,
  border: `1px solid ${T.border}`,
  color: T.text,
  fontFamily: F,
  fontSize: FS.sm,
  outline: 'none',
  borderRadius: 0,
  boxSizing: 'border-box',
}

// Simple bar chart renderer using divs (no external chart library needed)
function MiniBarChart({ data, xField, yField }: { data: Record<string, any>[]; xField: string; yField: string }) {
  if (!data.length || !xField || !yField) {
    return (
      <div style={{ padding: 20, textAlign: 'center', color: T.dim, fontFamily: F, fontSize: FS.xs }}>
        Configure data fields to preview chart
      </div>
    )
  }

  const values = data.map((d) => Number(d[yField]) || 0)
  const maxVal = Math.max(...values, 1)

  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 120, padding: '8px 4px' }}>
      {data.slice(0, 12).map((d, i) => {
        const val = Number(d[yField]) || 0
        const height = (val / maxVal) * 100
        return (
          <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
            <div
              style={{
                width: '100%',
                height: `${height}%`,
                minHeight: 2,
                background: `linear-gradient(180deg, ${T.cyan}, ${T.cyan}60)`,
                transition: 'height 0.3s ease',
              }}
            />
            <span style={{ fontFamily: F, fontSize: 4, color: T.dim, textAlign: 'center', overflow: 'hidden', maxWidth: '100%' }}>
              {String(d[xField] || '').slice(0, 4)}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export default function ChartBuilder() {
  const { charts, addChart, updateChart, removeChart } = usePaperStore()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [csvInput, setCsvInput] = useState('')

  const editingChart = charts.find((c) => c.id === editingId)

  const handleAddChart = () => {
    addChart({
      title: 'New Chart',
      type: 'bar',
      xField: '',
      yField: '',
      colorField: '',
      data: [],
      width: 500,
      height: 300,
    })
  }

  const handleParseCsv = () => {
    if (!editingId || !csvInput.trim()) return
    const lines = csvInput.trim().split('\n')
    if (lines.length < 2) return
    const headers = lines[0].split(',').map((h) => h.trim())
    const data = lines.slice(1).map((line) => {
      const values = line.split(',').map((v) => v.trim())
      const row: Record<string, any> = {}
      headers.forEach((h, i) => {
        const num = Number(values[i])
        row[h] = isNaN(num) ? values[i] : num
      })
      return row
    })
    updateChart(editingId, { data })
    if (!editingChart?.xField && headers.length > 0) {
      updateChart(editingId, { xField: headers[0] })
    }
    if (!editingChart?.yField && headers.length > 1) {
      updateChart(editingId, { yField: headers[1] })
    }
  }

  const dataFields = useMemo(() => {
    if (!editingChart?.data?.length) return []
    return Object.keys(editingChart.data[0])
  }, [editingChart])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontFamily: FD, fontSize: FS.xl, fontWeight: 700, color: T.text, letterSpacing: '0.06em' }}>
          CHARTS
        </span>
        <button
          onClick={handleAddChart}
          style={{
            display: 'flex', alignItems: 'center', gap: 3,
            background: `${T.cyan}14`, border: `1px solid ${T.cyan}30`,
            color: T.cyan, fontFamily: F, fontSize: FS.xxs,
            fontWeight: 900, letterSpacing: '0.1em',
            padding: '3px 8px', cursor: 'pointer',
          }}
        >
          <Plus size={8} /> ADD
        </button>
      </div>

      {/* Chart list */}
      {charts.map((chart) => (
        <div
          key={chart.id}
          style={{
            background: editingId === chart.id ? T.surface3 : T.surface2,
            border: `1px solid ${editingId === chart.id ? T.cyan + '40' : T.border}`,
            transition: 'all 0.15s',
          }}
        >
          {/* Chart header */}
          <div
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 8px', cursor: 'pointer',
              borderBottom: editingId === chart.id ? `1px solid ${T.border}` : 'none',
            }}
            onClick={() => setEditingId(editingId === chart.id ? null : chart.id)}
          >
            <GripVertical size={8} color={T.dim} />
            <BarChart3 size={9} color={T.cyan} />
            <span style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 600, flex: 1 }}>
              {chart.title}
            </span>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
              {chart.type.toUpperCase()}
            </span>
            <button
              onClick={(e) => { e.stopPropagation(); removeChart(chart.id) }}
              style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 2, display: 'flex' }}
            >
              <X size={8} />
            </button>
          </div>

          {/* Expanded editor */}
          {editingId === chart.id && (
            <div style={{ padding: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {/* Title */}
              <div>
                <label style={labelStyle}>TITLE</label>
                <input
                  value={chart.title}
                  onChange={(e) => updateChart(chart.id, { title: e.target.value })}
                  style={inputStyle}
                />
              </div>

              {/* Chart type */}
              <div>
                <label style={labelStyle}>TYPE</label>
                <div style={{ display: 'flex', gap: 4 }}>
                  {CHART_TYPES.map(({ type, label, icon: Icon }) => (
                    <button
                      key={type}
                      onClick={() => updateChart(chart.id, { type })}
                      style={{
                        flex: 1,
                        padding: '4px 0',
                        background: chart.type === type ? `${T.cyan}20` : T.surface4,
                        border: `1px solid ${chart.type === type ? T.cyan + '50' : T.border}`,
                        color: chart.type === type ? T.cyan : T.dim,
                        fontFamily: F,
                        fontSize: FS.xxs,
                        fontWeight: 900,
                        letterSpacing: '0.08em',
                        cursor: 'pointer',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        gap: 2,
                      }}
                    >
                      <Icon size={10} />
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Data input */}
              <div>
                <label style={labelStyle}>DATA (CSV)</label>
                <textarea
                  value={csvInput}
                  onChange={(e) => setCsvInput(e.target.value)}
                  placeholder="name,value&#10;A,10&#10;B,20&#10;C,15"
                  style={{ ...inputStyle, height: 60, resize: 'vertical', fontFamily: F }}
                />
                <button
                  onClick={handleParseCsv}
                  style={{
                    marginTop: 4, padding: '3px 8px',
                    background: T.surface4, border: `1px solid ${T.border}`,
                    color: T.sec, fontFamily: F, fontSize: FS.xxs,
                    fontWeight: 700, cursor: 'pointer',
                  }}
                >
                  PARSE CSV
                </button>
              </div>

              {/* Field mapping */}
              {dataFields.length > 0 && (
                <div style={{ display: 'flex', gap: 6 }}>
                  <div style={{ flex: 1 }}>
                    <label style={labelStyle}>X AXIS</label>
                    <select
                      value={chart.xField}
                      onChange={(e) => updateChart(chart.id, { xField: e.target.value })}
                      style={inputStyle}
                    >
                      <option value="">Select...</option>
                      {dataFields.map((f) => <option key={f} value={f}>{f}</option>)}
                    </select>
                  </div>
                  <div style={{ flex: 1 }}>
                    <label style={labelStyle}>Y AXIS</label>
                    <select
                      value={chart.yField}
                      onChange={(e) => updateChart(chart.id, { yField: e.target.value })}
                      style={inputStyle}
                    >
                      <option value="">Select...</option>
                      {dataFields.map((f) => <option key={f} value={f}>{f}</option>)}
                    </select>
                  </div>
                </div>
              )}

              {/* Preview */}
              <div style={{ background: T.surface0, border: `1px solid ${T.border}`, minHeight: 80 }}>
                <MiniBarChart data={chart.data} xField={chart.xField} yField={chart.yField} />
              </div>
            </div>
          )}
        </div>
      ))}

      {charts.length === 0 && (
        <div style={{ padding: 16, textAlign: 'center', fontFamily: F, fontSize: FS.xs, color: T.dim }}>
          No charts yet. Click ADD to create a visualization.
        </div>
      )}
    </div>
  )
}
