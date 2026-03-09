import { useState, useEffect, useCallback } from 'react'
import { T, F, FS, FD } from '@/lib/design-tokens'
import { api } from '@/api/client'
import ResultsTable, { type RunRow } from '@/components/Results/ResultsTable'
import MetricChart from '@/components/Results/MetricChart'
import RunComparison from '@/components/Results/RunComparison'
import EmptyState from '@/components/shared/EmptyState'
import { BarChart3, Table, LineChart, GitCompare, RefreshCw } from 'lucide-react'
import { useSettingsStore } from '@/stores/settingsStore'
import { DEMO_RUNS } from '@/lib/demo-data'
import toast from 'react-hot-toast'

type Tab = 'table' | 'chart' | 'compare'

export default function ResultsView() {
  const [runs, setRuns] = useState<RunRow[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<Tab>('table')
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [statusFilter, setStatusFilter] = useState<string>('')
  const demoMode = useSettingsStore((s) => s.demoMode)

  const fetchRuns = useCallback(async () => {
    setLoading(true)
    if (demoMode) {
      const demoRuns: RunRow[] = DEMO_RUNS.map((r) => ({
        id: r.id,
        pipeline_id: r.pipeline_id,
        status: r.status,
        started_at: r.started_at,
        finished_at: r.completed_at || null,
        duration_seconds: r.completed_at ? 150 : null,
        error_message: r.status === 'failed' ? 'Demo error' : null,
        config_snapshot: {},
        metrics: r.metrics as Record<string, unknown>,
      }))
      setRuns(statusFilter ? demoRuns.filter((r) => r.status === statusFilter) : demoRuns)
      setLoading(false)
      return
    }
    try {
      const params = new URLSearchParams()
      if (statusFilter) params.set('status', statusFilter)
      params.set('limit', '100')
      const data = await api.get<RunRow[]>(`/runs?${params}`)
      setRuns(data)
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to load runs'
      toast.error(msg)
      console.error('[ResultsView] fetchRuns error:', e)
    } finally {
      setLoading(false)
    }
  }, [statusFilter, demoMode])

  useEffect(() => {
    fetchRuns()
  }, [fetchRuns])

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id].slice(-4)
    )
  }

  const selectedRuns = runs.filter((r) => selectedIds.includes(r.id))

  const tabs: { id: Tab; label: string; icon: typeof Table }[] = [
    { id: 'table', label: 'TABLE', icon: Table },
    { id: 'chart', label: 'CHART', icon: LineChart },
    { id: 'compare', label: 'COMPARE', icon: GitCompare },
  ]

  const selectStyle: React.CSSProperties = {
    background: T.surface2,
    border: `1px solid ${T.border}`,
    color: T.sec,
    fontFamily: F,
    fontSize: FS.xs,
    padding: '3px 8px',
    outline: 'none',
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div
        style={{
          padding: '12px 16px 0',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}
      >
        <h2
          style={{
            fontFamily: FD,
            fontSize: FS.h2,
            fontWeight: 600,
            color: T.text,
            margin: 0,
            letterSpacing: '0.04em',
          }}
        >
          RESULTS EXPLORER
        </h2>

        <div style={{ flex: 1 }} />

        {/* Status filter */}
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={selectStyle}>
          <option value="">All statuses</option>
          <option value="complete">Complete</option>
          <option value="running">Running</option>
          <option value="failed">Failed</option>
        </select>

        {/* Refresh */}
        <button
          onClick={fetchRuns}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            padding: '3px 10px',
            background: T.surface3,
            border: `1px solid ${T.border}`,
            color: T.sec,
            fontFamily: F,
            fontSize: FS.xs,
          }}
        >
          <RefreshCw size={10} />
          REFRESH
        </button>
      </div>

      {/* Tabs */}
      <div
        style={{
          display: 'flex',
          gap: 0,
          padding: '10px 16px 0',
          borderBottom: `1px solid ${T.border}`,
        }}
      >
        {tabs.map((tab) => {
          const Icon = tab.icon
          const active = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: '6px 14px',
                background: active ? T.surface2 : 'transparent',
                border: 'none',
                borderBottom: active ? `2px solid ${T.cyan}` : '2px solid transparent',
                color: active ? T.cyan : T.dim,
                fontFamily: F,
                fontSize: FS.xs,
                letterSpacing: '0.08em',
                marginBottom: -1,
              }}
            >
              <Icon size={10} />
              {tab.label}
              {tab.id === 'compare' && selectedIds.length >= 2 && (
                <span
                  style={{
                    background: T.cyan,
                    color: T.bg,
                    fontSize: FS.xxs,
                    padding: '0 4px',
                    marginLeft: 2,
                    fontWeight: 700,
                  }}
                >
                  {selectedIds.length}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center' }}>
            <span style={{ fontFamily: F, fontSize: FS.md, color: T.dim }}>Loading runs...</span>
          </div>
        ) : runs.length === 0 ? (
          <EmptyState
            icon={BarChart3}
            title="No runs yet"
            description="Execute a pipeline to see results here"
          />
        ) : (
          <>
            {activeTab === 'table' && (
              <ResultsTable
                runs={runs}
                selectedIds={selectedIds}
                onToggleSelect={toggleSelect}
                onRowClick={() => {}}
              />
            )}
            {activeTab === 'chart' && <MetricChart runs={runs} />}
            {activeTab === 'compare' && <RunComparison runs={selectedRuns} />}
          </>
        )}
      </div>
    </div>
  )
}
