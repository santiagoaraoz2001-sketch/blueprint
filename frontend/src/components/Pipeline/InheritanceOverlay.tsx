import { T, F, FS } from '@/lib/design-tokens'
import { usePipelineStore } from '@/stores/pipelineStore'
import { X, GitBranch } from 'lucide-react'
import { useEffect } from 'react'

/** Colors for inheritance overlay roles (kept in sync with BlockNode badges) */
export const OVERLAY_COLORS = {
  origin: '#22c55e',     // green — where the value is set
  inheriting: '#3B82F6', // blue — receives value from upstream
  overriding: '#F97316', // orange — locally overrides the upstream value
} as const

/**
 * Floating banner shown when the inheritance overlay is active.
 * Displays which config key is being visualized and provides a close button.
 * Handles Escape-to-dismiss in capture phase so it fires even from input fields.
 */
export default function InheritanceOverlay() {
  const overlay = usePipelineStore((s) => s.inheritanceOverlay)
  const deactivate = usePipelineStore((s) => s.deactivateInheritanceOverlay)

  // Derived selector — returns a primitive string so this component only re-renders
  // when the resolved label actually changes (not on every node position change)
  const originLabel = usePipelineStore((s) => {
    if (!s.inheritanceOverlay) return ''
    const node = s.nodes.find(n => n.id === s.inheritanceOverlay!.originNode)
    return node?.data?.label || s.inheritanceOverlay!.originNode
  })

  // Escape key to dismiss — capture phase ensures it works even from input fields
  useEffect(() => {
    if (!overlay) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        deactivate()
      }
    }
    window.addEventListener('keydown', handleKeyDown, true)
    return () => window.removeEventListener('keydown', handleKeyDown, true)
  }, [overlay, deactivate])

  if (!overlay) return null

  const roles = Object.values(overlay.nodeRoles)
  const inheritingCount = roles.filter(r => r === 'inheriting').length
  const overridingCount = roles.filter(r => r === 'overriding').length
  const totalNodes = inheritingCount + overridingCount

  return (
    <div
      style={{
        position: 'absolute',
        top: 12,
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 50,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '8px 16px',
        background: T.surface,
        backdropFilter: 'blur(12px)',
        border: `1px solid ${OVERLAY_COLORS.inheriting}40`,
        boxShadow: `0 4px 24px ${T.shadow}, 0 0 0 1px ${OVERLAY_COLORS.inheriting}20`,
        borderRadius: 0,
        animation: 'fade-in-scale 0.2s ease both',
        whiteSpace: 'nowrap',
      }}
    >
      <GitBranch size={14} color={OVERLAY_COLORS.inheriting} />

      <span style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 700, letterSpacing: '0.04em' }}>
        Inheritance: <span style={{ color: OVERLAY_COLORS.inheriting }}>{overlay.key}</span>
      </span>

      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
        from {originLabel}
      </span>

      <div style={{ width: 1, height: 14, background: T.border }} />

      {/* Legend */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <LegendDot color={OVERLAY_COLORS.origin} label="Origin" />
        <LegendDot color={OVERLAY_COLORS.inheriting} label={`Inherited (${inheritingCount})`} />
        <LegendDot color={OVERLAY_COLORS.overriding} label={`Overridden (${overridingCount})`} />
      </div>

      {totalNodes === 0 && (
        <>
          <div style={{ width: 1, height: 14, background: T.border }} />
          <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>
            No downstream propagation
          </span>
        </>
      )}

      <button
        onClick={deactivate}
        title="Close (Esc)"
        style={{
          background: 'none',
          border: 'none',
          color: T.dim,
          cursor: 'pointer',
          display: 'flex',
          padding: 4,
          marginLeft: 4,
        }}
        onMouseEnter={(e) => { e.currentTarget.style.color = T.text }}
        onMouseLeave={(e) => { e.currentTarget.style.color = T.dim }}
      >
        <X size={12} />
      </button>
    </div>
  )
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      <div style={{
        width: 7,
        height: 7,
        borderRadius: '50%',
        background: color,
        boxShadow: `0 0 6px ${color}80`,
      }} />
      <span style={{ fontFamily: F, fontSize: FS.xs, color: T.sec }}>
        {label}
      </span>
    </div>
  )
}
