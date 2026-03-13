import { useState, useEffect, useRef } from 'react'
import { useMetricsStore } from '@/stores/metricsStore'
import TrainingDashboard from './TrainingDashboard'
import EvaluationDashboard from './EvaluationDashboard'
import InferenceDashboard from './InferenceDashboard'
import MergeDashboard from './MergeDashboard'
import DataDashboard from './DataDashboard'
import DefaultDashboard from './DefaultDashboard'
import { T, F, FS } from '@/lib/design-tokens'

const DASHBOARD_MAP: Record<string, React.ComponentType<{ blockId: string }>> = {
  training: TrainingDashboard,
  evaluation: EvaluationDashboard,
  inference: InferenceDashboard,
  merge: MergeDashboard,
  data: DataDashboard,
}

export default function DashboardSelector() {
  const viewedBlockId = useMetricsStore((s) => s.viewedBlockId)
  const executionOrder = useMetricsStore((s) => s.monitorExecutionOrder)
  const [opacity, setOpacity] = useState(1)
  const [renderedBlockId, setRenderedBlockId] = useState(viewedBlockId)
  const timerRef = useRef<ReturnType<typeof setTimeout>>()

  // Smooth fade transition on block change
  useEffect(() => {
    if (viewedBlockId !== renderedBlockId) {
      setOpacity(0)
      timerRef.current = setTimeout(() => {
        setRenderedBlockId(viewedBlockId)
        setOpacity(1)
      }, 200)
      return () => {
        if (timerRef.current) clearTimeout(timerRef.current)
      }
    }
  }, [viewedBlockId, renderedBlockId])

  if (!renderedBlockId) {
    return (
      <div style={{
        height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>
          Select a block from the pipeline strip
        </span>
      </div>
    )
  }

  const block = executionOrder.find(b => b.id === renderedBlockId)
  const category = block?.category || 'default'
  const Dashboard = DASHBOARD_MAP[category] || DefaultDashboard

  return (
    <div style={{
      height: '100%',
      opacity,
      transition: 'opacity 200ms ease',
    }}>
      <Dashboard blockId={renderedBlockId} />
    </div>
  )
}
