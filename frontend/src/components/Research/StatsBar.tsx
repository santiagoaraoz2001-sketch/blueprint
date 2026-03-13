import { T } from '@/lib/design-tokens'
import MetricDisplay from '@/components/shared/MetricDisplay'

interface StatsBarProps {
  runningCount: number
  completedTodayCount: number
  blockedCount: number
  computeHours: number
  onRunningClick?: () => void
  onCompletedClick?: () => void
  onBlockedClick?: () => void
}

export default function StatsBar({
  runningCount,
  completedTodayCount,
  blockedCount,
  computeHours,
  onRunningClick,
  onCompletedClick,
  onBlockedClick,
}: StatsBarProps) {
  const cards = [
    { label: 'RUNNING NOW', value: runningCount, accent: T.cyan, onClick: onRunningClick },
    { label: 'COMPLETED TODAY', value: completedTodayCount, accent: T.green, onClick: onCompletedClick },
    { label: 'BLOCKED', value: blockedCount, accent: T.amber, onClick: onBlockedClick },
    { label: 'COMPUTE HOURS', value: computeHours.toFixed(1), accent: T.sec, onClick: undefined },
  ]

  return (
    <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
      {cards.map((card) => (
        <div
          key={card.label}
          onClick={card.onClick}
          className="hover-glow"
          style={{
            flex: 1,
            padding: '10px 14px',
            background: T.surface1,
            border: `1px solid ${T.borderHi}`,
            cursor: card.onClick ? 'pointer' : 'default',
            transition: 'border-color 0.15s',
          }}
        >
          <MetricDisplay
            label={card.label}
            value={typeof card.value === 'string' ? card.value : card.value}
            accent={card.accent}
          />
        </div>
      ))}
    </div>
  )
}
