import { useEffect, useMemo, lazy, Suspense } from 'react'
import { T, F, FS, FCODE } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { useRunStore } from '@/stores/runStore'
import { useMonitorStore } from '@/stores/monitorStore'
import { motion, AnimatePresence } from 'framer-motion'
import { X, ChevronDown, Maximize2, BarChart3, Terminal, FolderOutput } from 'lucide-react'

const ExecutionTimeline = lazy(() => import('@/components/Monitor/ExecutionTimeline'))
const LogViewer = lazy(() => import('@/components/Monitor/LogViewer'))
const ArtifactBrowser = lazy(() => import('@/components/Artifacts/ArtifactBrowser'))

export interface MonitorBlock {
  id: string
  name: string
  status: string
  elapsed?: number
  log?: string
  output?: Record<string, any>
}

interface PipelineMonitorProps {
  visible: boolean
  blocks: MonitorBlock[]
  progress: number
  logs: string[]
  onClose: () => void
}

type MonitorTab = 'timeline' | 'logs' | 'outputs'

const TABS: { key: MonitorTab; label: string; icon: typeof BarChart3 }[] = [
  { key: 'timeline', label: 'Timeline', icon: BarChart3 },
  { key: 'logs', label: 'Logs', icon: Terminal },
  { key: 'outputs', label: 'Outputs', icon: FolderOutput },
]

