import { T, F, FS } from '@/lib/design-tokens'
import type { DashboardStats } from '@/stores/metricsStore'

interface QuickStatsProps {
  stats: DashboardStats
}

export default function QuickStats({ stats }: QuickStatsProps) {
  const pct = stats.total_experiments > 0
    ? Math.round((stats.completed_experiments / stats.total_experiments) * 100)
    : 0

  return (
    <div
      style={{
        padding: '8px 14px',
        background: T.surface1,
        borderTop: `1px solid ${T.border}`,
        fontFamily: F,
        fontSize: FS.xs,
        color: T.dim,
        letterSpacing: '0.04em',
        display: 'flex',
        alignItems: 'center',
        gap: 4,
      }}
    >
      <span style={{ color: T.sec }}>{stats.total_papers}</span> papers
      <span style={{ color: T.dim, margin: '0 4px' }}>|</span>
      <span style={{ color: T.cyan }}>{stats.active_papers}</span> active
      <span style={{ color: T.dim, margin: '0 4px' }}>|</span>
      <span style={{ color: T.sec }}>{stats.completed_experiments}/{stats.total_experiments}</span> experiments ({pct}%)
      <span style={{ color: T.dim, margin: '0 4px' }}>|</span>
      <span style={{ color: T.sec }}>{(stats.compute_hours ?? 0).toFixed(0)}h</span> compute
    </div>
  )
}
