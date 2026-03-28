/**
 * Backend Validation Panel — collapsible panel that slides up from the bottom
 * of the canvas, listing all backend validation errors and warnings.
 *
 * - Grouped by severity (errors first, then warnings)
 * - Click any item to center the canvas on the affected node
 * - Error count badge on the toggle button
 */

import { useState, useCallback } from 'react'
import { useReactFlow } from '@xyflow/react'
import { T, F, FS } from '@/lib/design-tokens'
import { useValidationStore } from '@/stores/validationStore'
import { usePipelineStore } from '@/stores/pipelineStore'
import { api } from '@/api/client'
import AutofixPreview, { type AutofixPatch } from './AutofixPreview'
import {
  AlertTriangle,
  XCircle,
  AlertCircle,
  ChevronUp,
  ChevronDown,
  X,
  Loader2,
  CheckCircle2,
  Wrench,
} from 'lucide-react'

export default function BackendValidationPanel() {
  const result = useValidationStore((s) => s.result)
  const isValidating = useValidationStore((s) => s.isValidating)
  const isStale = useValidationStore((s) => s.isStale)
  const panelVisible = useValidationStore((s) => s.panelVisible)
  const togglePanel = useValidationStore((s) => s.togglePanel)
  const setPanelVisible = useValidationStore((s) => s.setPanelVisible)
  const nodeErrors = useValidationStore((s) => s.nodeErrors)
  const validate = useValidationStore((s) => s.validate)
  const isPending = isValidating || isStale

  const nodes = usePipelineStore((s) => s.nodes)
  const pipelineId = usePipelineStore((s) => s.id)
  const focusErrorNode = usePipelineStore((s) => s.focusErrorNode)
  const pushHistory = usePipelineStore((s) => s.pushHistory)
  const { fitView } = useReactFlow()

  // Autofix state
  const [autofixPatches, setAutofixPatches] = useState<AutofixPatch[]>([])
  const [showAutofixModal, setShowAutofixModal] = useState(false)
  const [isProposing, setIsProposing] = useState(false)
  const [isApplying, setIsApplying] = useState(false)

  const errorCount = result ? result.errors.length : 0
  const warningCount = result ? result.warnings.length : 0
  const totalCount = errorCount + warningCount

  const handleItemClick = useCallback(
    (nodeId: string) => {
      focusErrorNode(nodeId)
      fitView({ nodes: [{ id: nodeId }], duration: 800, padding: 0.5 })
    },
    [focusErrorNode, fitView],
  )

  // ── Autofix handlers ──

  const handleProposeAutofix = useCallback(async () => {
    if (!pipelineId) return
    setIsProposing(true)
    try {
      const resp = await api.post<{
        patches: AutofixPatch[]
        applied: string[]
        skipped: Array<{ patch_id: string; reason: string }>
      }>(`/pipelines/${pipelineId}/autofix`, { action: 'propose' })
      if (resp && resp.patches.length > 0) {
        setAutofixPatches(resp.patches)
        setShowAutofixModal(true)
      }
    } catch {
      // Silently fail — autofix is best-effort
    } finally {
      setIsProposing(false)
    }
  }, [pipelineId])

  const handleApplyAutofix = useCallback(async (patchIds: string[]) => {
    if (!pipelineId || patchIds.length === 0) return
    setIsApplying(true)
    try {
      const resp = await api.post<{
        patches: AutofixPatch[]
        applied: string[]
        skipped: Array<{ patch_id: string; reason: string }>
        definition: { nodes: any[]; edges: any[] } | null
      }>(`/pipelines/${pipelineId}/autofix`, { action: 'apply', patch_ids: patchIds })

      if (resp && resp.applied.length > 0 && resp.definition) {
        // Push current state to undo history before applying changes.
        // This makes the entire autofix a single undo entry.
        pushHistory()

        // Apply the definition returned by the autofix endpoint directly
        // to local state — no redundant GET, no race condition.
        const { applyDefinition } = usePipelineStore.getState()
        applyDefinition(resp.definition)

        // Close modal and re-validate
        setShowAutofixModal(false)
        setAutofixPatches([])
        await validate(pipelineId)
      }
    } catch {
      // Silently fail
    } finally {
      setIsApplying(false)
    }
  }, [pipelineId, pushHistory, validate])

  // Build a flat item list from errors + warnings with node attribution
  const items = (() => {
    if (!result) return []
    const labelToId = new Map<string, string>()
    for (const n of nodes) {
      labelToId.set(n.data.label, n.id)
      labelToId.set(n.id, n.id)
    }

    const parseNodeId = (msg: string): string | null => {
      const match = msg.match(/Block '([^']+)'/)
      if (match) return labelToId.get(match[1]) ?? null
      const idMatch = msg.match(/\(([a-zA-Z0-9_-]+)\)/)
      if (idMatch) return labelToId.get(idMatch[1]) ?? null
      return null
    }

    const list: Array<{
      message: string
      severity: 'error' | 'warning'
      nodeId: string | null
      nodeName: string | null
    }> = []

    for (const err of result.errors) {
      const nodeId = parseNodeId(err)
      const nodeName = nodeId ? nodes.find((n) => n.id === nodeId)?.data.label ?? null : null
      list.push({ message: err, severity: 'error', nodeId, nodeName })
    }
    for (const warn of result.warnings) {
      const nodeId = parseNodeId(warn)
      const nodeName = nodeId ? nodes.find((n) => n.id === nodeId)?.data.label ?? null : null
      list.push({ message: warn, severity: 'warning', nodeId, nodeName })
    }
    return list
  })()

  // Don't render at all if there's no validation result
  if (!result && !isValidating) return null

  return (
    <>
      {/* Toggle button — bottom-center of canvas */}
      <div
        style={{
          position: 'absolute',
          bottom: panelVisible ? undefined : 12,
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 50,
          ...(panelVisible ? { bottom: Math.min(totalCount * 36 + 60, 300) + 12 } : {}),
        }}
      >
        <button
          onClick={togglePanel}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '4px 12px',
            background: errorCount > 0 ? `${T.red}20` : warningCount > 0 ? `${T.amber}15` : `${T.green}15`,
            border: `1px solid ${errorCount > 0 ? `${T.red}40` : warningCount > 0 ? `${T.amber}30` : `${T.green}30`}`,
            borderRadius: 16,
            cursor: 'pointer',
            fontFamily: F,
            fontSize: FS.xxs,
            fontWeight: 700,
            letterSpacing: '0.06em',
            color: errorCount > 0 ? T.red : warningCount > 0 ? T.amber : T.green,
            boxShadow: `0 4px 12px ${T.shadow}`,
            transition: 'all 0.15s',
          }}
        >
          {isPending ? (
            <Loader2 size={10} style={{ animation: 'spin 1s linear infinite' }} />
          ) : errorCount > 0 ? (
            <XCircle size={10} />
          ) : warningCount > 0 ? (
            <AlertTriangle size={10} />
          ) : (
            <CheckCircle2 size={10} />
          )}
          {isPending
            ? 'VALIDATING...'
            : errorCount > 0
              ? `${errorCount} ERROR${errorCount !== 1 ? 'S' : ''}`
              : warningCount > 0
                ? `${warningCount} WARNING${warningCount !== 1 ? 'S' : ''}`
                : 'VALID'}
          {totalCount > 0 && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                minWidth: 16,
                height: 16,
                borderRadius: 8,
                background: errorCount > 0 ? T.red : T.amber,
                color: '#000',
                fontSize: 9,
                fontWeight: 800,
              }}
            >
              {totalCount}
            </span>
          )}
          {panelVisible ? <ChevronDown size={10} /> : <ChevronUp size={10} />}
        </button>
      </div>

      {/* Collapsible panel — slides up from bottom */}
      {panelVisible && totalCount > 0 && (
        <div
          style={{
            position: 'absolute',
            bottom: 0,
            left: 0,
            right: 0,
            maxHeight: 300,
            background: T.surface2,
            borderTop: `1px solid ${errorCount > 0 ? `${T.red}40` : `${T.amber}30`}`,
            zIndex: 40,
            display: 'flex',
            flexDirection: 'column',
            boxShadow: `0 -4px 16px ${T.shadowHeavy}`,
          }}
        >
          {/* Panel header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '6px 12px',
              borderBottom: `1px solid ${T.border}`,
              flexShrink: 0,
            }}
          >
            <AlertCircle size={12} color={errorCount > 0 ? T.red : T.amber} />
            <span
              style={{
                fontFamily: F,
                fontSize: FS.xs,
                fontWeight: 700,
                color: T.text,
                letterSpacing: '0.06em',
                flex: 1,
              }}
            >
              VALIDATION ISSUES
            </span>
            {errorCount > 0 && (
              <span
                style={{
                  padding: '1px 6px',
                  borderRadius: 8,
                  background: `${T.red}20`,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  fontWeight: 700,
                  color: T.red,
                }}
              >
                {errorCount} error{errorCount !== 1 ? 's' : ''}
              </span>
            )}
            {warningCount > 0 && (
              <span
                style={{
                  padding: '1px 6px',
                  borderRadius: 8,
                  background: `${T.amber}15`,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  fontWeight: 700,
                  color: T.amber,
                }}
              >
                {warningCount} warning{warningCount !== 1 ? 's' : ''}
              </span>
            )}
            {/* Fix N Issues button */}
            {totalCount > 0 && (
              <button
                onClick={handleProposeAutofix}
                disabled={isProposing || isPending}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '2px 8px',
                  borderRadius: 6,
                  border: 'none',
                  background: T.cyan,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  fontWeight: 700,
                  color: '#000',
                  cursor: isProposing || isPending ? 'not-allowed' : 'pointer',
                  opacity: isProposing || isPending ? 0.5 : 1,
                  letterSpacing: '0.04em',
                }}
              >
                {isProposing ? (
                  <Loader2 size={9} style={{ animation: 'spin 1s linear infinite' }} />
                ) : (
                  <Wrench size={9} />
                )}
                {isProposing ? 'Scanning...' : `Fix ${totalCount} Issue${totalCount !== 1 ? 's' : ''}`}
              </button>
            )}
            <button
              onClick={() => setPanelVisible(false)}
              style={{
                background: 'none',
                border: 'none',
                color: T.dim,
                cursor: 'pointer',
                padding: 2,
                display: 'flex',
              }}
            >
              <X size={12} />
            </button>
          </div>

          {/* Items list */}
          <div style={{ overflowY: 'auto', padding: '4px 8px 8px' }}>
            {items.map((item, i) => {
              const color = item.severity === 'error' ? T.red : T.amber
              const Icon = item.severity === 'error' ? XCircle : AlertTriangle
              return (
                <div
                  key={i}
                  onClick={item.nodeId ? () => handleItemClick(item.nodeId!) : undefined}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 8,
                    padding: '5px 6px',
                    borderRadius: 4,
                    cursor: item.nodeId ? 'pointer' : 'default',
                    transition: 'background 0.1s',
                  }}
                  onMouseEnter={(e) => {
                    if (item.nodeId) e.currentTarget.style.background = `${color}10`
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'transparent'
                  }}
                >
                  <Icon size={11} color={color} style={{ flexShrink: 0, marginTop: 1 }} />
                  <div style={{ flex: 1 }}>
                    {item.nodeName && (
                      <span
                        style={{
                          fontFamily: F,
                          fontSize: FS.xxs,
                          fontWeight: 700,
                          color: T.sec,
                          marginRight: 6,
                        }}
                      >
                        {item.nodeName}
                      </span>
                    )}
                    <span
                      style={{
                        fontFamily: F,
                        fontSize: FS.xxs,
                        color,
                        lineHeight: 1.5,
                      }}
                    >
                      {item.message}
                    </span>
                    {item.nodeId && (
                      <span
                        style={{
                          fontFamily: F,
                          fontSize: 8,
                          color: T.cyan,
                          marginLeft: 6,
                          textDecoration: 'underline',
                          cursor: 'pointer',
                        }}
                      >
                        Focus
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Autofix preview modal */}
      {showAutofixModal && autofixPatches.length > 0 && (
        <AutofixPreview
          patches={autofixPatches}
          onApply={handleApplyAutofix}
          onClose={() => setShowAutofixModal(false)}
          isApplying={isApplying}
        />
      )}
    </>
  )
}
