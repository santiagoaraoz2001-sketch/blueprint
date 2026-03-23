import { useState, useCallback, useEffect } from 'react'
import { T, F, FS, FD } from '@/lib/design-tokens'
import { useVizStore, type ChartType, type ChartPanel } from '@/stores/vizStore'
import { useDataStore } from '@/stores/dataStore'
import { api } from '@/api/client'
import { runMetricsToTimeSeries } from '@/services/metricsBridge'
import { motion, AnimatePresence } from 'framer-motion'
import toast from 'react-hot-toast'
import {
  BarChart3, LineChart, ScatterChart,
  Plus, Trash2, Settings, X, ChevronDown,
  LayoutGrid, Layers, Grid3X3, TrendingUp,
  Activity, Radar, TreePine, SquareStack,
  FlaskConical,
} from 'lucide-react'
import {
  BarChart, Bar, LineChart as ReLineChart, Line,
  AreaChart, Area, ScatterChart as ReScatterChart, Scatter,
  RadarChart as ReRadarChart, Radar as ReRadar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  Treemap as ReTreemap,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell,
} from 'recharts'

/* ── Chart type icon & label mapping ── */
const CHART_TYPES: { type: ChartType; label: string; icon: React.ReactNode }[] = [
  { type: 'bar', label: 'Bar', icon: <BarChart3 size={14} /> },
  { type: 'line', label: 'Line', icon: <TrendingUp size={14} /> },
  { type: 'area', label: 'Area', icon: <Activity size={14} /> },
  { type: 'scatter', label: 'Scatter', icon: <ScatterChart size={14} /> },
  { type: 'histogram', label: 'Histogram', icon: <BarChart3 size={14} /> },
  { type: 'radar', label: 'Radar', icon: <Radar size={14} /> },
  { type: 'treemap', label: 'Treemap', icon: <TreePine size={14} /> },
  { type: 'heatmap', label: 'Heatmap', icon: <Grid3X3 size={14} /> },
  { type: 'box', label: 'Box Plot', icon: <SquareStack size={14} /> },
]

const COLOR_SCHEMES: { id: string; label: string; colors: string[] }[] = [
  { id: 'default', label: 'Blueprint', colors: ['#4af6c3', '#3B82F6', '#8B5CF6', '#F59E0B', '#EC4899', '#10B981'] },
  { id: 'warm', label: 'Warm', colors: ['#F97316', '#EF4444', '#F59E0B', '#EC4899', '#D946EF', '#FB7185'] },
  { id: 'cool', label: 'Cool', colors: ['#06B6D4', '#3B82F6', '#6366F1', '#8B5CF6', '#10B981', '#14B8A6'] },
  { id: 'mono', label: 'Mono', colors: ['#E5E5E5', '#A3A3A3', '#737373', '#525252', '#404040', '#262626'] },
]

function getSchemeColors(schemeId: string): string[] {
  return COLOR_SCHEMES.find((s) => s.id === schemeId)?.colors || COLOR_SCHEMES[0].colors
}

