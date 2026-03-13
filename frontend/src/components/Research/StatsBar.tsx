import { T, F, FD, FS } from '@/lib/design-tokens'
import type { DashboardStats } from '@/stores/metricsStore'

interface StatsBarProps {
  stats: DashboardStats
}

interface StatCardProps {
  label: string
  value: number | string
  accent?: string
  pulse?: boolean
}

function StatCard({ label, value, accent = T.sec, pulse = false }: StatCardProps) {
  return (
    <div
      style={{
        flex: 1,
        padding: '10px 14px',
        background: T.surface1,
        border: `1px solid ${T.border}`,
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
      }}
    >
      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
        {label}
      </span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {pulse && (
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: accent,
              animation: 'pulse-dot 1.5s ease-in-out infinite',
              flexShrink: 0,
            }}
          />
        )}
        <span style={{ fontFamily: FD, fontSize: FS.h2, fontWeight: 600, color: accent }}>
          {value}
        </span>
        {pulse && (
          <style>{`
            @keyframes pulse-dot {
              0%, 100% { opacity: 1; transform: scale(1); }
              50% { opacity: 0.4; transform: scale(0.8); }
            }
          `}</style>
        )}
      </div>
    </div>
  )
}

export default function StatsBar({ stats }: StatsBarProps) {
  return (
    <div style={{ display: 'flex', gap: 8 }}>
      <StatCard
        label="Running Now"
        value={stats.running_now}
        accent={stats.running_now > 0 ? T.cyan : T.dim}
        pulse={stats.running_now > 0}
      />
      <StatCard label="Completed Today" value={stats.completed_today} accent={T.green} />
      <StatCard label="Blocked" value={stats.blocked} accent={T.amber} />
      <StatCard label="Compute Hours" value={(stats.compute_hours ?? 0).toFixed(1)} accent={T.sec} />
    </div>
  )
}
