import { AlertTriangle } from 'lucide-react'
import { T, F, FS } from '@/lib/design-tokens'

export interface NodeErrorOverlayProps {
  message?: string
}

export default function NodeErrorOverlay({ message }: NodeErrorOverlayProps) {
  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        background: 'rgba(239, 83, 80, 0.12)',
        borderRadius: 8,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 4,
        pointerEvents: 'none',
        zIndex: 30,
      }}
    >
      <AlertTriangle size={20} color={T.red} />
      {message && (
        <div style={{
          fontFamily: F,
          fontSize: FS.xxs,
          color: T.red,
          fontWeight: 600,
          textAlign: 'center',
          padding: '0 8px',
          maxWidth: '90%',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {message}
        </div>
      )}
    </div>
  )
}
