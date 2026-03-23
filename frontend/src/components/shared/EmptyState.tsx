import { T, F, FD, FS } from '@/lib/design-tokens'
import type { LucideIcon } from 'lucide-react'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description: string
  action?: {
    label: string
    onClick: () => void
  }
}

export default function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 48,
        gap: 12,
        minHeight: 300,
      }}
    >
      <Icon size={28} color={T.dim} strokeWidth={1.2} />
      <span
        style={{
          fontFamily: FD,
          fontSize: FS.xl,
          color: T.sec,
          fontWeight: 500,
          letterSpacing: '0.04em',
        }}
      >
        {title}
      </span>
      <span
        style={{
          fontFamily: F,
          fontSize: FS.sm,
          color: T.dim,
          textAlign: 'center',
          maxWidth: 300,
        }}
      >
        {description}
      </span>
      {action && (
        <button
          onClick={action.onClick}
          style={{
            marginTop: 8,
            padding: '6px 16px',
            background: `${T.cyan}14`,
            border: `1px solid ${T.cyan}33`,
            color: T.cyan,
            fontFamily: F,
            fontSize: FS.md,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            transition: 'all 0.15s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = `${T.cyan}22`
            e.currentTarget.style.borderColor = `${T.cyan}55`
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = `${T.cyan}14`
            e.currentTarget.style.borderColor = `${T.cyan}33`
          }}
        >
          {action.label}
        </button>
      )}
    </div>
  )
}
