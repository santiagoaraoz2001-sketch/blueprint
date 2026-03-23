import { T, F, FS } from '@/lib/design-tokens'
import { TrendingUp, TrendingDown } from 'lucide-react'

interface MetricDisplayProps {
  label: string
  value: string | number
  delta?: number
  accent?: string
}

export default function MetricDisplay({ label, value, delta, accent = T.cyan }: MetricDisplayProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span
        style={{
          fontFamily: F,
          fontSize: FS.xxs,
          color: T.dim,
          letterSpacing: '0.14em',
          textTransform: 'uppercase',
          fontWeight: 900,
        }}
      >
        {label}
      </span>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span
          style={{
            fontFamily: F,
            fontSize: FS.h3,
            color: accent,
            fontWeight: 600,
          }}
        >
          {value}
        </span>
        {delta !== undefined && delta !== 0 && (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 2,
              fontFamily: F,
              fontSize: FS.xxs,
              color: delta > 0 ? T.green : T.red,
            }}
          >
            {delta > 0 ? <TrendingUp size={8} /> : <TrendingDown size={8} />}
            {delta > 0 ? '+' : ''}{delta.toFixed(1)}%
          </span>
        )}
      </div>
    </div>
  )
}
