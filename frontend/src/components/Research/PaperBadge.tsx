import { F, FS } from '@/lib/design-tokens'

const PAPER_STATUS_COLORS: Record<string, string> = {
  planned: '#64748B',
  queued: '#8B5CF6',
  active: '#00BFA5',
  blocked: '#F59E0B',
  analyzing: '#3B82F6',
  writing: '#6366F1',
  complete: '#10B981',
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
