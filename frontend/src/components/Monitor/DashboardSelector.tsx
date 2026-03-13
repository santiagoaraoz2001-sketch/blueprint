import { useState, useEffect, useRef } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore } from '@/stores/metricsStore'
import TrainingDashboard from './TrainingDashboard'
import EvaluationDashboard from './EvaluationDashboard'
import DefaultDashboard from './DefaultDashboard'
import { Loader } from 'lucide-react'

interface DashboardSelectorProps {
  runId: string
  viewedBlockId: string | null
}

function WaitingState() {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        gap: 8,
      }}
    >
      <Loader size={16} color={T.dim} style={{ animation: 'spin 1s linear infinite' }} />
      <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>
        Waiting for block to start...
      </span>
    </div>
  )
}

function selectDashboard(category: string, runId: string, blockId: string) {
  switch (category) {
    case 'training':
      return <TrainingDashboard runId={runId} blockId={blockId} />
    case 'evaluate':
    case 'metrics':
    case 'evaluation':
      return <EvaluationDashboard runId={runId} blockId={blockId} />
    default:
      return <DefaultDashboard runId={runId} blockId={blockId} />
  }
}

export default function DashboardSelector({ runId, viewedBlockId }: DashboardSelectorProps) {
  const viewedBlock = useMetricsStore((s) =>
    viewedBlockId ? s.runs[runId]?.blocks[viewedBlockId] : null
  )
  const activeBlock = useMetricsStore((s) => s.getActiveBlock(runId))
  const [opacity, setOpacity] = useState(1)
  const prevCategoryRef = useRef<string | null>(null)

  const block = viewedBlock || activeBlock

  // Fade transition when category changes
  useEffect(() => {
    const newCategory = block?.category || null
    if (prevCategoryRef.current !== null && prevCategoryRef.current !== newCategory) {
      setOpacity(0)
      const timer = setTimeout(() => setOpacity(1), 50)
      return () => clearTimeout(timer)
    }
    prevCategoryRef.current = newCategory
  }, [block?.category])

  if (!block) {
    return <WaitingState />
  }

  return (
    <div
      style={{
        height: '100%',
        opacity,
        transition: 'opacity 200ms ease-in-out',
      }}
    >
      {selectDashboard(block.category, runId, block.nodeId)}
    </div>
  )
}
