import { T, F, FS } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { useMetricsStore } from '@/stores/metricsStore'
import { runMetricsToTable } from '@/services/metricsBridge'
import ProgressBar from '@/components/shared/ProgressBar'
import toast from 'react-hot-toast'
import {
  CheckCircle2,
  XCircle,
  Clock,
  Loader,
  Copy,
  ExternalLink,
  TableProperties,
} from 'lucide-react'

interface Run {
  id: string
  name: string
  status: string
  progress?: number
  loss?: number | null
  accuracy?: number | null
  elapsed?: number
  eta?: number | null
}

interface RunRowProps {
  run: Run
  onClone?: (runId: string) => void
  onCompareToggle?: (runId: string) => void
  compareSelected?: boolean
}

const STATUS_ICONS: Record<string, { icon: typeof CheckCircle2; color: string }> = {
  complete: { icon: CheckCircle2, color: T.green },
  failed: { icon: XCircle, color: T.red },
  running: { icon: Loader, color: T.cyan },
  pending: { icon: Clock, color: T.dim },
}

function formatDuration(seconds: number | undefined): string {
  if (seconds == null) return ''
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  return `${(seconds / 3600).toFixed(1)}h`
}

export default function RunRow({ run, onClone, onCompareToggle, compareSelected }: RunRowProps) {
  const setView = useUIStore((s) => s.setView)
  const cloneRun = useMetricsStore((s) => s.cloneRun)
  const statusDef = STATUS_ICONS[run.status] || STATUS_ICONS.pending
  const Icon = statusDef.icon

  const handleClone = async () => {
    if (onClone) {
      onClone(run.id)
    } else {
      await cloneRun(run.id)
      setView('editor')
    }
  }

  const btnStyle: React.CSSProperties = {
    padding: '2px 6px',
    background: `${T.cyan}14`,
    border: `1px solid ${T.cyan}33`,
    color: T.cyan,
    fontFamily: F,
    fontSize: FS.xxs,
    letterSpacing: '0.06em',
    textTransform: 'uppercase',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    transition: 'all 0.15s',
  }

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 0',
        borderBottom: `1px solid ${T.border}`,
      }}
    >
      {onCompareToggle && (
        <input
          type="checkbox"
          checked={compareSelected}
          onChange={() => onCompareToggle(run.id)}
          style={{ accentColor: T.cyan, cursor: 'pointer' }}
        />
      )}
      <Icon
        size={12}
        color={statusDef.color}
        style={run.status === 'running' ? { animation: 'spin 1.5s linear infinite' } : undefined}
      />
      <span style={{ fontFamily: F, fontSize: FS.sm, color: T.text, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {run.name}
      </span>

      {run.loss != null && (
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
          {run.loss.toFixed(3)}
        </span>
      )}
      {run.accuracy != null && (
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
          {(run.accuracy * 100).toFixed(1)}%
        </span>
      )}

      {run.status === 'running' && run.progress != null && (
        <div style={{ width: 60 }}>
          <ProgressBar value={run.progress * 100} color={T.cyan} height={2} />
        </div>
      )}

      {run.elapsed != null && (
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, minWidth: 30, textAlign: 'right' }}>
          {formatDuration(run.elapsed)}
        </span>
      )}

      <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
        {run.status === 'complete' && (
          <button
            onClick={async () => {
              try {
                await runMetricsToTable(run.id, run.name)
                setView('data')
              } catch (e: any) {
                toast.error(e.message || 'No metrics available')
              }
            }}
            title="Analyze in Data View"
            style={btnStyle}
            onMouseEnter={(e) => { e.currentTarget.style.background = `${T.cyan}22` }}
            onMouseLeave={(e) => { e.currentTarget.style.background = `${T.cyan}14` }}
          >
            <TableProperties size={9} />
          </button>
        )}
        <button
          onClick={handleClone}
          title="Clone"
          style={btnStyle}
          onMouseEnter={(e) => { e.currentTarget.style.background = `${T.cyan}22` }}
          onMouseLeave={(e) => { e.currentTarget.style.background = `${T.cyan}14` }}
        >
          <Copy size={9} />
        </button>
        <button
          onClick={() => setView('results')}
          title="Results"
          style={btnStyle}
          onMouseEnter={(e) => { e.currentTarget.style.background = `${T.cyan}22` }}
          onMouseLeave={(e) => { e.currentTarget.style.background = `${T.cyan}14` }}
        >
          <ExternalLink size={9} />
        </button>
      </div>

      {run.status === 'running' && (
        <style>{`
          @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
          }
        `}</style>
      )}
    </div>
  )
}
