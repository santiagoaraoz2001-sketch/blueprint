import { T, F, FS } from '@/lib/design-tokens'
import { AlertTriangle } from 'lucide-react'

interface Props {
  open: boolean
  timestamp: string
  onRestore: () => void
  onDiscard: () => void
}

export default function AutosaveRecoveryDialog({ open, timestamp, onRestore, onDiscard }: Props) {
  if (!open) return null

  const formattedTime = (() => {
    try {
      const d = new Date(timestamp)
      return d.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return timestamp
    }
  })()

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 10002,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: T.shadowHeavy,
      }}
    >
      <div
        style={{
          width: 440,
          background: T.surface2,
          border: `1px solid ${T.borderHi}`,
          boxShadow: `0 16px 48px ${T.shadowHeavy}`,
          padding: 24,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <AlertTriangle size={20} color={T.amber} />
          <span style={{
            fontFamily: F,
            fontSize: FS.lg,
            fontWeight: 700,
            color: T.text,
          }}>
            Recover Unsaved Changes
          </span>
        </div>

        <p style={{
          fontFamily: F,
          fontSize: FS.sm,
          color: T.sec,
          lineHeight: 1.5,
          margin: '0 0 20px',
        }}>
          Blueprint found unsaved changes from <strong style={{ color: T.text }}>{formattedTime}</strong>.
          Would you like to restore them or start from the last saved state?
        </p>

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button
            onClick={onDiscard}
            style={{
              padding: '6px 16px',
              background: 'transparent',
              border: `1px solid ${T.border}`,
              color: T.sec,
              fontFamily: F,
              fontSize: FS.sm,
              cursor: 'pointer',
            }}
          >
            Discard
          </button>
          <button
            onClick={onRestore}
            style={{
              padding: '6px 16px',
              background: T.cyan,
              border: 'none',
              color: '#000',
              fontFamily: F,
              fontSize: FS.sm,
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            Restore
          </button>
        </div>
      </div>
    </div>
  )
}
