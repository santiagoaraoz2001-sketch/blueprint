import { T, F, FS, CATEGORY_COLORS } from '@/lib/design-tokens'
import { useMetricsStore } from '@/stores/metricsStore'
import {
  Database, Brain, BarChart3, MessageSquare, GitMerge, Blocks, CheckCircle, XCircle, Clock, Loader, StopCircle,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { motion } from 'framer-motion'

const CATEGORY_ICONS: Record<string, LucideIcon> = {
  data: Database,
  training: Brain,
  evaluation: BarChart3,
  inference: MessageSquare,
  merge: GitMerge,
  default: Blocks,
}

export default function PipelineStrip() {
  const executionOrder = useMetricsStore((s) => s.monitorExecutionOrder)
  const viewedBlockId = useMetricsStore((s) => s.viewedBlockId)
  const setViewedBlock = useMetricsStore((s) => s.setViewedBlock)

  if (executionOrder.length === 0) {
    return (
      <div style={{
        height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 16,
      }}>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, textAlign: 'center', lineHeight: 1.5 }}>
          Connected, waiting for first block...
        </span>
      </div>
    )
  }

  return (
    <div style={{ padding: '8px 0', height: '100%', overflow: 'auto' }}>
      <div style={{
        padding: '4px 12px 8px',
        borderBottom: `1px solid ${T.border}`,
        marginBottom: 4,
      }}>
        <span style={{
          fontFamily: F, fontSize: FS.xxs, fontWeight: 900,
          color: T.dim, letterSpacing: '0.1em',
        }}>
          PIPELINE
        </span>
      </div>

      {executionOrder.map((block) => {
        const CategoryIcon = CATEGORY_ICONS[block.category] || CATEGORY_ICONS.default
        const isViewed = viewedBlockId === block.id
        const categoryColor = CATEGORY_COLORS[block.category] || T.dim

        return (
          <motion.button
            key={block.id}
            onClick={() => setViewedBlock(block.id)}
            whileHover={{ x: 2 }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              width: '100%',
              padding: '8px 12px',
              background: isViewed ? `${T.cyan}08` : 'transparent',
              border: 'none',
              borderLeft: isViewed ? `2px solid ${T.cyan}` : '2px solid transparent',
              borderBottom: `1px solid ${T.border}`,
              cursor: 'pointer',
              transition: 'all 0.15s',
              position: 'relative',
            }}
          >
            {/* Category icon */}
            <div style={{
              width: 24, height: 24, borderRadius: 4,
              background: `${categoryColor}15`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}>
              <CategoryIcon size={12} color={categoryColor} />
            </div>

            {/* Name + status */}
            <div style={{ flex: 1, textAlign: 'left', minWidth: 0 }}>
              <div style={{
                fontFamily: F, fontSize: FS.xs, fontWeight: isViewed ? 700 : 500,
                color: isViewed ? T.text : T.sec,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                letterSpacing: '0.04em',
              }}>
                {block.name}
              </div>
              {block.status === 'running' && (
                <div style={{
                  width: '100%', height: 2, background: T.surface3,
                  marginTop: 3, borderRadius: 1, overflow: 'hidden',
                }}>
                  <div style={{
                    width: `${Math.round(block.progress * 100)}%`,
                    height: '100%', background: '#00BFA5',
                    transition: 'width 0.3s ease',
                  }} />
                </div>
              )}
            </div>

            {/* Status icon */}
            <div style={{ flexShrink: 0 }}>
              {block.status === 'running' ? (
                <Loader
                  size={12}
                  color="#00BFA5"
                  style={{ animation: 'spin 1.5s linear infinite' }}
                />
              ) : block.status === 'complete' ? (
                <CheckCircle size={12} color={T.green} />
              ) : block.status === 'failed' ? (
                <XCircle size={12} color={T.red} />
              ) : block.status === 'cancelled' ? (
                <StopCircle size={12} color={T.amber} />
              ) : (
                <Clock size={12} color={T.dim} />
              )}
            </div>

            {/* Running pulse animation */}
            {block.status === 'running' && (
              <style>{`
                @keyframes spin {
                  from { transform: rotate(0deg); }
                  to { transform: rotate(360deg); }
                }
              `}</style>
            )}
          </motion.button>
        )
      })}
    </div>
  )
}
