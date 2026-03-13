import { T, F, FS } from '@/lib/design-tokens'
import { Circle, FileText, ExternalLink } from 'lucide-react'

interface Props {
  runName: string | null
  paperId: string | null
  status: { label: string; color: string; pulse: boolean }
  elapsed: string
  phase: string
}

export default function PopoutBar({ runName, paperId, status, elapsed, phase }: Props) {
  const handleOpenInMain = () => {
    if (window.opener) {
      try {
        window.opener.focus()
      } catch {
        // Cross-origin, ignore
      }
    }
  }

  const handlePaperClick = () => {
    if (window.opener && paperId) {
      try {
        window.opener.postMessage({ type: 'navigate', view: 'paper', paperId }, '*')
        window.opener.focus()
      } catch {
        // Cross-origin, ignore
      }
    }
  }

  return (
    <div style={{
      height: 24,
      display: 'flex',
      alignItems: 'center',
      padding: '0 10px',
      background: T.surface1,
      borderBottom: `1px solid ${T.border}`,
      gap: 8,
      flexShrink: 0,
    }}>
      {/* Left: Paper badge + phase + run name */}
      {paperId && (
        <button
          onClick={handlePaperClick}
          style={{
            display: 'flex', alignItems: 'center', gap: 3,
            background: `${T.cyan}10`, border: `1px solid ${T.cyan}30`,
            padding: '0px 5px', cursor: 'pointer',
            fontFamily: F, fontSize: FS.xxs, color: T.cyan,
          }}
        >
          <FileText size={8} />
        </button>
      )}

      <span style={{
        fontFamily: F, fontSize: FS.xxs, color: T.sec,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {phase}
      </span>

      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>|</span>

      <span style={{
        fontFamily: F, fontSize: FS.xxs, fontWeight: 700, color: T.text,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {runName || 'Run'}
      </span>

      <div style={{ flex: 1 }} />

      {/* Center: Status + elapsed */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <Circle
          size={5}
          fill={status.color}
          color={status.color}
          style={status.pulse ? { animation: 'pulse-glow 1.5s ease-in-out infinite' } : undefined}
        />
        <span style={{
          fontFamily: F, fontSize: FS.xxs, fontWeight: 700,
          color: status.color, letterSpacing: '0.08em',
        }}>
          {status.label}
        </span>
      </div>

      <span style={{
        fontFamily: F, fontSize: FS.xxs, color: T.dim,
        fontVariantNumeric: 'tabular-nums',
      }}>
        {elapsed}
      </span>

      {/* Right: Open in Main */}
      <button
        onClick={handleOpenInMain}
        style={{
          display: 'flex', alignItems: 'center', gap: 3,
          padding: '1px 6px',
          background: T.surface2, border: `1px solid ${T.border}`,
          color: T.sec, fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
        }}
      >
        <ExternalLink size={8} /> Open in Main
      </button>

      {status.pulse && (
        <style>{`
          @keyframes pulse-glow {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
          }
        `}</style>
      )}
    </div>
  )
}
