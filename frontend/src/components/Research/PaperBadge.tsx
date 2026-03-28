import { T, F, FS } from '@/lib/design-tokens'

const PAPER_STATUS_COLORS: Record<string, string> = {
  planned: T.dim,
  queued: T.purple,
  active: T.cyan,
  blocked: T.amber,
  analyzing: T.blue,
  writing: T.purple,
  complete: T.green,
}

interface PaperBadgeProps {
  paperNumber: string | null
  status: string
  size?: 'sm' | 'lg'
}

export default function PaperBadge({ paperNumber, status, size = 'sm' }: PaperBadgeProps) {
  const color = PAPER_STATUS_COLORS[status] || '#64748B'
  const isLarge = size === 'lg'

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: isLarge ? 6 : 4,
        padding: isLarge ? '4px 10px' : '2px 7px',
        background: `${color}33`,
        borderRadius: 4,
        fontFamily: F,
        fontSize: isLarge ? FS.md : FS.xs,
        fontWeight: 700,
        color,
        letterSpacing: '0.06em',
        whiteSpace: 'nowrap',
      }}
    >
      {paperNumber || '---'}
    </span>
  )
}

export { PAPER_STATUS_COLORS }
