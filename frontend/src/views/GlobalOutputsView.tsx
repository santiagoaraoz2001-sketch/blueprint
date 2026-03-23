import { useState, useCallback } from 'react'
import { T, F, FD, FS } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { useOutputsDashboard, useLiveRuns } from '@/hooks/useOutputs'
import EmptyState from '@/components/shared/EmptyState'
import RunRow from '@/components/Outputs/RunRow'
import LiveRunBanner from '@/components/Outputs/LiveRunBanner'
import { Package, RefreshCw, GitCompare, Loader2 } from 'lucide-react'

type StatusFilter = '' | 'complete' | 'running' | 'failed' | 'cancelled'

const STATUS_TABS: { id: StatusFilter; label: string }[] = [
  { id: '',          label: 'ALL' },
  { id: 'complete',  label: 'COMPLETE' },
  { id: 'running',   label: 'RUNNING' },
  { id: 'failed',    label: 'FAILED' },
  { id: 'cancelled', label: 'CANCELLED' },
]

export default function GlobalOutputsView() {
  const projectId = useUIStore((s) => s.selectedProjectId)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('')
  const [selectedIds, setSelectedIds] = useState<string[]>([])

  const {
    data: dashboard,
    isLoading,
    refetch,
    isFetching,
  } = useOutputsDashboard({
    projectId,
    status: statusFilter || undefined,
    limit: 100,
  })

  const { data: liveRuns } = useLiveRuns()

  const runs = dashboard?.runs ?? []
  const totalRuns = dashboard?.total_runs ?? 0
  const totalArtifacts = dashboard?.total_artifacts ?? 0
  const typeCounts = dashboard?.artifact_type_counts ?? {}

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id].slice(-4)
    )
  }, [])

  const handleCompare = () => {
    if (selectedIds.length >= 2) {
      useUIStore.getState().openComparison(selectedIds)
    }
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ padding: '16px 16px 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
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
            GLOBAL OUTPUTS
          </h2>

          <div style={{ flex: 1 }} />

          {/* Compare button */}
          {selectedIds.length >= 2 && (
            <button
              onClick={handleCompare}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: '4px 12px',
                background: `${T.cyan}14`,
                border: `1px solid ${T.cyan}33`,
                color: T.cyan,
                fontFamily: F,
                fontSize: FS.xs,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = `${T.cyan}22`
                e.currentTarget.style.borderColor = `${T.cyan}55`
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = `${T.cyan}14`
                e.currentTarget.style.borderColor = `${T.cyan}33`
              }}
            >
              <GitCompare size={10} />
              Compare {selectedIds.length}
            </button>
          )}

          {/* Refresh */}
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              padding: '4px 10px',
              background: T.surface3,
              border: `1px solid ${T.border}`,
              color: T.sec,
              fontFamily: F,
              fontSize: FS.xs,
              cursor: 'pointer',
              opacity: isFetching ? 0.5 : 1,
            }}
          >
            <RefreshCw size={10} style={isFetching ? { animation: 'spin 1s linear infinite' } : undefined} />
            REFRESH
          </button>
        </div>

        {/* Stats line */}
        <div
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.dim,
            marginTop: 6,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <span>{totalRuns} run{totalRuns !== 1 ? 's' : ''}</span>
          <span style={{ color: T.muted }}>|</span>
          <span>{totalArtifacts} artifact{totalArtifacts !== 1 ? 's' : ''}</span>
          {Object.keys(typeCounts).length > 0 && (
            <>
              <span style={{ color: T.muted }}>|</span>
              {Object.entries(typeCounts).map(([type, count]) => (
                <span key={type} style={{ color: T.sec }}>
                  {count} {type}
                </span>
              ))}
            </>
          )}
        </div>
      </div>

      {/* Status filter tabs */}
      <div
        style={{
          display: 'flex',
          gap: 0,
          padding: '10px 16px 0',
          borderBottom: `1px solid ${T.border}`,
        }}
      >
        {STATUS_TABS.map((tab) => {
          const active = statusFilter === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => { setStatusFilter(tab.id); setSelectedIds([]) }}
              style={{
                padding: '6px 14px',
                background: active ? T.surface2 : 'transparent',
                border: 'none',
                borderBottom: active ? `2px solid ${T.cyan}` : '2px solid transparent',
                color: active ? T.cyan : T.dim,
                fontFamily: F,
                fontSize: FS.xs,
                letterSpacing: '0.08em',
                cursor: 'pointer',
                marginBottom: -1,
                transition: 'color 0.1s',
              }}
            >
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {isLoading ? (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 60,
              gap: 8,
            }}
          >
            <Loader2
              size={16}
              color={T.dim}
              style={{ animation: 'spin 1s linear infinite' }}
            />
            <span style={{ fontFamily: F, fontSize: FS.md, color: T.dim }}>
              Loading outputs...
            </span>
          </div>
        ) : runs.length === 0 && (!liveRuns || liveRuns.length === 0) ? (
          <EmptyState
            icon={Package}
            title="No outputs yet"
            description="Execute a pipeline to see runs and artifacts here. Every output is tracked with full lineage."
            action={{
              label: 'Go to Pipelines',
              onClick: () => useUIStore.getState().setView('editor'),
            }}
          />
        ) : (
          <>
            {/* Live runs */}
            <div style={{ paddingTop: liveRuns && liveRuns.length > 0 ? 12 : 0 }}>
              <LiveRunBanner runs={liveRuns ?? []} />
            </div>

            {/* Historical runs */}
            <div>
              {runs.map((run) => (
                <RunRow
                  key={run.id}
                  run={run}
                  selected={selectedIds.includes(run.id)}
                  onToggleSelect={toggleSelect}
                />
              ))}
            </div>
          </>
        )}
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
