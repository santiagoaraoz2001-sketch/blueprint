import { useState } from 'react'
import { AlertTriangle, AlertCircle, Info, ChevronDown, ChevronRight } from 'lucide-react'
import { T, F, FS, FCODE } from '@/lib/design-tokens'

export type ErrorSeverity = 'error' | 'warning' | 'info'

export interface ErrorCardProps {
  title: string
  message: string
  action?: string
  severity: ErrorSeverity
  details?: string
  onAction?: () => void
}

const SEVERITY_CONFIG: Record<ErrorSeverity, { icon: typeof AlertTriangle; color: string }> = {
  error:   { icon: AlertTriangle, color: '' },
  warning: { icon: AlertCircle,   color: '' },
  info:    { icon: Info,          color: '' },
}

function getSeverityColor(severity: ErrorSeverity): string {
  switch (severity) {
    case 'error':   return T.red
    case 'warning': return T.amber
    case 'info':    return T.blue
  }
}

export default function ErrorCard({ title, message, action, severity, details, onAction }: ErrorCardProps) {
  const [detailsOpen, setDetailsOpen] = useState(false)
  const config = SEVERITY_CONFIG[severity]
  const Icon = config.icon
  const color = getSeverityColor(severity)

  return (
    <div
      style={{
        background: T.surface2,
        border: `1px solid ${color}30`,
        borderLeft: `3px solid ${color}`,
        borderRadius: 6,
        padding: '10px 12px',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
        <Icon size={14} color={color} style={{ marginTop: 1, flexShrink: 0 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontFamily: F,
            fontSize: FS.sm,
            fontWeight: 700,
            color: T.text,
            lineHeight: 1.3,
          }}>
            {title}
          </div>
          <div style={{
            fontFamily: F,
            fontSize: FS.xs,
            color: T.sec,
            lineHeight: 1.4,
            marginTop: 2,
          }}>
            {message}
          </div>
        </div>
      </div>

      {/* Action link */}
      {action && (
        <div
          role="button"
          tabIndex={0}
          onClick={onAction}
          onKeyDown={(e) => e.key === 'Enter' && onAction?.()}
          style={{
            fontFamily: F,
            fontSize: FS.xs,
            color: T.cyan,
            cursor: onAction ? 'pointer' : 'default',
            paddingLeft: 22,
            lineHeight: 1.4,
          }}
        >
          {action}
        </div>
      )}

      {/* Expandable technical details */}
      {details && (
        <div style={{ paddingLeft: 22 }}>
          <div
            role="button"
            tabIndex={0}
            onClick={() => setDetailsOpen(!detailsOpen)}
            onKeyDown={(e) => e.key === 'Enter' && setDetailsOpen(!detailsOpen)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              cursor: 'pointer',
              fontFamily: F,
              fontSize: FS.xxs,
              color: T.dim,
              userSelect: 'none',
            }}
          >
            {detailsOpen ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
            Technical Details
          </div>
          {detailsOpen && (
            <pre style={{
              fontFamily: FCODE,
              fontSize: FS.xxs,
              color: T.dim,
              background: T.surface0,
              border: `1px solid ${T.border}`,
              borderRadius: 4,
              padding: '6px 8px',
              marginTop: 4,
              overflow: 'auto',
              maxHeight: 120,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-all',
              lineHeight: 1.5,
            }}>
              {details}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}
