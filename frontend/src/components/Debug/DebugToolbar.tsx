import { T, F, FS } from '@/lib/design-tokens'
import { useRunStore } from '@/stores/runStore'
import { Play, SkipForward, Square } from 'lucide-react'

export default function DebugToolbar() {
  const status = useRunStore((s) => s.status)
  const breakpoint = useRunStore((s) => s.breakpoint)
  const debugResume = useRunStore((s) => s.debugResume)
  const debugStep = useRunStore((s) => s.debugStep)
  const debugAbort = useRunStore((s) => s.debugAbort)

  if (status !== 'paused' || !breakpoint) return null

  return (
    <div
      style={{
        position: 'fixed',
        top: 12,
        left: '50%',
        transform: 'translateX(-50%)',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '8px 16px',
        background: T.surface2,
        border: `1px solid ${T.red}40`,
        borderRadius: 8,
        boxShadow: `0 8px 32px ${T.shadowHeavy}, 0 0 0 1px ${T.red}20`,
        zIndex: 1000,
        backdropFilter: 'blur(12px)',
      }}
    >
      {/* Paused indicator */}
      <div
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: T.red,
          boxShadow: `0 0 8px ${T.red}80`,
          animation: 'breakpoint-pulse 1.5s ease-in-out infinite',
        }}
      />

      {/* Status text */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1, marginRight: 4 }}>
        <span style={{
          fontFamily: F,
          fontSize: FS.xxs,
          color: T.red,
          fontWeight: 700,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
        }}>
          Paused at breakpoint
        </span>
        <span style={{
          fontFamily: F,
          fontSize: FS.xs,
          color: T.text,
          fontWeight: 600,
        }}>
          Node: {breakpoint.nodeId}
        </span>
        <span style={{
          fontFamily: F,
          fontSize: FS.xxs,
          color: T.dim,
        }}>
          {breakpoint.index + 1} / {breakpoint.total} blocks
        </span>
      </div>

      {/* Divider */}
      <div style={{ width: 1, height: 32, background: T.border, margin: '0 4px' }} />

      {/* Resume button */}
      <DebugButton
        icon={<Play size={12} />}
        label="Resume"
        color={T.cyan}
        onClick={debugResume}
        title="Continue to next breakpoint"
      />

      {/* Step button */}
      <DebugButton
        icon={<SkipForward size={12} />}
        label="Step"
        color={T.blue}
        onClick={debugStep}
        title="Execute one node then pause"
      />

      {/* Abort button */}
      <DebugButton
        icon={<Square size={12} />}
        label="Abort"
        color={T.red}
        onClick={debugAbort}
        title="Cancel the run"
      />
    </div>
  )
}

function DebugButton({ icon, label, color, onClick, title }: {
  icon: React.ReactNode
  label: string
  color: string
  onClick: () => void
  title: string
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 5,
        padding: '5px 10px',
        background: `${color}14`,
        border: `1px solid ${color}33`,
        borderRadius: 6,
        color,
        fontFamily: F,
        fontSize: FS.xxs,
        fontWeight: 600,
        letterSpacing: '0.04em',
        cursor: 'pointer',
        transition: 'all 0.15s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = `${color}28`
        e.currentTarget.style.borderColor = `${color}55`
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = `${color}14`
        e.currentTarget.style.borderColor = `${color}33`
      }}
    >
      {icon}
      {label}
    </button>
  )
}
