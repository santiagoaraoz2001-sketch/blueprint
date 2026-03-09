import { useEffect, useRef } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle2, Circle, Loader, XCircle, X, ChevronDown } from 'lucide-react'

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

function formatElapsed(seconds?: number): string {
  if (seconds == null) return '--'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case 'done':
    case 'complete':
      return <CheckCircle2 size={12} color={T.green} />
    case 'running':
      return (
        <Loader
          size={12}
          color={T.cyan}
          style={{ animation: 'spin 1s linear infinite' }}
        />
      )
    case 'error':
    case 'failed':
      return <XCircle size={12} color={T.red} />
    default:
      return <Circle size={12} color={T.dim} />
  }
}

function estimateETA(progress: number, blocks: MonitorBlock[]): string {
  if (progress <= 0) return '--'
  if (progress >= 1) return '0s'
  const totalElapsed = blocks.reduce((sum, b) => sum + (b.elapsed || 0), 0)
  if (totalElapsed === 0) return '--'
  const estimated = totalElapsed / progress - totalElapsed
  return formatElapsed(Math.round(estimated))
}

export default function PipelineMonitor({
  visible,
  blocks,
  progress,
  logs,
  onClose,
}: PipelineMonitorProps) {
  const logContainerRef = useRef<HTMLDivElement>(null)

  // Auto-scroll logs to bottom
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logs])

  const displayLogs = logs.slice(-50)
  const pct = Math.round(progress * 100)

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
            height: 280,
            background: T.surface1,
            borderTop: `1px solid ${T.borderHi}`,
            display: 'flex',
            flexDirection: 'column',
            zIndex: 50,
          }}
        >
          {/* Header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              padding: '6px 12px',
              gap: 10,
              borderBottom: `1px solid ${T.border}`,
              flexShrink: 0,
            }}
          >
            <span
              style={{
                fontFamily: F,
                fontSize: FS.sm,
                fontWeight: 700,
                color: T.text,
                letterSpacing: '0.08em',
              }}
            >
              PIPELINE MONITOR
            </span>

            {/* Progress bar */}
            <div
              style={{
                flex: 1,
                height: 4,
                background: T.surface3,
                overflow: 'hidden',
                maxWidth: 200,
              }}
            >
              <div
                style={{
                  width: `${pct}%`,
                  height: '100%',
                  background: T.cyan,
                  transition: 'width 0.3s ease',
                }}
              />
            </div>

            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.cyan }}>
              {pct}%
            </span>

            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
              ETA {estimateETA(progress, blocks)}
            </span>

            <div style={{ flex: 1 }} />

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
              title="Close monitor"
            >
              <ChevronDown size={14} />
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
              <X size={14} />
            </button>
          </div>

          {/* Content */}
          <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
            {/* Block status list */}
            <div
              style={{
                width: 280,
                borderRight: `1px solid ${T.border}`,
                overflowY: 'auto',
                flexShrink: 0,
              }}
            >
              {blocks.map((block) => (
                <div
                  key={block.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '5px 10px',
                    borderBottom: `1px solid ${T.border}`,
                  }}
                >
                  <StatusIcon status={block.status} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontFamily: F,
                        fontSize: FS.xs,
                        color: T.text,
                        fontWeight: 600,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {block.name}
                    </div>
                    {block.log && (
                      <div
                        style={{
                          fontFamily: F,
                          fontSize: FS.xxs,
                          color: T.dim,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {block.log}
                      </div>
                    )}
                  </div>
                  <span
                    style={{
                      fontFamily: F,
                      fontSize: FS.xxs,
                      color: T.dim,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {formatElapsed(block.elapsed)}
                  </span>
                </div>
              ))}
              {blocks.length === 0 && (
                <div
                  style={{
                    padding: 16,
                    fontFamily: F,
                    fontSize: FS.xs,
                    color: T.dim,
                    textAlign: 'center',
                  }}
                >
                  No blocks in execution
                </div>
              )}
            </div>

            {/* Right: Log stream + output preview */}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <div
                ref={logContainerRef}
                style={{
                  flex: 1,
                  overflowY: 'auto',
                  padding: '6px 10px',
                  background: T.surface0,
                }}
              >
                {displayLogs.length === 0 ? (
                  <div
                    style={{
                      fontFamily: F,
                      fontSize: FS.xs,
                      color: T.dim,
                      padding: 10,
                      textAlign: 'center',
                    }}
                  >
                    Waiting for log output...
                  </div>
                ) : (
                  displayLogs.map((line, i) => (
                    <div
                      key={i}
                      style={{
                        fontFamily: F,
                        fontSize: FS.xxs,
                        color: T.sec,
                        lineHeight: 1.6,
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-all',
                      }}
                    >
                      <span style={{ color: T.dim, marginRight: 8 }}>
                        {String(i + 1).padStart(3, ' ')}
                      </span>
                      {line}
                    </div>
                  ))
                )}
              </div>

              {/* Output preview section */}
              {blocks.filter(b => b.status === 'complete' && b.output && Object.keys(b.output).length > 0).length > 0 && (
                <div style={{ borderTop: `1px solid ${T.border}`, flexShrink: 0, maxHeight: 100, overflowY: 'auto', padding: '6px 10px', background: T.surface1 }}>
                  <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.1em', marginBottom: 4 }}>BLOCK OUTPUTS</div>
                  {blocks.filter(b => b.output && Object.keys(b.output).length > 0).map(b => (
                    <div key={b.id} style={{ display: 'flex', gap: 8, marginBottom: 2, flexWrap: 'wrap' }}>
                      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.purple, fontWeight: 700 }}>{b.name}:</span>
                      {Object.entries(b.output!).map(([k, v]) => (
                        <span key={k} style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
                          <span style={{ color: T.cyan }}>{k}</span>={typeof v === 'object' ? JSON.stringify(v).slice(0, 40) + (JSON.stringify(v).length > 40 ? '…' : '') : String(v).slice(0, 40)}
                        </span>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
