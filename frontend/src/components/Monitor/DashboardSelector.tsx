import { useMetricsStore } from '@/stores/metricsStore'
import { T, F, FS } from '@/lib/design-tokens'
import { Loader2 } from 'lucide-react'
import TrainingDashboard from './TrainingDashboard'
import EvaluationDashboard from './EvaluationDashboard'
import InferenceDashboard from './InferenceDashboard'
import MergeDashboard from './MergeDashboard'
import DataDashboard from './DataDashboard'
import DefaultDashboard from './DefaultDashboard'

interface DashboardSelectorProps {
  runId: string
  viewedBlockId: string | null
}

function WaitingForStart() {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', height: 300, gap: 12,
    }}>
      <Loader2 size={24} color={T.cyan} style={{ animation: 'spin 1s linear infinite' }} />
      <span style={{ fontFamily: F, fontSize: FS.sm, color: T.dim }}>
        Waiting for pipeline to start...
      </span>
    </div>
  )
}

export default function DashboardSelector({ runId, viewedBlockId }: DashboardSelectorProps) {
  const activeBlock = viewedBlockId
    ? useMetricsStore((s) => s.runs[runId]?.blocks[viewedBlockId])
    : useMetricsStore((s) => {
        const run = s.runs[runId]
        if (!run || !run.activeBlockId) return null
        return run.blocks[run.activeBlockId]
      })

  if (!activeBlock) return <WaitingForStart />

  const props = { runId, blockId: activeBlock.nodeId }

  switch (activeBlock.category) {
    case 'training': return <TrainingDashboard {...props} />
    case 'evaluation': return <EvaluationDashboard {...props} />
    case 'inference': return <InferenceDashboard {...props} />
    case 'merge': return <MergeDashboard {...props} />
    case 'data': return <DataDashboard {...props} />
    default: return <DefaultDashboard {...props} />
  }
}
