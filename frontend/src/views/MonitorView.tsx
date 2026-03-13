import { useState, useEffect } from 'react'
import { T, F, FD, FS } from '@/lib/design-tokens'
import { useMetricsStore } from '@/stores/metricsStore'
import { useRunMonitor } from '@/hooks/useRunMonitor'
import PipelineStrip from '@/components/Monitor/PipelineStrip'
import DashboardSelector from '@/components/Monitor/DashboardSelector'
import SystemPanel from '@/components/Monitor/SystemPanel'
import LogStream from '@/components/Monitor/LogStream'
import StatusBadge from '@/components/shared/StatusBadge'
import { ExternalLink, ArrowLeft } from 'lucide-react'
import { useUIStore } from '@/stores/uiStore'

export default function MonitorView() {
  const [runId, setRunId] = useState<string | null>(null)
  const [viewedBlockId, setViewedBlockId] = useState<string | null>(null)
  const [showLogs, setShowLogs] = useState(true)

  // Get runId from URL params or from latest active run
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const urlRunId = params.get('runId')
    if (urlRunId) {
      setRunId(urlRunId)
      return
    }
    // Find latest running run
    const runs = useMetricsStore.getState().runs
    const running = Object.entries(runs).find(([, r]) => r.status === 'running')
    if (running) setRunId(running[0])
  }, [])

  const { run, status } = useRunMonitor(runId, true)
  const setView = useUIStore((s) => s.setView)

  const handlePopOut = () => {
    if (runId) {
      window.open(
        `/monitor/${runId}?popout=true`,
        'blueprint-monitor',
        'width=900,height=700'
      )
    }
  }

  if (!runId || !run) {
    return (
      <div style={{ padding: 20 }}>
        <h1 style={{ fontFamily: FD, fontSize: FS.xl * 1.5, fontWeight: 600, color: T.text, margin: 0 }}>
          MONITOR
        </h1>
        <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, marginTop: 8 }}>
          No active run selected. Start a pipeline to monitor it here.
        </p>
        <button
          onClick={() => setView('editor')}
          style={{
            marginTop: 16, padding: '6px 14px', background: `${T.cyan}14`,
            border: `1px solid ${T.cyan}33`, color: T.cyan, fontFamily: F,
            fontSize: FS.xs, cursor: 'pointer', letterSpacing: '0.08em',
          }}
        >
          GO TO PIPELINE EDITOR
        </button>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Top bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '8px 16px',
        borderBottom: `1px solid ${T.border}`, background: T.surface1,
      }}>
        <button
          onClick={() => setView('dashboard')}
          style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 2 }}
        >
          <ArrowLeft size={14} />
        </button>
        <span style={{ fontFamily: F, fontSize: FS.md, color: T.text, fontWeight: 700 }}>
          {run.pipelineName || 'Pipeline Run'}
        </span>
        <StatusBadge status={status || 'running'} />
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          {Math.round(run.overallProgress * 100)}%
        </span>
        {run.eta != null && (
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
            ETA: {Math.round(run.eta / 60)}m
          </span>
        )}
        <div style={{ flex: 1 }} />
        <button
          onClick={() => setShowLogs(!showLogs)}
          style={{
            padding: '3px 8px', background: 'none', border: `1px solid ${T.border}`,
            color: T.sec, fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
          }}
        >
          {showLogs ? 'HIDE LOGS' : 'SHOW LOGS'}
        </button>
        <button
          onClick={handlePopOut}
          style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 2 }}
        >
          <ExternalLink size={12} />
        </button>
      </div>

      {/* Pipeline strip */}
      <PipelineStrip runId={runId} viewedBlockId={viewedBlockId} onBlockClick={setViewedBlockId} />

      {/* Main content area */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Dashboard center */}
        <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
          <DashboardSelector runId={runId} viewedBlockId={viewedBlockId} />
        </div>

        {/* System panel right */}
        <div style={{ width: 220, borderLeft: `1px solid ${T.border}`, overflow: 'auto' }}>
          <SystemPanel runId={runId} />
        </div>
      </div>

      {/* Log stream bottom */}
      {showLogs && (
        <div style={{ height: 180, borderTop: `1px solid ${T.border}` }}>
          <LogStream runId={runId} />
        </div>
      )}
    </div>
  )
}
