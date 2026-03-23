import { useState, useEffect, useCallback } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useRunMonitor } from '@/hooks/useRunMonitor'
import { useRunStore } from '@/stores/runStore'
import { useMetricsStore } from '@/stores/metricsStore'
import { useUIStore } from '@/stores/uiStore'
import { api } from '@/api/client'
import PipelineStrip from '@/components/Monitor/PipelineStrip'
import DashboardSelector from '@/components/Monitor/DashboardSelector'
import SystemPanel from '@/components/Monitor/SystemPanel'
import LogStream from '@/components/Monitor/LogStream'
import ComparisonView from '@/components/Monitor/ComparisonView'
import PluginPanelContainer from '@/components/Monitor/PluginPanelContainer'
import { runMetricsToTable } from '@/services/metricsBridge'
import { Activity, ExternalLink, Wifi, WifiOff, Radio, Archive, TableProperties, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'

export default function MonitorView() {
  const monitorRunId = useUIStore((s) => s.monitorRunId)
  const compareRunIds = useUIStore((s) => s.compareRunIds)

  // If no run specified, try to get the active run from runStore
  const activeRunId = useRunStore((s) => s.activeRunId)
  const runId = monitorRunId || activeRunId

  // Comparison mode
  if (compareRunIds && compareRunIds.length >= 2) {
    return <ComparisonView runIds={compareRunIds} />
  }

  if (!runId) {
    return <NoRunState />
  }

  return <MonitorContent runId={runId} />
}

function NoRunState() {
  const [recentRuns, setRecentRuns] = useState<any[]>([])
  const setMonitorRunId = useUIStore((s) => s.setMonitorRunId)

  useEffect(() => {
    api
      .get<any[]>('/runs?limit=10')
      .then((runs) => setRecentRuns(runs || []))
      .catch(() => setRecentRuns([]))
  }, [])

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        gap: 16,
        padding: 32,
      }}
    >
      <Activity size={24} color={T.dim} />
      <span style={{ fontFamily: F, fontSize: FS.sm, color: T.dim }}>
        No active run to monitor
      </span>
      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
        Start a pipeline run or select a recent run below
      </span>
      {recentRuns.length > 0 && (
        <div style={{ marginTop: 8, width: '100%', maxWidth: 400 }}>
          <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.1em', marginBottom: 6 }}>
            RECENT RUNS
          </div>
          {recentRuns.map((run: any) => (
            <button
              key={run.id}
              onClick={() => setMonitorRunId(run.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                width: '100%',
                padding: '8px 12px',
                background: 'transparent',
                border: `1px solid ${T.border}`,
                borderBottom: 'none',
                cursor: 'pointer',
                fontFamily: F,
                fontSize: FS.xs,
                color: T.text,
                textAlign: 'left',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = T.surface2 }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
            >
              <div
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: run.status === 'complete' ? '#22c55e' : run.status === 'running' ? '#f59e0b' : run.status === 'failed' ? '#ff433d' : T.dim,
                  flexShrink: 0,
                }}
              />
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {run.id.slice(0, 8)}
              </span>
              <span style={{ color: T.dim, fontSize: FS.xxs }}>
                {run.status}
              </span>
              {run.started_at && (
                <span style={{ color: T.dim, fontSize: FS.xxs }}>
                  {new Date(run.started_at).toLocaleDateString()}
                </span>
              )}
            </button>
          ))}
          <div style={{ borderBottom: `1px solid ${T.border}` }} />
        </div>
      )}
    </div>
  )
}

