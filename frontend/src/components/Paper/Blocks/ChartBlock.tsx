import { useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { usePaperStore } from '@/stores/paperStore'
import { BarChart3, ChevronDown } from 'lucide-react'

// Reuse the MiniBarChart from ChartBuilder to render the preview
function MiniBarChart({ data, xField, yField }: { data: Record<string, any>[]; xField: string; yField: string }) {
    if (!data?.length || !xField || !yField) {
        return (
            <div style={{ padding: 20, textAlign: 'center', color: T.dim, fontFamily: F, fontSize: FS.xs }}>
                No Data to Display
            </div>
        )
    }

    const values = data.map((d) => Number(d[yField]) || 0)
    const maxVal = Math.max(...values, 1)

    return (
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, height: 160, padding: '16px 8px' }}>
            {data.slice(0, 16).map((d, i) => {
                const val = Number(d[yField]) || 0
                const height = (val / maxVal) * 100
                return (
                    <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                        <div
                            style={{
                                width: '100%',
                                height: `${height}%`,
                                minHeight: 2,
                                background: `linear-gradient(180deg, ${T.purple}, ${T.purple}60)`,
                                borderRadius: '2px 2px 0 0',
                                transition: 'height 0.3s ease',
                            }}
                        />
                        <span style={{ fontFamily: F, fontSize: 8, color: T.dim, textAlign: 'center', overflow: 'hidden', maxWidth: '100%' }}>
                            {String(d[xField] || '').slice(0, 6)}
                        </span>
                    </div>
                )
            })}
        </div>
    )
}

interface ChartBlockProps {
    sectionId: string
    blockId: string
    chartId: string  // The selected chart's ID stored in block.content
}

export default function ChartBlock({ sectionId, blockId, chartId }: ChartBlockProps) {
    const { charts, updateBlock } = usePaperStore()
    const [dropdownOpen, setDropdownOpen] = useState(false)

    const selectedChart = charts.find(c => c.id === chartId)

    const handleSelect = (id: string) => {
        updateBlock(sectionId, blockId, id)
        setDropdownOpen(false)
    }

    return (
        <div style={{ padding: 12 }}>

            {/* Selection Dropdown */}
            <div style={{ position: 'relative', marginBottom: selectedChart ? 12 : 0 }}>
                <button
                    onClick={() => setDropdownOpen(!dropdownOpen)}
                    style={{
                        width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        padding: '8px 12px', background: T.surface4, border: `1px solid ${T.border}`,
                        color: selectedChart ? T.text : T.dim, fontFamily: F, fontSize: FS.sm,
                        cursor: 'pointer', outline: 'none', borderRadius: 4,
                    }}
                >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <BarChart3 size={14} color={selectedChart ? T.purple : T.dim} />
                        {selectedChart ? (
                            <span style={{ fontWeight: 600 }}>{selectedChart.title}</span>
                        ) : (
                            <span>Select a Chart to display...</span>
                        )}
                    </div>
                    <ChevronDown size={14} style={{ color: T.dim, transform: dropdownOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
                </button>

                {dropdownOpen && (
                    <div
                        style={{
                            position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 4,
                            background: T.surface2, border: `1px solid ${T.border}`, borderRadius: 4,
                            boxShadow: `0 8px 16px ${T.shadow}`, zIndex: 10,
                            maxHeight: 200, overflowY: 'auto'
                        }}
                    >
                        {charts.length === 0 ? (
                            <div style={{ padding: '12px', color: T.dim, fontFamily: F, fontSize: FS.xs, textAlign: 'center' }}>
                                No charts available. Create one in the Charts panel first.
                            </div>
                        ) : (
                            charts.map(chart => (
                                <button
                                    key={chart.id}
                                    onClick={() => handleSelect(chart.id)}
                                    style={{
                                        width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                                        padding: '8px 12px', background: 'transparent', border: 'none',
                                        borderBottom: `1px solid ${T.border}`, color: T.text,
                                        fontFamily: F, fontSize: FS.sm, cursor: 'pointer', textAlign: 'left',
                                    }}
                                    onMouseEnter={e => e.currentTarget.style.background = T.surface4}
                                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                                >
                                    <BarChart3 size={12} color={T.purple} />
                                    <span style={{ fontWeight: 500 }}>{chart.title}</span>
                                    <span style={{ fontSize: FS.xxs, color: T.dim, textTransform: 'uppercase' }}>{chart.type}</span>
                                </button>
                            ))
                        )}
                    </div>
                )}
            </div>

            {/* Chart Render */}
            {selectedChart && (
                <div style={{ background: T.surface0, border: `1px solid ${T.border}`, borderRadius: 4, overflow: 'hidden' }}>
                    <MiniBarChart data={selectedChart.data} xField={selectedChart.xField} yField={selectedChart.yField} />
                </div>
            )}
        </div>
    )
}
