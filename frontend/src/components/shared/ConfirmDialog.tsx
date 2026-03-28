import { T, F, FS } from '@/lib/design-tokens'
import { AlertTriangle } from 'lucide-react'

interface ConfirmDialogProps {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  confirmColor?: string
  onConfirm: () => void
  onCancel: () => void
}

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  confirmColor = T.red,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.5)',
        backdropFilter: 'blur(4px)',
      }}
      onClick={onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        style={{
          width: 360,
          background: T.surface1,
          border: `1px solid ${T.borderHi}`,
          borderRadius: 8,
          padding: 20,
          boxShadow: `0 16px 48px rgba(0,0,0,0.5)`,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: 28, height: 28, borderRadius: 6,
            background: `${confirmColor}15`, border: `1px solid ${confirmColor}30`,
          }}>
            <AlertTriangle size={14} color={confirmColor} />
          </div>
          <span style={{
            fontFamily: F, fontSize: FS.md, color: T.text, fontWeight: 700,
          }}>
            {title}
          </span>
        </div>

        <div style={{
          fontFamily: F, fontSize: FS.sm, color: T.sec,
          lineHeight: 1.5, marginBottom: 20,
        }}>
          {message}
        </div>

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button
            onClick={onCancel}
            style={{
              padding: '6px 16px',
              background: 'none',
              border: `1px solid ${T.border}`,
              borderRadius: 4,
              color: T.dim,
              fontFamily: F,
              fontSize: FS.xs,
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            style={{
              padding: '6px 16px',
              background: `${confirmColor}20`,
              border: `1px solid ${confirmColor}40`,
              borderRadius: 4,
              color: confirmColor,
              fontFamily: F,
              fontSize: FS.xs,
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
