import { useState, useMemo, useRef } from 'react'
import { T, F, FCODE, FS } from '@/lib/design-tokens'
import type { ComparisonMatrixData } from '@/stores/dashboardStore'

interface ComparisonMatrixProps {
  data: ComparisonMatrixData
  onChangeKeys?: (configKeys: string[], metricKeys: string[]) => void
}

export function ComparisonMatrix({ data, onChangeKeys }: ComparisonMatrixProps) {
  const [showKeyPicker, setShowKeyPicker] = useState(false)
  const [keySearch, setKeySearch] = useState('')
  const [selectedConfigKeys, setSelectedConfigKeys] = useState<Set<string>>(
    new Set(data.sections.config)
  )
  const [selectedMetricKeys, setSelectedMetricKeys] = useState<Set<string>>(
    new Set(data.sections.metrics)
  )
  const scrollRef = useRef<HTMLDivElement>(null)

  // Build diff lookup
  const diffSet = useMemo(() => {
    const s = new Set<string>()
    for (const cell of data.diff_cells) {
      s.add(`${cell.row_key}:${cell.col_idx}`)
    }
    return s
  }, [data.diff_cells])

  const isDiff = (rowKey: string, colIdx: number) => diffSet.has(`${rowKey}:${colIdx}`)

  const formatValue = (v: unknown): string => {
    if (v === null || v === undefined) return '—'
    if (typeof v === 'number') {
      return Number.isInteger(v) ? String(v) : v.toFixed(4)
    }
    return String(v)
  }

  const allAvailableKeys = useMemo(() => {
    const configs = (data.available_config_keys || []).filter(
      (k) => !keySearch || k.toLowerCase().includes(keySearch.toLowerCase())
    )
    const metrics = (data.available_metric_keys || []).filter(
      (k) => !keySearch || k.toLowerCase().includes(keySearch.toLowerCase())
    )
    return { configs, metrics }
  }, [data.available_config_keys, data.available_metric_keys, keySearch])

  const handleApplyKeys = () => {
    setShowKeyPicker(false)
    onChangeKeys?.(Array.from(selectedConfigKeys), Array.from(selectedMetricKeys))
  }

  if (!data.columns.length) {
    return (
      <div style={{ padding: 24, color: T.dim, fontFamily: F, fontSize: FS.sm, textAlign: 'center' }}>
        Select runs to compare
      </div>
    )
  }

  return (
    <div style={{ position: 'relative' }}>
      {/* Column Picker Toggle */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
        <button
          onClick={() => setShowKeyPicker(!showKeyPicker)}
          style={{
            background: T.surface3,
            border: `1px solid ${T.border}`,
            borderRadius: 6,
            color: T.sec,
            padding: '4px 12px',
            fontSize: FS.xs,
            fontFamily: F,
            cursor: 'pointer',
          }}
        >
          Columns ({data.sections.config.length + data.sections.metrics.length})
        </button>
      </div>

      {/* Key Picker Dropdown */}
      {showKeyPicker && (
        <div
          style={{
            position: 'absolute',
            top: 32,
            right: 0,
            zIndex: 100,
            background: T.raised,
            border: `1px solid ${T.border}`,
            borderRadius: 8,
            padding: 12,
            width: 280,
            maxHeight: 360,
            overflow: 'auto',
            boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
          }}
        >
          <input
            type="text"
            placeholder="Search keys..."
            value={keySearch}
            onChange={(e) => setKeySearch(e.target.value)}
            style={{
              width: '100%',
              background: T.surface2,
              border: `1px solid ${T.border}`,
              borderRadius: 4,
              color: T.text,
              padding: '4px 8px',
              fontSize: FS.xs,
              fontFamily: F,
              marginBottom: 8,
              boxSizing: 'border-box',
            }}
          />
          {allAvailableKeys.configs.length > 0 && (
            <>
              <div style={{ fontSize: FS.xxs, color: T.dim, fontFamily: F, marginBottom: 4, fontWeight: 600 }}>
                Config
              </div>
              {allAvailableKeys.configs.map((key) => (
                <label key={`c-${key}`} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 0', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={selectedConfigKeys.has(key)}
                    onChange={() => {
                      const next = new Set(selectedConfigKeys)
                      next.has(key) ? next.delete(key) : next.add(key)
                      setSelectedConfigKeys(next)
                    }}
                  />
                  <span style={{ fontSize: FS.xs, fontFamily: FCODE, color: T.sec }}>{key}</span>
                </label>
              ))}
            </>
          )}
          {allAvailableKeys.metrics.length > 0 && (
            <>
              <div style={{ fontSize: FS.xxs, color: T.dim, fontFamily: F, marginTop: 8, marginBottom: 4, fontWeight: 600 }}>
                Metrics
              </div>
              {allAvailableKeys.metrics.map((key) => (
                <label key={`m-${key}`} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 0', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={selectedMetricKeys.has(key)}
                    onChange={() => {
                      const next = new Set(selectedMetricKeys)
                      next.has(key) ? next.delete(key) : next.add(key)
                      setSelectedMetricKeys(next)
                    }}
                  />
                  <span style={{ fontSize: FS.xs, fontFamily: FCODE, color: T.sec }}>{key}</span>
                </label>
              ))}
            </>
          )}
          <button
            onClick={handleApplyKeys}
            style={{
              marginTop: 8,
              width: '100%',
              background: T.cyan,
              color: '#000',
              border: 'none',
              borderRadius: 4,
              padding: '6px 0',
              fontSize: FS.xs,
              fontFamily: F,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Apply
          </button>
        </div>
      )}

      {/* Scrollable Table */}
      <div ref={scrollRef} style={{ overflowX: 'auto' }}>
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontFamily: F,
            fontSize: FS.xs,
          }}
        >
          {/* Header */}
          <thead>
            <tr>
              <th
                style={{
                  position: 'sticky',
                  left: 0,
                  zIndex: 10,
                  background: T.surface2,
                  borderBottom: `1px solid ${T.border}`,
                  padding: '8px 12px',
                  textAlign: 'left',
                  color: T.dim,
                  fontWeight: 500,
                  minWidth: 160,
                }}
              >
                Key
              </th>
              {data.columns.map((col) => (
                <th
                  key={col.run_id}
                  style={{
                    background: T.surface2,
                    borderBottom: `1px solid ${T.border}`,
                    padding: '8px 12px',
                    textAlign: 'left',
                    color: T.text,
                    fontWeight: 600,
                    minWidth: 140,
                    whiteSpace: 'nowrap',
                  }}
                >
                  <div style={{ fontSize: FS.xs }}>{col.experiment_name}</div>
                  <div style={{ fontSize: FS.xxs, color: T.dim, fontFamily: FCODE }}>
                    {col.run_id.slice(0, 8)}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {/* Config Section */}
            {data.sections.config.length > 0 && (
              <tr>
                <td
                  colSpan={data.columns.length + 1}
                  style={{
                    padding: '8px 12px 4px',
                    fontSize: FS.xxs,
                    fontWeight: 700,
                    color: T.dim,
                    textTransform: 'uppercase',
                    letterSpacing: '0.5px',
                    background: T.surface1,
                    borderBottom: `1px solid ${T.border}`,
                  }}
                >
                  Configuration
                </td>
              </tr>
            )}
            {data.sections.config.map((key) => (
              <tr key={`config-${key}`}>
                <td
                  style={{
                    position: 'sticky',
                    left: 0,
                    zIndex: 5,
                    background: T.surface1,
                    borderBottom: `1px solid ${T.border}`,
                    padding: '6px 12px',
                    fontFamily: FCODE,
                    color: T.sec,
                    fontSize: FS.xxs,
                  }}
                >
                  {key}
                </td>
                {data.columns.map((col, colIdx) => (
                  <td
                    key={col.run_id}
                    style={{
                      borderBottom: `1px solid ${T.border}`,
                      padding: '6px 12px',
                      fontFamily: FCODE,
                      fontSize: FS.xxs,
                      color: T.text,
                      background: isDiff(key, colIdx)
                        ? 'rgba(255, 183, 77, 0.15)'
                        : 'transparent',
                    }}
                  >
                    {formatValue(col.values[key])}
                  </td>
                ))}
              </tr>
            ))}

            {/* Divider */}
            {data.sections.config.length > 0 && data.sections.metrics.length > 0 && (
              <tr>
                <td
                  colSpan={data.columns.length + 1}
                  style={{
                    height: 2,
                    background: T.border,
                    padding: 0,
                  }}
                />
              </tr>
            )}

            {/* Metrics Section */}
            {data.sections.metrics.length > 0 && (
              <tr>
                <td
                  colSpan={data.columns.length + 1}
                  style={{
                    padding: '8px 12px 4px',
                    fontSize: FS.xxs,
                    fontWeight: 700,
                    color: T.dim,
                    textTransform: 'uppercase',
                    letterSpacing: '0.5px',
                    background: T.surface1,
                    borderBottom: `1px solid ${T.border}`,
                  }}
                >
                  Metrics
                </td>
              </tr>
            )}
            {data.sections.metrics.map((key) => (
              <tr key={`metric-${key}`}>
                <td
                  style={{
                    position: 'sticky',
                    left: 0,
                    zIndex: 5,
                    background: T.surface1,
                    borderBottom: `1px solid ${T.border}`,
                    padding: '6px 12px',
                    fontFamily: FCODE,
                    color: T.sec,
                    fontSize: FS.xxs,
                  }}
                >
                  {key}
                </td>
                {data.columns.map((col, colIdx) => (
                  <td
                    key={col.run_id}
                    style={{
                      borderBottom: `1px solid ${T.border}`,
                      padding: '6px 12px',
                      fontFamily: FCODE,
                      fontSize: FS.xxs,
                      color: T.text,
                      background: isDiff(key, colIdx)
                        ? 'rgba(255, 183, 77, 0.15)'
                        : 'transparent',
                    }}
                  >
                    {formatValue(col.values[key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
