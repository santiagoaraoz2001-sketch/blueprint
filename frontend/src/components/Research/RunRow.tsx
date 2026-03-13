import { useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import StatusBadge from '@/components/shared/StatusBadge'
import ProgressBar from '@/components/shared/ProgressBar'
import { ChevronDown, ChevronRight } from 'lucide-react'

export interface RunRowData {
  id: string
  name: string
  status: string // 'running' | 'complete' | 'failed' | 'cancelled' | 'planned'
  progress?: number
  eta?: string
  metrics?: Record<string, number>
  errorMessage?: string
  createdAt?: string
}

interface RunRowProps {
  run: RunRowData
  onClick?: () => void
}

export default function RunRow({ run, onClick }: RunRowProps) {
  const [expanded, setExpanded] = useState(false)
  const isFailed = run.status === 'failed'
  const isRunning = run.status === 'running'
  const isPlanned = run.status === 'planned'

  return (
    <div
      style={{
        borderBottom: `1px solid ${T.surface4}`,
        background: isRunning ? `${T.cyan}04` : 'transparent',
      }}
    >
      <div
        onClick={() => (isFailed && run.errorMessage) ? setExpanded(!expanded) : onClick?.()}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '6px 10px',
          cursor: isPlanned ? 'default' : 'pointer',
        }}
      >
        {isFailed && run.errorMessage && (
          expanded ? <ChevronDown size={10} color={T.dim} /> : <ChevronRight size={10} color={T.dim} />
        )}
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.text, flex: 1 }}>
          {run.name}
        </span>

        {isRunning && run.progress != null && (
          <div style={{ width: 60 }}>
            <ProgressBar value={run.progress * 100} height={3} color={T.cyan} />
          </div>
        )}

        {isRunning && run.eta && (
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
            ETA {run.eta}
          </span>
        )}

        {run.status === 'complete' && run.metrics && (
          <div style={{ display: 'flex', gap: 8 }}>
            {Object.entries(run.metrics).slice(0, 3).map(([key, val]) => (
              <span key={key} style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
                {key}=<span style={{ color: T.cyan }}>{typeof val === 'number' ? val.toFixed(2) : val}</span>
              </span>
            ))}
          </div>
        )}

        <StatusBadge status={run.status} size="sm" />
      </div>

      {/* Expanded error traceback */}
      {expanded && isFailed && run.errorMessage && (
        <div style={{
          padding: '8px 10px 8px 28px',
          background: `${T.red}06`,
          borderTop: `1px solid ${T.red}20`,
        }}>
          <pre style={{
            fontFamily: F, fontSize: FS.xxs, color: T.red,
            whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: 0,
            maxHeight: 200, overflow: 'auto',
          }}>
            {run.errorMessage}
          </pre>
        </div>
      )}
    </div>
  )
}