/* ── Main View ── */
export default function VisualizationView() {
  const {
    dashboards, activeDashboardId,
    createDashboard,
    setActiveDashboard, getActiveDashboard,
    addPanel, updatePanel, removePanel,
  } = useVizStore()

  const tables = useDataStore((s) => s.tables)

  const [selectedPanelId, setSelectedPanelId] = useState<string | null>(null)
  const [newChartType, setNewChartType] = useState<ChartType>('bar')
  const [showNewChartModal, setShowNewChartModal] = useState(false)
  const [dashDropdown, setDashDropdown] = useState(false)
  const [showRunImport, setShowRunImport] = useState(false)
  const [recentRuns, setRecentRuns] = useState<any[]>([])

  // Fetch recent runs when dropdown is opened
  useEffect(() => {
    if (!showRunImport) return
    api.get<any[]>('/runs?status=complete&limit=20')
      .then((runs) => setRecentRuns(runs || []))
      .catch(() => setRecentRuns([]))
  }, [showRunImport])

  const handleImportRunData = useCallback(async (runId: string) => {
    try {
      const tableId = await runMetricsToTimeSeries(runId)
      setShowRunImport(false)

      // Auto-create a line chart if we have an active dashboard
      const dash = getActiveDashboard()
      const table = useDataStore.getState().tables.find((t) => t.id === tableId)
      if (dash && table) {
        const numCols = table.columns.filter((c) => c.type === 'number' && c.id !== 'step')
        const panelCount = dash.panels.length
        addPanel(dash.id, {
          title: `Run ${runId.slice(0, 8)} — ${numCols[0]?.name || 'Metrics'}`,
          chartType: 'line',
          dataTableId: tableId,
          xField: 'step',
          yField: numCols[0]?.id || table.columns[1]?.id || '',
          style: { colorScheme: 'default', showLegend: true, showGrid: true },
          layout: { x: (panelCount % 2) * 6, y: Math.floor(panelCount / 2) * 4, w: 6, h: 4 },
        })
      }
    } catch (e: any) {
      toast.error(e.message || 'Failed to import run data')
    }
  }, [getActiveDashboard, addPanel])

  const activeDashboard = getActiveDashboard()
  const selectedPanel = activeDashboard?.panels.find((p) => p.id === selectedPanelId) || null

  const handleCreateDashboard = useCallback(() => {
    const name = `Dashboard ${dashboards.length + 1}`
    createDashboard(name)
  }, [dashboards.length, createDashboard])

  const handleAddChart = useCallback(() => {
    if (!activeDashboard) return
    const table = tables[0]
    if (!table) return

    const numCols = table.columns.filter((c) => c.type === 'number')
    const strCols = table.columns.filter((c) => c.type === 'string')

    const panelCount = activeDashboard.panels.length
    const col = panelCount % 2
    const row = Math.floor(panelCount / 2)

    addPanel(activeDashboard.id, {
      title: `Chart ${panelCount + 1}`,
      chartType: newChartType,
      dataTableId: table.id,
      xField: strCols[0]?.id || table.columns[0]?.id || '',
      yField: numCols[0]?.id || table.columns[1]?.id || '',
      style: { colorScheme: 'default', showLegend: true, showGrid: true },
      layout: { x: col * 6, y: row * 4, w: 6, h: 4 },
    })
    setShowNewChartModal(false)
  }, [activeDashboard, tables, newChartType, addPanel])

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* ── Header ── */}
      <div style={{
        padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 12,
        borderBottom: `1px solid ${T.border}`, flexShrink: 0, background: T.surface1,
      }}>
        <LineChart size={16} color={T.cyan} />
        <h2 style={{
          fontFamily: FD, fontSize: FS.xl * 1.5, fontWeight: 600,
          color: T.text, margin: 0, letterSpacing: '0.04em',
        }}>
          VISUALIZATION STUDIO
        </h2>

        <div style={{ flex: 1 }} />

        {/* Dashboard selector */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setDashDropdown(!dashDropdown)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '5px 12px', background: T.surface3,
              border: `1px solid ${T.border}`, borderRadius: 4,
              color: T.text, fontFamily: F, fontSize: FS.sm,
              cursor: 'pointer', letterSpacing: '0.04em',
            }}
          >
            <Layers size={10} />
            {activeDashboard?.name || 'No Dashboard'}
            <ChevronDown size={10} />
          </button>
          {dashDropdown && (
            <div style={{
              position: 'absolute', top: '100%', right: 0, marginTop: 4,
              width: 240, zIndex: 100, background: T.surface2,
              border: `1px solid ${T.border}`, boxShadow: `0 8px 24px ${T.shadow}`,
              borderRadius: 4, overflow: 'hidden',
            }}>
              {dashboards.map((d) => (
                <button
                  key={d.id}
                  onClick={() => { setActiveDashboard(d.id); setDashDropdown(false) }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    width: '100%', padding: '8px 12px',
                    background: d.id === activeDashboardId ? `${T.cyan}12` : 'transparent',
                    border: 'none', color: d.id === activeDashboardId ? T.text : T.sec,
                    fontFamily: F, fontSize: FS.sm, cursor: 'pointer', textAlign: 'left',
                    borderBottom: `1px solid ${T.border}`,
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = T.surface4}
                  onMouseLeave={(e) => e.currentTarget.style.background = d.id === activeDashboardId ? `${T.cyan}12` : 'transparent'}
                >
                  <LayoutGrid size={10} />
                  {d.name}
                  <span style={{ marginLeft: 'auto', fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                    {d.panels.length} charts
                  </span>
                </button>
              ))}
              <button
                onClick={() => { handleCreateDashboard(); setDashDropdown(false) }}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6, width: '100%',
                  padding: '8px 12px', background: 'transparent', border: 'none',
                  color: T.cyan, fontFamily: F, fontSize: FS.sm, cursor: 'pointer',
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = T.surface4}
                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
              >
                <Plus size={10} /> New Dashboard
              </button>
            </div>
          )}
        </div>

        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setShowRunImport(!showRunImport)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '5px 12px', background: T.surface3,
              border: `1px solid ${T.border}`, borderRadius: 4,
              color: T.sec, fontFamily: F, fontSize: FS.sm,
              cursor: 'pointer', letterSpacing: '0.04em',
            }}
          >
            <FlaskConical size={10} />
            Import Run Data
            <ChevronDown size={10} />
          </button>
          {showRunImport && (
            <div style={{
              position: 'absolute', top: '100%', right: 0, marginTop: 4,
              width: 260, zIndex: 100, background: T.surface2,
              border: `1px solid ${T.border}`, boxShadow: `0 8px 24px ${T.shadow}`,
              borderRadius: 4, overflow: 'hidden', maxHeight: 320, overflowY: 'auto',
            }}>
              <div style={{ padding: '6px 10px', fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.1em', borderBottom: `1px solid ${T.border}` }}>
                SELECT A COMPLETED RUN
              </div>
              {recentRuns.length === 0 ? (
                <div style={{ padding: '10px 12px', fontFamily: F, fontSize: FS.xs, color: T.dim }}>
                  No completed runs found
                </div>
              ) : (
                recentRuns.map((run: any) => (
                  <button
                    key={run.id}
                    onClick={() => handleImportRunData(run.id)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 6,
                      width: '100%', padding: '6px 10px',
                      background: 'transparent', border: 'none',
                      borderBottom: `1px solid ${T.border}`,
                      color: T.sec, fontFamily: F, fontSize: FS.xs,
                      cursor: 'pointer', textAlign: 'left',
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = T.surface4 }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
                  >
                    <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#22c55e', flexShrink: 0 }} />
                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const }}>
                      {run.id.slice(0, 8)}
                    </span>
                    {run.started_at && (
                      <span style={{ fontSize: FS.xxs, color: T.dim }}>
                        {new Date(run.started_at).toLocaleDateString()}
                      </span>
                    )}
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        <button
          onClick={() => setShowNewChartModal(true)}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '5px 14px', background: `${T.cyan}1A`,
            border: `1px solid ${T.cyan}50`, borderRadius: 4,
            color: T.cyan, fontFamily: FD, fontSize: FS.sm,
            fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase' as const,
            cursor: 'pointer',
          }}
        >
          <Plus size={12} /> NEW CHART
        </button>
      </div>

      {/* ── Body ── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Left: Chart type selector */}
        <div style={{
          width: 200, minWidth: 200, borderRight: `1px solid ${T.border}`,
          background: T.surface0, display: 'flex', flexDirection: 'column', overflow: 'auto',
          padding: '12px 0',
        }}>
          <div style={{
            padding: '0 12px 10px', fontFamily: F, fontSize: FS.xxs, fontWeight: 900,
            letterSpacing: '0.12em', color: T.dim, textTransform: 'uppercase' as const,
          }}>
            CHART TYPES
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 4, padding: '0 8px' }}>
            {CHART_TYPES.map(({ type, label, icon }) => (
              <button
                key={type}
                onClick={() => setNewChartType(type)}
                style={{
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
                  padding: '8px 4px', background: newChartType === type ? `${T.cyan}15` : T.surface2,
                  border: `1px solid ${newChartType === type ? T.cyan + '40' : T.border}`,
                  borderRadius: 6, cursor: 'pointer',
                  color: newChartType === type ? T.cyan : T.sec,
                  fontFamily: F, fontSize: FS.xxs, letterSpacing: '0.04em',
                  transition: 'all 0.15s',
                }}
              >
                {icon}
                <span>{label}</span>
              </button>
            ))}
          </div>

          {/* Data tables for field picker */}
          <div style={{
            padding: '16px 12px 6px', fontFamily: F, fontSize: FS.xxs, fontWeight: 900,
            letterSpacing: '0.12em', color: T.dim, textTransform: 'uppercase' as const,
          }}>
            DATA TABLES
          </div>
          {tables.length === 0 ? (
            <div style={{ padding: '8px 12px', fontFamily: F, fontSize: FS.xxs, color: T.dim, fontStyle: 'italic' }}>
              No data tables available. Create one in the Data view.
            </div>
          ) : (
            tables.map((t) => (
              <div
                key={t.id}
                style={{
                  padding: '6px 12px', fontFamily: F, fontSize: FS.xs, color: T.sec,
                  borderBottom: `1px solid ${T.border}`,
                  display: 'flex', alignItems: 'center', gap: 6,
                }}
              >
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: T.cyan, flexShrink: 0 }} />
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const }}>{t.name}</span>
                <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>{t.rows.length}r</span>
              </div>
            ))
          )}
        </div>

        {/* Main: Chart Grid */}
        <div style={{ flex: 1, overflow: 'auto', padding: 20, background: T.bg }}>
          {!activeDashboard ? (
            <EmptyState
              icon={<LayoutGrid size={32} color={T.dim} style={{ opacity: 0.4 }} />}
              title="No Dashboard Selected"
              subtitle="Create a new dashboard to get started."
            />
          ) : activeDashboard.panels.length === 0 ? (
            <EmptyState
              icon={<BarChart3 size={32} color={T.dim} style={{ opacity: 0.4 }} />}
              title="No Charts Yet"
              subtitle="Click '+ NEW CHART' to add your first visualization."
            />
          ) : (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(420px, 1fr))',
              gap: 16,
            }}>
              <AnimatePresence>
                {activeDashboard.panels.map((panel) => (
                  <motion.div
                    key={panel.id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    transition={{ duration: 0.25 }}
                  >
                    <ChartCard
                      panel={panel}
                      tables={tables}
                      isSelected={selectedPanelId === panel.id}
                      onSelect={() => setSelectedPanelId(selectedPanelId === panel.id ? null : panel.id)}
                      onRemove={() => {
                        if (activeDashboard) removePanel(activeDashboard.id, panel.id)
                        if (selectedPanelId === panel.id) setSelectedPanelId(null)
                      }}
                    />
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </div>

        {/* Right: Chart Configurator */}
        {selectedPanel && activeDashboard && (
          <div style={{
            width: 280, minWidth: 280, borderLeft: `1px solid ${T.border}`,
            background: T.surface1, display: 'flex', flexDirection: 'column', overflow: 'auto',
          }}>
            <div style={{
              padding: '10px 12px', borderBottom: `1px solid ${T.border}`,
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
              <Settings size={10} color={T.cyan} />
              <span style={{
                fontFamily: F, fontSize: FS.xxs, fontWeight: 900,
                letterSpacing: '0.12em', color: T.dim, textTransform: 'uppercase' as const,
              }}>
                CHART CONFIG
              </span>
              <div style={{ flex: 1 }} />
              <button
                onClick={() => setSelectedPanelId(null)}
                style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', display: 'flex' }}
              >
                <X size={12} />
              </button>
            </div>

            <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* Title */}
              <ConfigField label="TITLE">
                <input
                  value={selectedPanel.title}
                  onChange={(e) => updatePanel(activeDashboard.id, selectedPanel.id, { title: e.target.value })}
                  style={{
                    width: '100%', padding: '5px 8px', background: T.surface3,
                    border: `1px solid ${T.border}`, borderRadius: 4,
                    color: T.text, fontFamily: F, fontSize: FS.sm, outline: 'none',
                  }}
                />
              </ConfigField>

              {/* Chart Type */}
              <ConfigField label="CHART TYPE">
                <select
                  value={selectedPanel.chartType}
                  onChange={(e) => updatePanel(activeDashboard.id, selectedPanel.id, { chartType: e.target.value as ChartType })}
                  style={{
                    width: '100%', padding: '5px 8px', background: T.surface3,
                    border: `1px solid ${T.border}`, borderRadius: 4,
                    color: T.text, fontFamily: F, fontSize: FS.sm, outline: 'none',
                  }}
                >
                  {CHART_TYPES.map(({ type, label }) => (
                    <option key={type} value={type}>{label}</option>
                  ))}
                </select>
              </ConfigField>

              {/* Data Table */}
              <ConfigField label="DATA TABLE">
                <select
                  value={selectedPanel.dataTableId}
                  onChange={(e) => updatePanel(activeDashboard.id, selectedPanel.id, { dataTableId: e.target.value })}
                  style={{
                    width: '100%', padding: '5px 8px', background: T.surface3,
                    border: `1px solid ${T.border}`, borderRadius: 4,
                    color: T.text, fontFamily: F, fontSize: FS.sm, outline: 'none',
                  }}
                >
                  {tables.map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
              </ConfigField>

              {/* X Field */}
              <ConfigField label="X AXIS FIELD">
                <FieldSelect
                  tableId={selectedPanel.dataTableId}
                  value={selectedPanel.xField}
                  onChange={(v) => updatePanel(activeDashboard.id, selectedPanel.id, { xField: v })}
                />
              </ConfigField>

              {/* Y Field */}
              <ConfigField label="Y AXIS FIELD">
                <FieldSelect
                  tableId={selectedPanel.dataTableId}
                  value={selectedPanel.yField}
                  onChange={(v) => updatePanel(activeDashboard.id, selectedPanel.id, { yField: v })}
                />
              </ConfigField>

              {/* Color Field */}
              <ConfigField label="COLOR FIELD (OPTIONAL)">
                <FieldSelect
                  tableId={selectedPanel.dataTableId}
                  value={selectedPanel.colorField || ''}
                  onChange={(v) => updatePanel(activeDashboard.id, selectedPanel.id, { colorField: v || undefined })}
                  allowNone
                />
              </ConfigField>

              {/* Color Scheme */}
              <ConfigField label="COLOR SCHEME">
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' as const }}>
                  {COLOR_SCHEMES.map((scheme) => (
                    <button
                      key={scheme.id}
                      onClick={() => updatePanel(activeDashboard.id, selectedPanel.id, {
                        style: { ...selectedPanel.style, colorScheme: scheme.id },
                      })}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 4,
                        padding: '3px 8px', borderRadius: 4,
                        background: selectedPanel.style.colorScheme === scheme.id ? `${T.cyan}15` : T.surface3,
                        border: `1px solid ${selectedPanel.style.colorScheme === scheme.id ? T.cyan + '40' : T.border}`,
                        color: selectedPanel.style.colorScheme === scheme.id ? T.cyan : T.sec,
                        fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
                      }}
                    >
                      <span style={{
                        display: 'flex', gap: 1,
                      }}>
                        {scheme.colors.slice(0, 3).map((c, i) => (
                          <span key={i} style={{ width: 6, height: 6, borderRadius: 2, background: c }} />
                        ))}
                      </span>
                      {scheme.label}
                    </button>
                  ))}
                </div>
              </ConfigField>

              {/* Toggles */}
              <ConfigField label="OPTIONS">
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <ToggleRow
                    label="Show Legend"
                    checked={selectedPanel.style.showLegend}
                    onChange={(v) => updatePanel(activeDashboard.id, selectedPanel.id, {
                      style: { ...selectedPanel.style, showLegend: v },
                    })}
                  />
                  <ToggleRow
                    label="Show Grid"
                    checked={selectedPanel.style.showGrid}
                    onChange={(v) => updatePanel(activeDashboard.id, selectedPanel.id, {
                      style: { ...selectedPanel.style, showGrid: v },
                    })}
                  />
                </div>
              </ConfigField>
            </div>
          </div>
        )}
      </div>

      {/* New Chart Modal */}
      <AnimatePresence>
        {showNewChartModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{
              position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              zIndex: 1000,
            }}
            onClick={() => setShowNewChartModal(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              style={{
                width: 420, background: T.surface1, border: `1px solid ${T.border}`,
                borderRadius: 8, overflow: 'hidden',
                boxShadow: `0 16px 48px ${T.shadowHeavy}`,
              }}
            >
              <div style={{
                padding: '14px 16px', borderBottom: `1px solid ${T.border}`, background: T.surface2,
                display: 'flex', alignItems: 'center', gap: 8,
              }}>
                <Plus size={12} color={T.cyan} />
                <span style={{
                  fontFamily: FD, fontSize: FS.md, fontWeight: 700, color: T.text, letterSpacing: '0.04em',
                }}>
                  New Chart
                </span>
                <div style={{ flex: 1 }} />
                <button
                  onClick={() => setShowNewChartModal(false)}
                  style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', display: 'flex' }}
                >
                  <X size={14} />
                </button>
              </div>

              <div style={{ padding: 16 }}>
                <div style={{
                  fontFamily: F, fontSize: FS.xxs, fontWeight: 700, color: T.dim,
                  letterSpacing: '0.1em', marginBottom: 10, textTransform: 'uppercase' as const,
                }}>
                  SELECT CHART TYPE
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6, marginBottom: 16 }}>
                  {CHART_TYPES.map(({ type, label, icon }) => (
                    <button
                      key={type}
                      onClick={() => setNewChartType(type)}
                      style={{
                        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
                        padding: '12px 8px', borderRadius: 6,
                        background: newChartType === type ? `${T.cyan}15` : T.surface3,
                        border: `1px solid ${newChartType === type ? T.cyan + '40' : T.border}`,
                        color: newChartType === type ? T.cyan : T.sec,
                        fontFamily: F, fontSize: FS.xs, cursor: 'pointer',
                        transition: 'all 0.15s',
                      }}
                    >
                      {icon}
                      {label}
                    </button>
                  ))}
                </div>

                {tables.length === 0 ? (
                  <div style={{
                    padding: 16, textAlign: 'center', fontFamily: F, fontSize: FS.sm,
                    color: T.dim, background: T.surface0, border: `1px solid ${T.border}`, borderRadius: 6,
                  }}>
                    No data tables available. Import data in the Data view first.
                  </div>
                ) : (
                  <button
                    onClick={handleAddChart}
                    style={{
                      width: '100%', padding: '10px 16px', background: T.cyan,
                      border: 'none', borderRadius: 6, color: '#000',
                      fontFamily: FD, fontSize: FS.sm, fontWeight: 700,
                      letterSpacing: '0.08em', textTransform: 'uppercase' as const,
                      cursor: 'pointer', display: 'flex', alignItems: 'center',
                      justifyContent: 'center', gap: 8,
                      transition: 'all 0.15s',
                      boxShadow: `0 0 16px ${T.cyan}30`,
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.boxShadow = `0 0 24px ${T.cyan}50`}
                    onMouseLeave={(e) => e.currentTarget.style.boxShadow = `0 0 16px ${T.cyan}30`}
                  >
                    <Plus size={12} /> CREATE CHART
                  </button>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/* ── Chart Card ── */
function ChartCard({
  panel, tables, isSelected, onSelect, onRemove,
}: {
  panel: ChartPanel
  tables: { id: string; name: string; columns: { id: string; name: string; type: string }[]; rows: Record<string, any>[] }[]
  isSelected: boolean
  onSelect: () => void
  onRemove: () => void
}) {
  const table = tables.find((t) => t.id === panel.dataTableId)
  const data = table?.rows || []
  const colors = getSchemeColors(panel.style.colorScheme)

  return (
    <div
      onClick={onSelect}
      style={{
        background: `linear-gradient(180deg, ${T.surface1} 0%, ${T.surface0} 100%)`,
        border: `1px solid ${isSelected ? T.cyan + '60' : T.border}`,
        borderRadius: 8, overflow: 'hidden', cursor: 'pointer',
        backdropFilter: 'blur(8px)', transition: 'all 0.2s',
        boxShadow: isSelected ? `0 0 16px ${T.cyan}20` : `0 4px 12px ${T.shadow}`,
      }}
    >
      {/* Header */}
      <div style={{
        padding: '8px 12px', borderBottom: `1px solid ${T.border}`, background: T.surface2,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span style={{
          fontFamily: F, fontSize: FS.sm, fontWeight: 700, color: T.text, flex: 1,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const,
        }}>
          {panel.title}
        </span>
        <span style={{
          fontFamily: F, fontSize: FS.xxs, color: T.dim,
          padding: '1px 6px', background: T.surface3, borderRadius: 3,
          letterSpacing: '0.06em', textTransform: 'uppercase' as const,
        }}>
          {panel.chartType}
        </span>
        <button
          onClick={(e) => { e.stopPropagation(); onRemove() }}
          style={{
            background: 'none', border: 'none', color: T.dim, cursor: 'pointer',
            display: 'flex', padding: 2, borderRadius: 3,
          }}
          onMouseEnter={(e) => { e.currentTarget.style.color = '#ef4444'; e.currentTarget.style.background = '#ef444420' }}
          onMouseLeave={(e) => { e.currentTarget.style.color = T.dim; e.currentTarget.style.background = 'transparent' }}
        >
          <Trash2 size={11} />
        </button>
      </div>

      {/* Chart Area */}
      <div style={{ padding: 12, height: 240 }}>
        {data.length === 0 ? (
          <div style={{
            height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: F, fontSize: FS.sm, color: T.dim, fontStyle: 'italic',
          }}>
            No data available
          </div>
        ) : (
          <RenderChart panel={panel} data={data} colors={colors} />
        )}
      </div>

      {/* Footer */}
      <div style={{
        padding: '6px 12px', borderTop: `1px solid ${T.border}`,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          {table?.name || 'Unknown table'}
        </span>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginLeft: 'auto' }}>
          {panel.xField} / {panel.yField}
        </span>
      </div>
    </div>
  )
}

/* ── Chart Renderer ── */
function RenderChart({ panel, data, colors }: { panel: ChartPanel; data: Record<string, any>[]; colors: string[] }) {
  const { chartType, xField, yField, style } = panel

  const tooltipStyle = {
    contentStyle: {
      background: T.surface2,
      border: `1px solid ${T.border}`,
      borderRadius: 4,
      fontFamily: F,
      fontSize: 10,
      color: T.text,
    },
  }

  const axisProps = {
    tick: { fontFamily: F, fontSize: 9, fill: T.dim },
    axisLine: { stroke: T.border },
    tickLine: { stroke: T.border },
  }

  switch (chartType) {
    case 'bar':
      return (
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data}>
            {style.showGrid && <CartesianGrid stroke={T.border} strokeDasharray="3 3" />}
            <XAxis dataKey={xField} {...axisProps} />
            <YAxis {...axisProps} />
            <Tooltip {...tooltipStyle} />
            {style.showLegend && <Legend wrapperStyle={{ fontFamily: F, fontSize: 9 }} />}
            <Bar dataKey={yField} radius={[3, 3, 0, 0]}>
              {data.map((_, i) => (
                <Cell key={`cell-${i}`} fill={colors[i % colors.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )

    case 'line':
      return (
        <ResponsiveContainer width="100%" height="100%">
          <ReLineChart data={data}>
            {style.showGrid && <CartesianGrid stroke={T.border} strokeDasharray="3 3" />}
            <XAxis dataKey={xField} {...axisProps} />
            <YAxis {...axisProps} />
            <Tooltip {...tooltipStyle} />
            {style.showLegend && <Legend wrapperStyle={{ fontFamily: F, fontSize: 9 }} />}
            <Line type="monotone" dataKey={yField} stroke={colors[0]} strokeWidth={2} dot={{ r: 3, fill: colors[0] }} />
          </ReLineChart>
        </ResponsiveContainer>
      )

    case 'area':
      return (
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            {style.showGrid && <CartesianGrid stroke={T.border} strokeDasharray="3 3" />}
            <XAxis dataKey={xField} {...axisProps} />
            <YAxis {...axisProps} />
            <Tooltip {...tooltipStyle} />
            {style.showLegend && <Legend wrapperStyle={{ fontFamily: F, fontSize: 9 }} />}
            <Area type="monotone" dataKey={yField} stroke={colors[0]} fill={colors[0]} fillOpacity={0.2} />
          </AreaChart>
        </ResponsiveContainer>
      )

    case 'scatter':
      return (
        <ResponsiveContainer width="100%" height="100%">
          <ReScatterChart>
            {style.showGrid && <CartesianGrid stroke={T.border} strokeDasharray="3 3" />}
            <XAxis dataKey={xField} type="number" name={xField} {...axisProps} />
            <YAxis dataKey={yField} type="number" name={yField} {...axisProps} />
            <Tooltip {...tooltipStyle} />
            {style.showLegend && <Legend wrapperStyle={{ fontFamily: F, fontSize: 9 }} />}
            <Scatter name={yField} data={data} fill={colors[0]}>
              {data.map((_, i) => (
                <Cell key={`cell-${i}`} fill={colors[i % colors.length]} />
              ))}
            </Scatter>
          </ReScatterChart>
        </ResponsiveContainer>
      )

    case 'radar': {
      return (
        <ResponsiveContainer width="100%" height="100%">
          <ReRadarChart data={data}>
            <PolarGrid stroke={T.border} />
            <PolarAngleAxis dataKey={xField} tick={{ fontFamily: F, fontSize: 8, fill: T.dim }} />
            <PolarRadiusAxis tick={{ fontFamily: F, fontSize: 8, fill: T.dim }} />
            <Tooltip {...tooltipStyle} />
            <ReRadar dataKey={yField} stroke={colors[0]} fill={colors[0]} fillOpacity={0.3} />
          </ReRadarChart>
        </ResponsiveContainer>
      )
    }

    case 'treemap': {
      const treemapData = data.map((d, i) => ({
        name: String(d[xField] || `Item ${i}`),
        size: Number(d[yField]) || 0,
        fill: colors[i % colors.length],
      }))
      return (
        <ResponsiveContainer width="100%" height="100%">
          <ReTreemap
            data={treemapData}
            dataKey="size"
            aspectRatio={4 / 3}
            stroke={T.border}
            content={<TreemapCell colors={colors} />}
          />
        </ResponsiveContainer>
      )
    }

    case 'histogram': {
      // Simple histogram using bar chart with binned data
      return (
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data}>
            {style.showGrid && <CartesianGrid stroke={T.border} strokeDasharray="3 3" />}
            <XAxis dataKey={xField} {...axisProps} />
            <YAxis {...axisProps} />
            <Tooltip {...tooltipStyle} />
            <Bar dataKey={yField} fill={colors[0]} radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )
    }

    case 'heatmap':
    case 'box':
    default:
      // Fallback to bar chart for types not directly supported by recharts
      return (
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data}>
            {style.showGrid && <CartesianGrid stroke={T.border} strokeDasharray="3 3" />}
            <XAxis dataKey={xField} {...axisProps} />
            <YAxis {...axisProps} />
            <Tooltip {...tooltipStyle} />
            {style.showLegend && <Legend wrapperStyle={{ fontFamily: F, fontSize: 9 }} />}
            <Bar dataKey={yField} fill={colors[0]} radius={[3, 3, 0, 0]}>
              {data.map((_, i) => (
                <Cell key={`cell-${i}`} fill={colors[i % colors.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )
  }
}

/* ── Shared sub-components ── */

function TreemapCell(props: any) {
  const { x, y, width, height, name, index, colors } = props
  if (!width || !height || width < 4 || height < 4) return null
  const fill = colors?.[(index || 0) % (colors?.length || 1)] || T.cyan
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={fill} fillOpacity={0.8} stroke={T.bg} strokeWidth={2} rx={2} />
      {width > 40 && height > 20 && (
        <text x={x + width / 2} y={y + height / 2} textAnchor="middle" dominantBaseline="central" fill={T.text} fontSize={9} fontFamily={F}>
          {String(name || '').substring(0, Math.floor(width / 7))}
        </text>
      )}
    </g>
  )
}

function EmptyState({ icon, title, subtitle }: { icon: React.ReactNode; title: string; subtitle: string }) {
  return (
    <div style={{
      height: '100%', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', gap: 12,
    }}>
      {icon}
      <div style={{ fontFamily: FD, fontSize: FS.lg, color: T.dim, fontWeight: 600 }}>{title}</div>
      <div style={{ fontFamily: F, fontSize: FS.sm, color: T.dim }}>{subtitle}</div>
    </div>
  )
}

function ConfigField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{
        fontFamily: F, fontSize: FS.xxs, fontWeight: 700, color: T.dim,
        letterSpacing: '0.1em', marginBottom: 5, textTransform: 'uppercase' as const,
      }}>
        {label}
      </div>
      {children}
    </div>
  )
}

function FieldSelect({
  tableId, value, onChange, allowNone,
}: {
  tableId: string; value: string; onChange: (v: string) => void; allowNone?: boolean
}) {
  const tables = useDataStore((s) => s.tables)
  const table = tables.find((t) => t.id === tableId)
  const columns = table?.columns || []

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      style={{
        width: '100%', padding: '5px 8px', background: T.surface3,
        border: `1px solid ${T.border}`, borderRadius: 4,
        color: T.text, fontFamily: F, fontSize: FS.sm, outline: 'none',
      }}
    >
      {allowNone && <option value="">None</option>}
      {columns.map((col) => (
        <option key={col.id} value={col.id}>{col.name} ({col.type})</option>
      ))}
    </select>
  )
}

function ToggleRow({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div
      onClick={() => onChange(!checked)}
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        cursor: 'pointer', padding: '2px 0',
      }}
    >
      <span style={{ fontFamily: F, fontSize: FS.xs, color: T.sec }}>{label}</span>
      <div style={{
        width: 28, height: 14, borderRadius: 7,
        background: checked ? `${T.cyan}40` : T.surface4,
        position: 'relative', transition: 'background 0.2s',
        border: `1px solid ${checked ? T.cyan + '60' : T.border}`,
      }}>
        <div style={{
          width: 10, height: 10, borderRadius: '50%',
          background: checked ? T.cyan : T.dim,
          position: 'absolute', top: 1,
          left: checked ? 15 : 1,
          transition: 'all 0.2s',
        }} />
      </div>
    </div>
  )
}
