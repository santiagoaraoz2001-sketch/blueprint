import { useMetricsStore } from '@/stores/metricsStore'
import { T, F, FS } from '@/lib/design-tokens'
import { Check, Loader2, AlertTriangle, Clock } from 'lucide-react'

interface PipelineStripProps {
  runId: string
  viewedBlockId: string | null
  onBlockClick: (blockId: string) => void
}

const statusIcon = (status: string) => {
  switch (status) {
    case 'complete': return <Check size={10} color={T.green} />
    case 'running': return <Loader2 size={10} color={T.cyan} style={{ animation: 'spin 1s linear infinite' }} />
    case 'failed': return <AlertTriangle size={10} color={T.red} />
    default: return <Clock size={10} color={T.dim} />
  }
}

export default function PipelineStrip({ runId, viewedBlockId, onBlockClick }: PipelineStripProps) {
  const run = useMetricsStore((s) => s.runs[runId])
  if (!run) return null

  const blocks = run.executionOrder.length > 0
    ? run.executionOrder.map((id) => run.blocks[id]).filter(Boolean)
    : Object.values(run.blocks)

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 2, padding: '6px 16px',
      borderBottom: `1px solid ${T.border}`, background: T.surface0, overflowX: 'auto',
    }}>
      {blocks.map((block, i) => {
        const isActive = block.nodeId === run.activeBlockId
        const isViewed = block.nodeId === viewedBlockId
        const statusColor =
          block.status === 'complete' ? T.green :
          block.status === 'running' ? T.cyan :
          block.status === 'failed' ? T.red : T.dim

        return (
          <div key={block.nodeId} style={{ display: 'flex', alignItems: 'center' }}>
            {i > 0 && (
              <div style={{ width: 16, height: 1, background: T.border, margin: '0 2px' }} />
            )}
            <button
              onClick={() => onBlockClick(block.nodeId)}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '4px 8px', cursor: 'pointer',
                background: isViewed ? `${statusColor}14` : isActive ? `${T.cyan}08` : 'transparent',
                border: `1px solid ${isViewed ? statusColor : isActive ? `${T.cyan}33` : T.border}`,
                transition: 'all 0.15s ease',
              }}
            >
              {statusIcon(block.status)}
              <span style={{
                fontFamily: F, fontSize: FS.xxs, color: isActive ? T.text : T.sec,
                fontWeight: isActive ? 700 : 400, whiteSpace: 'nowrap',
              }}>
                {block.label}
              </span>
              {block.status === 'running' && block.progress > 0 && (
                <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.cyan }}>
                  {Math.round(block.progress * 100)}%
                </span>
              )}
            </button>
          </div>
        )
      })}
    </div>
  )
}
