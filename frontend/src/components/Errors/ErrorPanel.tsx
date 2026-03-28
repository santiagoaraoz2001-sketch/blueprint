import { useMemo, useCallback, createContext, useContext } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { AlertTriangle, AlertCircle, Info, X, Crosshair, Wrench } from 'lucide-react'
import { T, F, FS } from '@/lib/design-tokens'
import { useErrorStore, type PipelineError, type ErrorSeverity } from '@/stores/errorStore'
import { usePipelineStore } from '@/stores/pipelineStore'
import { api } from '@/api/client'

// ── ReactFlow integration layer ──────────────────────────────────────
// ErrorPanel must work whether or not a ReactFlowProvider ancestor exists.
// We use a context so the parent (PipelineEditorView, inside the provider)
// can inject the fitView function.  If nobody provides it, the panel
// degrades gracefully — "center on node" still selects the node, it just
// can't animate the canvas viewport.

type FitViewFn = (opts: { nodes: { id: string }[]; duration: number; padding: number }) => void

const FitViewContext = createContext<FitViewFn | null>(null)

/**
 * Wrap ErrorPanel with this provider inside a ReactFlowProvider to enable
 * "center on node" canvas navigation.  If omitted, ErrorPanel still works
 * — it just selects the node without viewport animation.
 *
 * Usage:
 * ```tsx
 * import { useReactFlow } from '@xyflow/react'
 *
 * function CanvasWrapper() {
 *   const { fitView } = useReactFlow()
 *   return (
 *     <ErrorPanelFitViewProvider fitView={fitView}>
 *       <ErrorPanel />
 *     </ErrorPanelFitViewProvider>
 *   )
 * }
 * ```
 */
export function ErrorPanelFitViewProvider({
  fitView,
  children,
}: {
  fitView: FitViewFn
  children: React.ReactNode
}) {
  return (
    <FitViewContext.Provider value={fitView}>
      {children}
    </FitViewContext.Provider>
  )
}

function useSafeFitView(): FitViewFn | null {
  return useContext(FitViewContext)
}

// ── Severity helpers ─────────────────────────────────────────────────

const SEVERITY_ICON: Record<ErrorSeverity, typeof AlertTriangle> = {
  error: AlertTriangle,
  warning: AlertCircle,
  info: Info,
}

function getSeverityColor(severity: ErrorSeverity): string {
  switch (severity) {
    case 'error':   return T.red
    case 'warning': return T.amber
    case 'info':    return T.blue
  }
}

// ── Error item row ───────────────────────────────────────────────────

function ErrorPanelItem({ error }: { error: PipelineError }) {
  const fitView = useSafeFitView()
  const focusErrorNode = usePipelineStore((s) => s.focusErrorNode)
  const Icon = SEVERITY_ICON[error.severity]
  const color = getSeverityColor(error.severity)

  const handleCenter = useCallback(() => {
    if (!error.nodeId) return
    focusErrorNode(error.nodeId)
    fitView?.({ nodes: [{ id: error.nodeId }], duration: 800, padding: 0.5 })
  }, [error.nodeId, focusErrorNode, fitView])

  const handleFix = useCallback(async () => {
    if (!error.recoveryType) return

    switch (error.recoveryType) {
      case 'start_service': {
        const name = error.recoveryPayload?.name
        if (name) {
          try {
            await api.post(`/system/start-service/${name}`, {})
            useErrorStore.getState().removeError(error.id)
          } catch { /* user sees toast from circuit breaker */ }
        }
        break
      }
      case 'open_config': {
        if (error.nodeId) {
          usePipelineStore.getState().selectNode(error.nodeId)
          handleCenter()
        }
        break
      }
      case 'suggest_connection': {
        if (error.nodeId) {
          handleCenter()
        }
        break
      }
      case 'clear_cache': {
        const runId = error.recoveryPayload?.run_id
        if (runId) {
          try {
            await api.delete(`/artifacts/runs/${runId}`)
            useErrorStore.getState().removeError(error.id)
          } catch { /* user sees toast from circuit breaker */ }
        }
        break
      }
    }
  }, [error, handleCenter])

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '8px 12px',
        borderBottom: `1px solid ${T.border}`,
        cursor: error.nodeId ? 'pointer' : 'default',
      }}
      onClick={handleCenter}
    >
      <Icon size={14} color={color} style={{ flexShrink: 0 }} />

      <div style={{ flex: 1, minWidth: 0 }}>
        {error.nodeName && (
          <span style={{
            fontFamily: F,
            fontSize: FS.xxs,
            fontWeight: 700,
            color: T.text,
            marginRight: 6,
          }}>
            {error.nodeName}
          </span>
        )}
        <span style={{
          fontFamily: F,
          fontSize: FS.xxs,
          color: T.sec,
        }}>
          {error.message}
        </span>
      </div>

      {error.nodeId && (
        <button
          onClick={(e) => { e.stopPropagation(); handleCenter() }}
          title="Center on node"
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: 2,
            color: T.dim,
            display: 'flex',
          }}
        >
          <Crosshair size={12} />
        </button>
      )}

      {error.recoveryType && (
        <button
          onClick={(e) => { e.stopPropagation(); handleFix() }}
          title="Fix"
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            fontWeight: 700,
            color: T.cyan,
            background: `${T.cyan}12`,
            border: `1px solid ${T.cyan}30`,
            borderRadius: 4,
            padding: '2px 8px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            whiteSpace: 'nowrap',
          }}
        >
          <Wrench size={10} />
          Fix
        </button>
      )}
    </div>
  )
}