export default function PipelineMonitor({
  visible,
  blocks,
  progress,
  onClose,
}: PipelineMonitorProps) {
  const activeRunId = useRunStore((s) => s.activeRunId)
  const runStatus = useRunStore((s) => s.status)
  const activeTab = useMonitorStore((s) => s.activeTab)
  const setActiveTab = useMonitorStore((s) => s.setActiveTab)
  const startMonitoring = useMonitorStore((s) => s.startMonitoring)

  // Build node labels map from blocks prop (pipeline node labels)
  const nodeLabels = useMemo(() => {
    const labels: Record<string, string> = {}
    for (const b of blocks) {
      labels[b.id] = b.name
    }
    return labels
  }, [blocks])

  // Start/stop monitoring when run starts/stops
  useEffect(() => {
    if (activeRunId && runStatus === 'running') {
      startMonitoring(activeRunId, nodeLabels)
    }
    return () => {
      // Don't stop monitoring when component unmounts during a run —
      // only stop when the run actually ends
    }
  }, [activeRunId, runStatus, startMonitoring, nodeLabels])

  // Stop monitoring when run completes
  useEffect(() => {
    if (runStatus !== 'running' && runStatus !== 'idle') {
      // Don't stop — keep the data for historical viewing
    }
  }, [runStatus])

  const pct = Math.round(progress * 100)
  const monitorRunStatus = useMonitorStore((s) => s.runStatus)
  const logCount = useMonitorStore((s) => s.logs.length)

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ y: '100%' }}
          animate={{ y: 0 }}
          exit={{ y: '100%' }}
          transition={{ type: 'spring', damping: 30, stiffness: 300 }}
          style={{
            position: 'absolute',
            bottom: 0,
            left: 0,
            right: 0,
            height: 320,
            background: T.surface1,
            borderTop: `1px solid ${T.borderHi}`,
            display: 'flex',
            flexDirection: 'column',
            zIndex: 50,
          }}
        >
          {/* Header with tab bar */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              padding: '0 12px',
              gap: 0,
              borderBottom: `1px solid ${T.border}`,
              flexShrink: 0,
              height: 34,
            }}
          >
            {/* Tab buttons */}
            {TABS.map((tab) => {
              const Icon = tab.icon
              const isActive = activeTab === tab.key
              return (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 5,
                    padding: '0 14px',
                    height: '100%',
                    background: 'none',
                    border: 'none',
                    borderBottom: isActive ? `2px solid ${T.cyan}` : '2px solid transparent',
                    color: isActive ? T.text : T.dim,
                    fontFamily: F,
                    fontSize: FS.xxs,
                    fontWeight: isActive ? 700 : 500,
                    letterSpacing: '0.08em',
                    cursor: 'pointer',
                    transition: 'all 0.15s',
                  }}
                >
                  <Icon size={11} />
                  {tab.label}
                  {/* Badge for log count */}
                  {tab.key === 'logs' && logCount > 0 && (
                    <span
                      style={{
                        fontFamily: FCODE,
                        fontSize: 9,
                        color: T.dim,
                        padding: '0 4px',
                        background: T.surface3,
                        borderRadius: 8,
                      }}
                    >
                      {logCount > 999 ? '999+' : logCount}
                    </span>
                  )}
                </button>
              )
            })}

            <div style={{ flex: 1 }} />

            {/* Progress indicator */}
            {runStatus === 'running' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 10 }}>
                <div
                  style={{
                    width: 80,
                    height: 3,
                    background: T.surface3,
                    borderRadius: 999,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      width: `${pct}%`,
                      height: '100%',
                      background: T.cyan,
                      transition: 'width 0.3s ease',
                      borderRadius: 999,
                    }}
                  />
                </div>
                <span style={{ fontFamily: FCODE, fontSize: FS.xxs, color: T.cyan }}>
                  {pct}%
                </span>
              </div>
            )}

            {/* Status badge */}
            {monitorRunStatus !== 'idle' && monitorRunStatus !== 'running' && (
              <span
                style={{
                  fontFamily: F,
                  fontSize: 9,
                  padding: '1px 6px',
                  borderRadius: 3,
                  marginRight: 8,
                  background: monitorRunStatus === 'complete' ? `${T.green}18` :
                              monitorRunStatus === 'failed' ? `${T.red}18` : `${T.amber}18`,
                  color: monitorRunStatus === 'complete' ? T.green :
                         monitorRunStatus === 'failed' ? T.red : T.amber,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                }}
              >
                {monitorRunStatus}
              </span>
            )}

            <button
              onClick={() => {
                const runId = useRunStore.getState().activeRunId
                useUIStore.getState().navigateToMonitor(runId)
              }}
              style={{
                background: 'none',
                border: 'none',
                color: T.dim,
                cursor: 'pointer',
                padding: 2,
                display: 'flex',
                alignItems: 'center',
              }}
              title="Open in Monitor view"
            >
              <Maximize2 size={13} />
            </button>
            <button
              onClick={onClose}
              style={{
                background: 'none',
                border: 'none',
                color: T.dim,
                cursor: 'pointer',
                padding: 2,
                display: 'flex',
                alignItems: 'center',
              }}
              title="Minimize"
            >
              <ChevronDown size={13} />
            </button>
            <button
              onClick={onClose}
              style={{
                background: 'none',
                border: 'none',
                color: T.dim,
                cursor: 'pointer',
                padding: 2,
                display: 'flex',
                alignItems: 'center',
              }}
              title="Close"
            >
              <X size={13} />
            </button>
          </div>

          {/* Tab content */}
          <div style={{ flex: 1, overflow: 'hidden' }}>
            <Suspense
              fallback={
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  height: '100%',
                  fontFamily: F,
                  fontSize: FS.xs,
                  color: T.dim,
                }}>
                  Loading...
                </div>
              }
            >
              {activeTab === 'timeline' && <ExecutionTimeline />}
              {activeTab === 'logs' && <LogViewer />}
              {activeTab === 'outputs' && activeRunId && (
                <div style={{ height: '100%', overflow: 'auto' }}>
                  <ArtifactBrowser runId={activeRunId} />
                </div>
              )}
              {activeTab === 'outputs' && !activeRunId && (
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  height: '100%',
                  fontFamily: F,
                  fontSize: FS.xs,
                  color: T.dim,
                }}>
                  Run a pipeline to see output artifacts
                </div>
              )}
            </Suspense>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