function MonitorContent({ runId }: { runId: string }) {
  const { isConnected: _isConnected, overallProgress, eta, status } = useRunMonitor(runId)
  const [viewedBlockId, setViewedBlockId] = useState<string | null>(null)
  const run = useMetricsStore((s) => s.runs[runId])
  const pipelineName = run?.pipelineName || ''
  const isReplay = status === 'complete' || status === 'failed'

  // Default to active block when not manually selected; for historical runs, use first block
  const activeBlockId = useMetricsStore((s) => s.runs[runId]?.activeBlockId)
  const firstBlockId = useMetricsStore((s) => s.runs[runId]?.executionOrder[0] ?? null)
  const effectiveBlockId = viewedBlockId || activeBlockId || firstBlockId

  const handleSelectBlock = useCallback((blockId: string) => {
    setViewedBlockId(blockId)
  }, [])

  const handlePopout = useCallback(() => {
    const url = `${window.location.origin}?view=monitor&runId=${runId}&popout=true`
    window.open(url, `monitor-${runId}`, 'width=1200,height=800')
  }, [runId])

  const handleOpenInDataView = useCallback(async () => {
    try {
      await runMetricsToTable(runId, pipelineName || undefined)
      useUIStore.getState().setView('data')
    } catch (e: any) {
      toast.error(e.message || 'Failed to export metrics')
    }
  }, [runId, pipelineName])

  const pct = Math.round(overallProgress * 100)

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      {/* Context bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '6px 12px',
          borderBottom: `1px solid ${T.border}`,
          flexShrink: 0,
          background: T.surface1,
        }}
      >
        <Activity size={12} color={T.cyan} />
        <span
          style={{
            fontFamily: F,
            fontSize: FS.sm,
            fontWeight: 700,
            color: T.text,
            letterSpacing: '0.06em',
          }}
        >
          MONITOR
        </span>
        {pipelineName && (
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
            {pipelineName}
          </span>
        )}

        {/* Progress bar */}
        <div style={{ width: 120, height: 4, background: T.surface3, overflow: 'hidden' }}>
          <div
            style={{
              width: `${pct}%`,
              height: '100%',
              background: T.cyan,
              transition: 'width 0.3s ease',
            }}
          />
        </div>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.cyan }}>{pct}%</span>

        {eta != null && eta > 0 && (
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
            ETA {Math.round(eta)}s
          </span>
        )}

        <div style={{ flex: 1 }} />

        {/* Status badges */}
        {isReplay && (
          <span
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              fontFamily: F,
              fontSize: FS.xxs,
              color: T.dim,
              background: T.surface3,
              padding: '2px 8px',
            }}
          >
            <Archive size={9} />
            Recorded
          </span>
        )}

        {!isReplay && <SSEStatusBadge />}

        {status === 'running' && (
          <span
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              fontFamily: F,
              fontSize: FS.xxs,
              color: T.cyan,
            }}
          >
            <Radio size={9} style={{ animation: 'pulse 1.5s ease-in-out infinite' }} />
          </span>
        )}

        <button
          onClick={handleOpenInDataView}
          title="Open metrics in Data View"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            padding: '2px 8px',
            background: `${T.cyan}14`,
            border: `1px solid ${T.cyan}33`,
            color: T.cyan,
            fontFamily: F,
            fontSize: FS.xxs,
            letterSpacing: '0.06em',
            cursor: 'pointer',
          }}
        >
          <TableProperties size={10} />
          Data View
        </button>

        <button
          onClick={handlePopout}
          title="Pop out to new window"
          style={{
            background: 'none',
            border: 'none',
            color: T.dim,
            cursor: 'pointer',
            padding: 2,
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <ExternalLink size={12} />
        </button>
      </div>

      {/* Main content */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Left: Pipeline strip */}
        <div
          style={{
            width: 200,
            minWidth: 200,
            borderRight: `1px solid ${T.border}`,
            overflowY: 'auto',
            background: T.surface0,
            flexShrink: 0,
          }}
        >
          <PipelineStrip
            runId={runId}
            viewedBlockId={effectiveBlockId}
            onSelectBlock={handleSelectBlock}
          />
        </div>

        {/* Center: Dashboard + Plugin panels */}
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <div style={{ flex: 1, overflow: 'hidden' }}>
            <DashboardSelector runId={runId} viewedBlockId={effectiveBlockId} />
          </div>
          <div style={{ flexShrink: 0, overflowY: 'auto', maxHeight: '40%', borderTop: `1px solid ${T.border}` }}>
            <PluginPanelContainer runId={runId} />
          </div>
        </div>

        {/* Right: System + Logs */}
        <div
          style={{
            width: 260,
            minWidth: 260,
            borderLeft: `1px solid ${T.border}`,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            flexShrink: 0,
          }}
        >
          {/* System gauges */}
          <div
            style={{
              borderBottom: `1px solid ${T.border}`,
              flexShrink: 0,
            }}
          >
            <SystemPanel runId={runId} />
          </div>

          {/* Log stream */}
          <div style={{ flex: 1, overflow: 'hidden' }}>
            <LogStream runId={runId} />
          </div>
        </div>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
      `}</style>
    </div>
  )
}

function SSEStatusBadge() {
  const sseStatus = useRunStore((s) => s.sseStatus)

  const config = {
    connected: { color: '#22c55e', icon: <Wifi size={9} />, label: 'Live' },
    reconnecting: { color: '#f59e0b', icon: <Loader2 size={9} style={{ animation: 'spin 1s linear infinite' }} />, label: 'Reconnecting...' },
    stale: { color: '#ff433d', icon: <WifiOff size={9} />, label: 'Connection lost' },
    disconnected: { color: T.dim, icon: <WifiOff size={9} />, label: 'Disconnected' },
  }[sseStatus]

  return (
    <span
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        fontFamily: F,
        fontSize: FS.xxs,
        color: config.color,
      }}
    >
      {config.icon}
      {config.label}
    </span>
  )
}
