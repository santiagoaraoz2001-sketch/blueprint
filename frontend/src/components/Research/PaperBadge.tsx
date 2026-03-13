import { T, F, FS } from '@/lib/design-tokens'

interface PaperBadgeProps {
  status: string
  size?: 'sm' | 'md'
}

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  active: { color: '#4af6c3', label: 'Active' },
  complete: { color: '#22c55e', label: 'Complete' },
  blocked: { color: '#F59E0B', label: 'Blocked' },
  planning: { color: '#8B5CF6', label: 'Planning' },
  paused: { color: '#EAB308', label: 'Paused' },
  cancelled: { color: '#F59E0B', label: 'Cancelled' },
  failed: { color: '#ff433d', label: 'Failed' },
}

export default function PaperBadge({ status, size = 'sm' }: PaperBadgeProps) {
  const info = STATUS_MAP[status] || { color: T.dim, label: status }

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: size === 'sm' ? '1px 6px' : '2px 8px',
        background: `${info.color}14`,
        border: `1px solid ${info.color}33`,
        fontFamily: F,
        fontSize: size === 'sm' ? FS.xxs : FS.xs,
        color: info.color,
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        fontWeight: 600,
        whiteSpace: 'nowrap',
      }}
    >
      <span style={{ width: 4, height: 4, borderRadius: '50%', background: info.color, flexShrink: 0 }} />
      {info.label}
    </span>
  )
}
