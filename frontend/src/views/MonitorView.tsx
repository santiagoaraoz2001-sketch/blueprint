import { useState, useEffect, useCallback } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore } from '@/stores/metricsStore'
import { useRunStore } from '@/stores/runStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { useMonitorView } from '@/hooks/useRunMonitor'
import PipelineStrip from '@/components/Monitor/PipelineStrip'
import DashboardSelector from '@/components/Monitor/DashboardSelector'
import SystemPanel from '@/components/Monitor/SystemPanel'
import LogStream from '@/components/Monitor/LogStream'
import ComparisonView from '@/components/Monitor/ComparisonView'
import PopoutBar from '@/components/Monitor/PopoutBar'
import { ExternalLink, Square, GitCompare, Circle, Radio, Play } from 'lucide-react'
import { motion } from 'framer-motion'

function getUrlParams(): { runId?: string; popout?: boolean; compare?: boolean; runs?: string[] } {
  const params = new URLSearchParams(window.location.search)
  const hash = window.location.hash
  return {
    runId: params.get('runId') || undefined,
    popout: params.get('popout') === 'true',
    compare: hash === '#compare' || params.get('compare') === 'true',
    runs: params.get('runs')?.split(',').filter(Boolean),
  }
}

export default function MonitorView() {
  const [compareMode, setCompareMode] = useState(false)
  const [demoRunId, setDemoRunId] = useState<string | null>(null)

  const urlParams = getUrlParams()
  const isPopout = urlParams.popout

  // Use SELECTORS — never subscribe to the whole store
  const runStatus = useMetricsStore((s) => s.runStatus)
  const runName = useMetricsStore((s) => s.runName)
  const elapsed = useMetricsStore((s) => s.elapsed)
  const paperId = useMetricsStore((s) => s.paperId)
  const executionOrder = useMetricsStore((s) => s.monitorExecutionOrder)

  const activeRunId = useRunStore((s) => s.activeRunId)
  const isDemoMode = useSettingsStore((s) => s.demoMode)

  // Use active run from runStore if no specific run selected
  const monitorRunId = demoRunId || activeRunId || urlParams.runId || null
  useMonitorView(monitorRunId)

  // Handle compare mode from URL
  useEffect(() => {
    if (urlParams.compare) setCompareMode(true)
  }, [])

  // Status badge
  const statusConfig = {
    live: { label: 'LIVE', color: T.green, pulse: true },
    recorded: { label: 'RECORDED', color: T.dim, pulse: false },
    cancelled: { label: 'CANCELLED', color: T.amber, pulse: false },
    idle: { label: 'IDLE', color: T.dim, pulse: false },
  }
  const status = statusConfig[runStatus]

  const handlePopout = () => {
    const url = `${window.location.origin}?view=monitor&runId=${monitorRunId || ''}&popout=true`
    window.open(url, 'blueprint-monitor', 'width=900,height=700')
  }

  const handleStop = useCallback(async () => {
    await useRunStore.getState().stopRun()
    useMetricsStore.getState().setRunStatus('cancelled')
  }, [])

  const formatElapsed = (s: number) => {
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    const sec = s % 60
    if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`
    return `${m}:${sec.toString().padStart(2, '0')}`
  }

  // Popout layout
  if (isPopout) {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: T.bg }}>
        <PopoutBar
          runName={runName}
          paperId={paperId}
          status={status}
          elapsed={formatElapsed(elapsed)}
          phase={executionOrder.find(b => b.status === 'running')?.name || 'Idle'}
        />
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          <div style={{ width: 160, borderRight: `1px solid ${T.border}` }}>
            <PipelineStrip />
          </div>
          <div style={{ flex: 1, overflow: 'auto' }}>
            <DashboardSelector />
          </div>
        </div>
        <div style={{ height: 120, borderTop: `1px solid ${T.border}` }}>
          <LogStream compact />
        </div>
      </div>
    )
  }

  // Compare mode
  if (compareMode) {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: T.bg }}>
        {/* Top bar */}
        <div style={{
          height: 36,
          display: 'flex',
          alignItems: 'center',
          padding: '0 12px',
          gap: 10,
          borderBottom: `1px solid ${T.border}`,
          background: T.surface1,
        }}>
          <span style={{ fontFamily: F, fontSize: FS.xs, fontWeight: 700, color: T.text, letterSpacing: '0.08em' }}>
            COMPARE RUNS
          </span>
          <div style={{ flex: 1 }} />
          <button
            onClick={() => setCompareMode(false)}
            style={{
              padding: '3px 10px', background: T.surface2, border: `1px solid ${T.border}`,
              color: T.sec, fontFamily: F, fontSize: FS.xxs, cursor: 'pointer', letterSpacing: '0.06em',
            }}
          >
            EXIT COMPARE
          </button>
        </div>
        <ComparisonView initialRunIds={urlParams.runs} />
      </div>
    )
  }

  // Empty state
  const hasRun = monitorRunId || runStatus !== 'idle'
  if (!hasRun) {
    return (
      <div style={{
        height: '100%', display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', background: T.bg, gap: 12,
      }}>
        <Radio size={32} color={T.dim} />
        <span style={{ fontFamily: F, fontSize: FS.md, color: T.dim, letterSpacing: '0.06em' }}>
          No experiments running
        </span>
        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, opacity: 0.6 }}>
          Launch from a paper or the pipeline editor
        </span>
        {isDemoMode && (
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => {
              useMetricsStore.getState().resetMonitor()
              setDemoRunId(`demo-monitor-${Date.now()}`)
            }}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              marginTop: 8, padding: '6px 16px',
              background: `${T.cyan}15`, border: `1px solid ${T.cyan}40`,
              color: T.cyan, fontFamily: F, fontSize: FS.xs,
              cursor: 'pointer', letterSpacing: '0.06em', fontWeight: 700,
            }}
          >
            <Play size={12} fill={T.cyan} />
            START DEMO RUN
          </motion.button>
        )}
      </div>
    )
  }

  // Main monitor layout
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: T.bg }}>
      {/* Top bar */}
      <div style={{
        height: 36,
        display: 'flex',
        alignItems: 'center',
        padding: '0 12px',
        gap: 10,
        borderBottom: `1px solid ${T.border}`,
        background: T.surface1,
        flexShrink: 0,
      }}>
        {/* Run selector */}
        <span style={{ fontFamily: F, fontSize: FS.xs, fontWeight: 700, color: T.text, letterSpacing: '0.06em' }}>
          {runName || 'Run'}
        </span>

        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          {formatElapsed(elapsed)}
        </span>

        <div style={{ flex: 1 }} />

        {/* Compare toggle */}
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => setCompareMode(true)}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '3px 8px', background: T.surface2, border: `1px solid ${T.border}`,
            color: T.sec, fontFamily: F, fontSize: FS.xxs, cursor: 'pointer', letterSpacing: '0.06em',
          }}
        >
          <GitCompare size={10} />
          COMPARE
        </motion.button>

        {/* Pop out */}
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={handlePopout}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '3px 8px', background: T.surface2, border: `1px solid ${T.border}`,
            color: T.sec, fontFamily: F, fontSize: FS.xxs, cursor: 'pointer', letterSpacing: '0.06em',
          }}
        >
          <ExternalLink size={10} />
          POP OUT
        </motion.button>

        {/* Stop button */}
        {runStatus === 'live' && (
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={handleStop}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '3px 8px', background: `${T.red}15`, border: `1px solid ${T.red}40`,
              color: T.red, fontFamily: F, fontSize: FS.xxs, cursor: 'pointer', letterSpacing: '0.06em',
              fontWeight: 700,
            }}
          >
            <Square size={8} fill={T.red} />
            STOP
          </motion.button>
        )}

        {/* Status badge */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 5,
          padding: '2px 8px',
          background: `${status.color}10`,
          border: `1px solid ${status.color}30`,
        }}>
          <Circle
            size={6}
            fill={status.color}
            color={status.color}
            style={status.pulse ? { animation: 'pulse-glow 1.5s ease-in-out infinite' } : undefined}
          />
          <span style={{
            fontFamily: F, fontSize: FS.xxs, fontWeight: 900,
            color: status.color, letterSpacing: '0.1em',
          }}>
            {status.label}
          </span>
        </div>

        {/* Pulse animation */}
        {status.pulse && (
          <style>{`
            @keyframes pulse-glow {
              0%, 100% { opacity: 1; }
              50% { opacity: 0.4; }
            }
          `}</style>
        )}
      </div>

      {/* Main content */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Pipeline Strip - 200px */}
        <div style={{ width: 200, minWidth: 200, borderRight: `1px solid ${T.border}`, overflow: 'auto' }}>
          <PipelineStrip />
        </div>

        {/* Center - Adaptive Dashboard */}
        <div style={{ flex: 1, overflow: 'auto' }}>
          <DashboardSelector />
        </div>

        {/* System Panel - 280px */}
        <div style={{ width: 280, minWidth: 280, borderLeft: `1px solid ${T.border}`, overflow: 'auto' }}>
          <SystemPanel
            runId={monitorRunId}
            paperId={paperId}
            elapsed={elapsed}
            formatElapsed={formatElapsed}
          />
        </div>
      </div>

      {/* Log Stream - 150px */}
      <div style={{ height: 150, minHeight: 150, borderTop: `1px solid ${T.border}`, flexShrink: 0 }}>
        <LogStream />
      </div>
    </div>
  )
}
