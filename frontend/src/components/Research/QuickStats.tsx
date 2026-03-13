import { T, F, FS } from '@/lib/design-tokens'

interface QuickStatsProps {
  totalRuns: number
  completedRuns: number
  bestMetric?: { name: string; value: number }
  totalComputeHours?: number
}

export default function QuickStats({ totalRuns, completedRuns, bestMetric, totalComputeHours }: QuickStatsProps) {
  return (
    <div style={{
      display: 'flex', gap: 16, padding: '8px 12px',
      background: T.surface1, border: `1px solid ${T.border}`,
    }}>
      <div>
        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>TOTAL RUNS</div>
        <div style={{ fontFamily: F, fontSize: FS.md, color: T.text, fontWeight: 700 }}>{totalRuns}</div>
      </div>
      <div>
        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>COMPLETED</div>
        <div style={{ fontFamily: F, fontSize: FS.md, color: T.green, fontWeight: 700 }}>{completedRuns}</div>
      </div>
      {bestMetric && (
        <div>
          <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>BEST {bestMetric.name.toUpperCase()}</div>
          <div style={{ fontFamily: F, fontSize: FS.md, color: T.cyan, fontWeight: 700 }}>{bestMetric.value.toFixed(4)}</div>
        </div>
      )}
      {totalComputeHours != null && (
        <div>
          <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>COMPUTE</div>
          <div style={{ fontFamily: F, fontSize: FS.md, color: T.sec, fontWeight: 700 }}>{totalComputeHours.toFixed(1)}h</div>
        </div>
      )}
    </div>
  )
}
