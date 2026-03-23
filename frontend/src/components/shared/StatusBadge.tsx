import { T, F, FS, STATUS_COLORS } from '@/lib/design-tokens'

interface StatusBadgeProps {
  status: string
  size?: 'sm' | 'md'
}

export default function StatusBadge({ status, size = 'sm' }: StatusBadgeProps) {
  const color = STATUS_COLORS[status] || T.dim

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: size === 'sm' ? '1px 6px' : '2px 8px',
        background: `${color}14`,
        border: `1px solid ${color}33`,
        fontFamily: F,
        fontSize: size === 'sm' ? FS.xxs : FS.xs,
        color,
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        fontWeight: 600,
        whiteSpace: 'nowrap',
      }}
    >
      <span
        style={{
          width: 4,
          height: 4,
          borderRadius: '50%',
          background: color,
          flexShrink: 0,
        }}
      />
      {status}
    </span>
  )
}
