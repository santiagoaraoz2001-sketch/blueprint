import { useState } from 'react'
import { AlertTriangle, X } from 'lucide-react'
import { T, F, FS } from '@/lib/design-tokens'
import type { ErrorSeverity } from './ErrorCard'

export interface ErrorBannerProps {
  message: string
  severity?: ErrorSeverity
  action?: string
  onAction?: () => void
  onDismiss?: () => void
}

export default function ErrorBanner({
  message,
  severity = 'error',
  action,
  onAction,
  onDismiss,
}: ErrorBannerProps) {
  const [dismissed, setDismissed] = useState(false)

  if (dismissed) return null

  const color = severity === 'error' ? T.red : severity === 'warning' ? T.amber : T.blue

  return (
    <div
      role="alert"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '8px 14px',
        background: `${color}12`,
        borderBottom: `1px solid ${color}30`,
        fontFamily: F,
        fontSize: FS.xs,
        color: T.text,
        position: 'relative',
        zIndex: 50,
      }}
    >
      <AlertTriangle size={14} color={color} style={{ flexShrink: 0 }} />

      <span style={{ flex: 1 }}>{message}</span>

      {action && (
        <button
          onClick={onAction}
          style={{
            fontFamily: F,
            fontSize: FS.xs,
            fontWeight: 700,
            color: T.cyan,
            background: 'none',
            border: `1px solid ${T.cyan}40`,
            borderRadius: 4,
            padding: '3px 8px',
            cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          {action}
        </button>
      )}

      <button
        onClick={() => {
          setDismissed(true)
          onDismiss?.()
        }}
        aria-label="Dismiss"
        style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          padding: 2,
          display: 'flex',
          alignItems: 'center',
          color: T.dim,
        }}
      >
        <X size={14} />
      </button>
    </div>
  )
}
