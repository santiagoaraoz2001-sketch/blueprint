import { useState, useCallback, useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore } from '@/stores/metricsStore'
import { BarChart3, Table, Download } from 'lucide-react'

interface RawDataToggleProps {
  blockId: string
  children: React.ReactNode
}

export default function RawDataToggle({ blockId, children }: RawDataToggleProps) {
  const [showRaw, setShowRaw] = useState(false)
  const allEvents = useMetricsStore((s) => s.metricEvents)
  const events = useMemo(() => allEvents.filter(e => e.blockId === blockId), [allEvents, blockId])

  const exportCSV = useCallback(() => {
    if (events.length === 0) return
    const header = 'Timestamp,Metric Name,Value,Step\n'
    const rows = events.map(e => `${e.timestamp},${e.name},${e.value},${e.step ?? ''}`).join('\n')
    const csv = header + rows
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `metrics-${blockId}-${Date.now()}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }, [events, blockId])

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Toggle bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 4,
        padding: '4px 8px',
        borderBottom: `1px solid ${T.border}`,
        flexShrink: 0,
      }}>
        <div style={{ flex: 1 }} />
        <button
          onClick={() => setShowRaw(false)}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '2px 8px',
            background: !showRaw ? `${T.cyan}15` : T.surface2,
            border: `1px solid ${!showRaw ? `${T.cyan}40` : T.border}`,
            color: !showRaw ? T.cyan : T.dim,
            fontFamily: F, fontSize: FS.xxs, cursor: 'pointer', letterSpacing: '0.04em',
          }}
        >
          <BarChart3 size={9} /> Charts
        </button>
        <button
          onClick={() => setShowRaw(true)}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '2px 8px',
            background: showRaw ? `${T.cyan}15` : T.surface2,
            border: `1px solid ${showRaw ? `${T.cyan}40` : T.border}`,
            color: showRaw ? T.cyan : T.dim,
            fontFamily: F, fontSize: FS.xxs, cursor: 'pointer', letterSpacing: '0.04em',
          }}
        >
          <Table size={9} /> Raw Data
        </button>
      </div>

      {showRaw ? (
        <div style={{ flex: 1, overflow: 'auto', padding: 8 }}>
          {/* Export button */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 6 }}>
            <button
              onClick={exportCSV}
              disabled={events.length === 0}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '3px 8px',
                background: T.surface2, border: `1px solid ${T.border}`,
                color: events.length > 0 ? T.sec : T.dim,
                fontFamily: F, fontSize: FS.xxs, cursor: events.length > 0 ? 'pointer' : 'default',
                letterSpacing: '0.04em',
              }}
            >
              <Download size={9} /> Export CSV
            </button>
          </div>

          {/* Data table */}
          <table style={{
            width: '100%', borderCollapse: 'collapse',
            fontFamily: F, fontSize: FS.xxs,
          }}>
            <thead>
              <tr>
                {['Timestamp', 'Metric Name', 'Value', 'Step'].map(h => (
                  <th key={h} style={{
                    padding: '4px 8px', textAlign: 'left',
                    borderBottom: `1px solid ${T.borderHi}`,
                    color: T.dim, fontWeight: 700, letterSpacing: '0.08em',
                    position: 'sticky', top: 0, background: T.bg,
                  }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {events.length === 0 ? (
                <tr>
                  <td colSpan={4} style={{ padding: 16, textAlign: 'center', color: T.dim }}>
                    No metric events yet
                  </td>
                </tr>
              ) : (
                events.map((e, i) => (
                  <tr key={i} style={{
                    borderBottom: `1px solid ${T.border}`,
                  }}>
                    <td style={{ padding: '3px 8px', color: T.dim }}>{e.timestamp}</td>
                    <td style={{ padding: '3px 8px', color: T.sec }}>{e.name}</td>
                    <td style={{ padding: '3px 8px', color: T.text, fontVariantNumeric: 'tabular-nums' }}>
                      {typeof e.value === 'number' ? e.value.toLocaleString(undefined, { maximumFractionDigits: 6 }) : String(e.value)}
                    </td>
                    <td style={{ padding: '3px 8px', color: T.dim }}>{e.step ?? '-'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ flex: 1, overflow: 'auto' }}>
          {children}
        </div>
      )}
    </div>
  )
}
