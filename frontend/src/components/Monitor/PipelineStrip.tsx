import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore, type BlockState } from '@/stores/metricsStore'
import { CheckCircle2, Circle, Loader, XCircle } from 'lucide-react'

const EMPTY_ORDER: string[] = []

interface PipelineStripProps {
  runId: string
  viewedBlockId: string | null
  onSelectBlock: (blockId: string) => void
}

function BlockStatusIcon({ status }: { status: string }) {
  switch (status) {
    case 'complete':
      return <CheckCircle2 size={11} color="#22c55e" />
    case 'running':
      return (
        <Loader
          size={11}
          color="#00BFA5"
          style={{ animation: 'spin 1s linear infinite' }}
        />
      )
    case 'failed':
      return <XCircle size={11} color="#ff433d" />
    default:
      return <Circle size={11} color={T.dim} />
  }
}

function borderColor(status: string): string {
  switch (status) {
    case 'complete': return '#22c55e'
    case 'running': return '#00BFA5'
    case 'failed': return '#ff433d'
    default: return 'transparent'
  }
}

export default function PipelineStrip({ runId, viewedBlockId, onSelectBlock }: PipelineStripProps) {
  const blocks = useMetricsStore((s) => s.runs[runId]?.blocks)
  const executionOrder = useMetricsStore((s) => s.runs[runId]?.executionOrder ?? EMPTY_ORDER)

  if (!blocks) return null

  // Sort blocks by execution order
  const orderedBlocks: BlockState[] = executionOrder
    .map((id) => blocks[id])
    .filter(Boolean)

  // Include any blocks not in executionOrder
  const inOrder = new Set(executionOrder)
  Object.values(blocks).forEach((b) => {
    if (!inOrder.has(b.nodeId)) orderedBlocks.push(b)
  })

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        width: '100%',
        gap: 1,
      }}
    >
      <div
        style={{
          fontFamily: F,
          fontSize: FS.xxs,
          color: T.dim,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          padding: '8px 10px 4px',
        }}
      >
        PIPELINE
      </div>
      {orderedBlocks.map((block) => {
        const isActive = viewedBlockId === block.nodeId
        const isRunning = block.status === 'running'
        return (
          <button
            key={block.nodeId}
            onClick={() => onSelectBlock(block.nodeId)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '7px 10px',
              background: isActive ? `${T.cyan}10` : 'transparent',
              border: 'none',
              borderLeft: `3px solid ${borderColor(block.status)}`,
              cursor: 'pointer',
              textAlign: 'left',
              transition: 'background 0.15s',
              animation: isRunning ? 'monitor-pulse 2s ease-in-out infinite' : 'none',
            }}
            onMouseEnter={(e) => {
              if (!isActive) e.currentTarget.style.background = T.surface2
            }}
            onMouseLeave={(e) => {
              if (!isActive) e.currentTarget.style.background = 'transparent'
            }}
          >
            <BlockStatusIcon status={block.status} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontFamily: F,
                  fontSize: FS.xs,
                  color: block.status === 'queued' ? T.dim : T.text,
                  fontWeight: isActive ? 700 : 500,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {block.label}
              </div>
              {block.status === 'running' && block.progress > 0 && (
                <div
                  style={{
                    marginTop: 3,
                    height: 2,
                    background: T.surface3,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      width: `${Math.round(block.progress * 100)}%`,
                      height: '100%',
                      background: '#00BFA5',
                      transition: 'width 0.3s ease',
                    }}
                  />
                </div>
              )}
            </div>
            {block.status === 'complete' && (
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>✓</span>
            )}
            {block.status === 'failed' && (
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: '#ff433d' }}>✗</span>
            )}
          </button>
        )
      })}
      <style>{`
        @keyframes monitor-pulse {
          0%, 100% { border-left-color: #00BFA5; }
          50% { border-left-color: transparent; }
        }
      `}</style>
    </div>
  )
}