// ── Main panel ───────────────────────────────────────────────────────

export default function ErrorPanel() {
  const errors = useErrorStore((s) => s.errors)
  const panelOpen = useErrorStore((s) => s.panelOpen)
  const togglePanel = useErrorStore((s) => s.togglePanel)

  const errorCount = errors.filter((e) => e.severity === 'error').length
  const warningCount = errors.filter((e) => e.severity === 'warning').length
  const totalCount = errors.length

  // Sort: errors first, then warnings, then info
  const sorted = useMemo(() => {
    const order: Record<ErrorSeverity, number> = { error: 0, warning: 1, info: 2 }
    return [...errors].sort((a, b) => order[a.severity] - order[b.severity])
  }, [errors])

  // Group by severity
  const groups = useMemo(() => {
    const g: Record<ErrorSeverity, PipelineError[]> = { error: [], warning: [], info: [] }
    for (const e of sorted) g[e.severity].push(e)
    return g
  }, [sorted])

  if (totalCount === 0) return null

  return (
    <>
      {/* Toggle button — always visible at bottom-right of canvas */}
      <div
        style={{
          position: 'absolute',
          bottom: panelOpen ? 260 : 12,
          right: 12,
          zIndex: 100,
          transition: 'bottom 0.3s ease',
        }}
      >
        <button
          onClick={togglePanel}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            fontFamily: F,
            fontSize: FS.xs,
            fontWeight: 700,
            color: errorCount > 0 ? T.red : T.amber,
            background: T.surface2,
            border: `1px solid ${errorCount > 0 ? T.red : T.amber}40`,
            borderRadius: 8,
            padding: '6px 12px',
            cursor: 'pointer',
            boxShadow: `0 4px 12px ${T.shadow}`,
          }}
        >
          <AlertTriangle size={14} />
          {errorCount > 0 && (
            <span style={{
              background: T.red,
              color: '#fff',
              borderRadius: 10,
              padding: '0 6px',
              fontSize: FS.xxs,
              fontWeight: 900,
              lineHeight: '16px',
              minWidth: 16,
              textAlign: 'center',
            }}>
              {errorCount}
            </span>
          )}
          {warningCount > 0 && (
            <span style={{
              background: T.amber,
              color: '#000',
              borderRadius: 10,
              padding: '0 6px',
              fontSize: FS.xxs,
              fontWeight: 900,
              lineHeight: '16px',
              minWidth: 16,
              textAlign: 'center',
            }}>
              {warningCount}
            </span>
          )}
        </button>
      </div>

      {/* Sliding panel */}
      <AnimatePresence>
        {panelOpen && (
          <motion.div
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            style={{
              position: 'absolute',
              bottom: 0,
              left: 0,
              right: 0,
              height: 250,
              background: T.surface1,
              borderTop: `1px solid ${T.border}`,
              zIndex: 99,
              display: 'flex',
              flexDirection: 'column',
              boxShadow: `0 -8px 24px ${T.shadowHeavy}`,
            }}
          >
            {/* Panel header */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '8px 14px',
              borderBottom: `1px solid ${T.border}`,
              flexShrink: 0,
            }}>
              <span style={{
                fontFamily: F,
                fontSize: FS.sm,
                fontWeight: 700,
                color: T.text,
                letterSpacing: '0.02em',
              }}>
                Issues ({totalCount})
              </span>
              <button
                onClick={togglePanel}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: T.dim,
                  display: 'flex',
                  padding: 2,
                }}
              >
                <X size={14} />
              </button>
            </div>

            {/* Error list */}
            <div style={{ flex: 1, overflowY: 'auto' }}>
              {(['error', 'warning', 'info'] as const).map((severity) => {
                const items = groups[severity]
                if (items.length === 0) return null
                return (
                  <div key={severity}>
                    <div style={{
                      fontFamily: F,
                      fontSize: FS.xxs,
                      fontWeight: 700,
                      color: getSeverityColor(severity),
                      padding: '6px 14px 2px',
                      textTransform: 'uppercase',
                      letterSpacing: '0.08em',
                    }}>
                      {severity === 'error' ? 'Errors' : severity === 'warning' ? 'Warnings' : 'Info'}
                      {' '}({items.length})
                    </div>
                    {items.map((err) => (
                      <ErrorPanelItem key={err.id} error={err} />
                    ))}
                  </div>
                )
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
