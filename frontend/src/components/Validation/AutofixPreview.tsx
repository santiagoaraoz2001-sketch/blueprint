/**
 * AutofixPreview — modal that displays proposed autofix patches with
 * before/after previews and selective application.
 *
 * - Lists each proposed fix with a checkbox (pre-checked for high confidence)
 * - Shows before/after values for each patch
 * - "Apply Selected" applies checked fixes, "Apply All" applies everything
 * - After applying, triggers re-validation to show updated status
 */

import { useState, useCallback } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import {
  X,
  Wrench,
  CheckCircle2,
  AlertTriangle,
  ChevronRight,
  Loader2,
} from 'lucide-react'

export interface AutofixPatch {
  patch_id: string
  node_id: string
  field: string
  action: 'set' | 'rename' | 'delete' | 'add_edge' | 'insert_converter'
  old_value: unknown
  new_value: unknown
  reason: string
  confidence: 'high' | 'medium'
  edge_id?: string | null
  source_id?: string | null
  target_id?: string | null
}

interface AutofixPreviewProps {
  patches: AutofixPatch[]
  onApply: (patchIds: string[]) => Promise<void>
  onClose: () => void
  isApplying: boolean
}

export default function AutofixPreview({
  patches,
  onApply,
  onClose,
  isApplying,
}: AutofixPreviewProps) {
  const [selected, setSelected] = useState<Set<string>>(() => {
    // Pre-check high confidence patches
    const initial = new Set<string>()
    for (const p of patches) {
      if (p.confidence === 'high') initial.add(p.patch_id)
    }
    return initial
  })

  const toggle = useCallback((patchId: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(patchId)) next.delete(patchId)
      else next.add(patchId)
      return next
    })
  }, [])

  const selectAll = useCallback(() => {
    setSelected(new Set(patches.map((p) => p.patch_id)))
  }, [patches])

  const handleApplySelected = useCallback(() => {
    onApply(Array.from(selected))
  }, [selected, onApply])

  const handleApplyAll = useCallback(() => {
    onApply(patches.map((p) => p.patch_id))
  }, [patches, onApply])

  const selectedCount = selected.size

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.6)',
        backdropFilter: 'blur(4px)',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !isApplying) onClose()
      }}
    >
      <div
        style={{
          background: T.surface2,
          border: `1px solid ${T.border}`,
          borderRadius: 12,
          width: 560,
          maxHeight: '80vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: `0 24px 48px ${T.shadowHeavy}`,
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '12px 16px',
            borderBottom: `1px solid ${T.border}`,
          }}
        >
          <Wrench size={14} color={T.cyan} />
          <span
            style={{
              fontFamily: F,
              fontSize: FS.sm,
              fontWeight: 700,
              color: T.text,
              flex: 1,
            }}
          >
            Autofix Preview
          </span>
          <span
            style={{
              fontFamily: F,
              fontSize: FS.xxs,
              color: T.dim,
            }}
          >
            {patches.length} fix{patches.length !== 1 ? 'es' : ''} proposed
          </span>
          <button
            onClick={onClose}
            disabled={isApplying}
            style={{
              background: 'none',
              border: 'none',
              color: T.dim,
              cursor: isApplying ? 'not-allowed' : 'pointer',
              padding: 2,
              display: 'flex',
            }}
          >
            <X size={14} />
          </button>
        </div>

        {/* Patch list */}
        <div style={{ overflowY: 'auto', padding: '8px 12px', flex: 1 }}>
          {patches.map((patch) => {
            const isChecked = selected.has(patch.patch_id)
            const isHigh = patch.confidence === 'high'

            return (
              <div
                key={patch.patch_id}
                style={{
                  display: 'flex',
                  gap: 8,
                  padding: '8px 6px',
                  borderRadius: 6,
                  marginBottom: 4,
                  background: isChecked ? `${T.cyan}08` : 'transparent',
                  border: `1px solid ${isChecked ? `${T.cyan}20` : 'transparent'}`,
                  transition: 'all 0.1s',
                }}
              >
                {/* Checkbox */}
                <div
                  onClick={() => !isApplying && toggle(patch.patch_id)}
                  style={{
                    width: 16,
                    height: 16,
                    borderRadius: 3,
                    border: `1.5px solid ${isChecked ? T.cyan : T.dim}`,
                    background: isChecked ? `${T.cyan}30` : 'transparent',
                    cursor: isApplying ? 'not-allowed' : 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                    marginTop: 1,
                  }}
                >
                  {isChecked && (
                    <CheckCircle2 size={10} color={T.cyan} />
                  )}
                </div>

                {/* Content */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  {/* Reason / description */}
                  <div
                    style={{
                      fontFamily: F,
                      fontSize: FS.xxs,
                      color: T.text,
                      lineHeight: 1.5,
                      marginBottom: 4,
                    }}
                  >
                    {patch.reason}
                  </div>

                  {/* Before / After */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      fontFamily: F,
                      fontSize: 9,
                    }}
                  >
                    {patch.old_value != null && (
                      <>
                        <span
                          style={{
                            padding: '1px 5px',
                            borderRadius: 3,
                            background: `${T.red}15`,
                            color: T.red,
                            fontFamily: "'IBM Plex Mono', monospace",
                          }}
                        >
                          {formatValue(patch.old_value)}
                        </span>
                        <ChevronRight size={8} color={T.dim} />
                      </>
                    )}
                    {patch.new_value != null && (
                      <span
                        style={{
                          padding: '1px 5px',
                          borderRadius: 3,
                          background: `${T.green}15`,
                          color: T.green,
                          fontFamily: "'IBM Plex Mono', monospace",
                        }}
                      >
                        {formatValue(patch.new_value)}
                      </span>
                    )}
                    {patch.action === 'delete' && (
                      <span
                        style={{
                          padding: '1px 5px',
                          borderRadius: 3,
                          background: `${T.red}15`,
                          color: T.red,
                        }}
                      >
                        remove
                      </span>
                    )}
                    {patch.action === 'insert_converter' && patch.new_value != null && (
                      <span
                        style={{
                          padding: '1px 5px',
                          borderRadius: 3,
                          background: `${T.cyan}15`,
                          color: T.cyan,
                          fontFamily: "'IBM Plex Mono', monospace",
                        }}
                      >
                        + {(patch.new_value as any).converter_label ?? 'converter'}
                      </span>
                    )}
                  </div>

                  {/* Confidence badge */}
                  <div style={{ marginTop: 4 }}>
                    <span
                      style={{
                        padding: '1px 5px',
                        borderRadius: 8,
                        fontFamily: F,
                        fontSize: 8,
                        fontWeight: 700,
                        letterSpacing: '0.08em',
                        background: isHigh ? `${T.green}15` : `${T.amber}15`,
                        color: isHigh ? T.green : T.amber,
                      }}
                    >
                      {patch.confidence.toUpperCase()}
                    </span>
                    <span
                      style={{
                        fontFamily: F,
                        fontSize: 8,
                        color: T.dim,
                        marginLeft: 6,
                      }}
                    >
                      {patch.action} {patch.field}
                    </span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Footer actions */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '10px 16px',
            borderTop: `1px solid ${T.border}`,
          }}
        >
          <button
            onClick={selectAll}
            disabled={isApplying}
            style={{
              background: 'none',
              border: 'none',
              fontFamily: F,
              fontSize: FS.xxs,
              color: T.cyan,
              cursor: isApplying ? 'not-allowed' : 'pointer',
              padding: '2px 4px',
            }}
          >
            Select All
          </button>

          <div style={{ flex: 1 }} />

          <button
            onClick={handleApplyAll}
            disabled={isApplying || patches.length === 0}
            style={{
              padding: '5px 12px',
              borderRadius: 6,
              border: `1px solid ${T.border}`,
              background: T.surface,
              fontFamily: F,
              fontSize: FS.xxs,
              fontWeight: 600,
              color: T.text,
              cursor: isApplying ? 'not-allowed' : 'pointer',
              opacity: isApplying ? 0.5 : 1,
            }}
          >
            Apply All
          </button>

          <button
            onClick={handleApplySelected}
            disabled={isApplying || selectedCount === 0}
            style={{
              padding: '5px 14px',
              borderRadius: 6,
              border: 'none',
              background: selectedCount > 0 ? T.cyan : T.dim,
              fontFamily: F,
              fontSize: FS.xxs,
              fontWeight: 700,
              color: '#000',
              cursor: isApplying || selectedCount === 0 ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              opacity: isApplying || selectedCount === 0 ? 0.5 : 1,
            }}
          >
            {isApplying ? (
              <>
                <Loader2 size={10} style={{ animation: 'spin 1s linear infinite' }} />
                Applying...
              </>
            ) : (
              `Apply Selected (${selectedCount})`
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

/** Format a value for display in before/after preview. */
function formatValue(value: unknown): string {
  if (value === null || value === undefined) return 'null'
  if (typeof value === 'string') return value
  if (typeof value === 'object') {
    try {
      const s = JSON.stringify(value)
      return s.length > 60 ? s.slice(0, 57) + '...' : s
    } catch {
      return String(value)
    }
  }
  return String(value)
}
