/**
 * CopilotPanel — floating copilot panel for pipeline alerts and AI explanations.
 *
 * Collapsed: teal circle with alert count badge at bottom-right.
 * Expanded: ~300px wide, ~400px tall panel with alert cards and explain button.
 * Auto-updates on graph changes (debounced 300ms).
 *
 * Rule-based alerts run entirely client-side (zero network calls) via the
 * TypeScript rule engine in lib/copilot-rules.ts. Only AI features
 * (explain, diagnose) require the backend API.
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useReactFlow } from '@xyflow/react'
import { motion, AnimatePresence } from 'framer-motion'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useShallow } from 'zustand/react/shallow'
import { T, F, FS, GLOW, DEPTH, MOTION } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { api } from '@/api/client'
import { evaluateRules, type CopilotAlert } from '@/lib/copilot-rules'

// ── Types ─────────────────────────────────────────────────────────

interface CopilotStatus {
  rules_available: boolean
  ai_available: boolean
  message: string
}

// ── Severity Helpers ──────────────────────────────────────────────

const SEVERITY_ICON: Record<string, string> = {
  error: '\u26D4',
  warning: '\u26A0\uFE0F',
  info: '\u2139\uFE0F',
}

const SEVERITY_COLOR: Record<string, string> = {
  error: T.red,
  warning: T.amber,
  info: T.blue,
}

// ── Component ─────────────────────────────────────────────────────

export default function CopilotPanel() {
  const expanded = useUIStore((s) => s.copilotOpen)
  const setExpanded = useUIStore((s) => s.setCopilotOpen)
  const [alerts, setAlerts] = useState<CopilotAlert[]>([])
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  const [aiStatus, setAiStatus] = useState<CopilotStatus | null>(null)
  const [explanation, setExplanation] = useState<string | null>(null)
  const [showExplanation, setShowExplanation] = useState(false)
  const [loading, setLoading] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { nodes, edges } = usePipelineStore(
    useShallow((s) => ({ nodes: s.nodes, edges: s.edges }))
  )

  const { setCenter } = useReactFlow()

  // Fetch copilot AI status once (only affects "AI active" indicator)
  useEffect(() => {
    api
      .get<CopilotStatus>('/copilot/status')
      .then(setAiStatus)
      .catch(() => {})
  }, [])

  // Evaluate rules CLIENT-SIDE on graph changes (debounced 300ms, no network)
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      if (!nodes.length) {
        setAlerts([])
        return
      }
      const result = evaluateRules(nodes, edges)
      setAlerts(result)
    }, 300)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [nodes, edges])

  // Filter out dismissed alerts
  const visibleAlerts = useMemo(
    () => alerts.filter((a) => !dismissed.has(a.id)),
    [alerts, dismissed]
  )

  const errorCount = visibleAlerts.filter((a) => a.severity === 'error').length
  const warningCount = visibleAlerts.filter((a) => a.severity === 'warning').length
  const totalCount = visibleAlerts.length

  // Center canvas on affected node
  const handleNodeClick = useCallback(
    (nodeId: string) => {
      const node = nodes.find((n) => n.id === nodeId)
      if (node) {
        setCenter(node.position.x + 100, node.position.y + 40, {
          duration: 400,
          zoom: 1.2,
        })
      }
    },
    [nodes, setCenter]
  )

  // Explain pipeline via AI
  const handleExplain = useCallback(async () => {
    setLoading(true)
    try {
      const payload = {
        nodes: nodes.map((n) => ({
          id: n.id,
          type: n.type,
          data: n.data,
        })),
        edges: edges.map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          sourceHandle: e.sourceHandle,
          targetHandle: e.targetHandle,
        })),
      }
      const result = await api.post<{
        available: boolean
        explanation: string | null
        message?: string
      }>('/copilot/explain', payload)
      if (result.explanation) {
        setExplanation(result.explanation)
        setShowExplanation(true)
      } else {
        setExplanation(result.message || 'AI is not available.')
        setShowExplanation(true)
      }
    } catch {
      setExplanation('Failed to get explanation.')
      setShowExplanation(true)
    } finally {
      setLoading(false)
    }
  }, [nodes, edges])

  const handleDismiss = useCallback((alertId: string) => {
    setDismissed((prev) => new Set(prev).add(alertId))
  }, [])

  // Badge color
  const badgeColor = errorCount > 0 ? T.red : warningCount > 0 ? T.amber : T.cyan

  return (
    <>
      {/* Collapsed: floating badge */}
      <AnimatePresence>
        {!expanded && (
          <motion.button
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            transition={{ duration: MOTION.fast }}
            onClick={() => setExpanded(true)}
            style={{
              position: 'fixed',
              bottom: 24,
              right: 24,
              zIndex: 1000,
              width: 48,
              height: 48,
              borderRadius: '50%',
              border: `1px solid ${T.border}`,
              background: T.surface2,
              boxShadow: totalCount > 0 ? GLOW.medium(badgeColor) : DEPTH.card,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontFamily: F,
              fontSize: FS.lg,
              color: T.cyan,
              padding: 0,
            }}
            title="Open Copilot"
          >
            {'\u2728'}
            {totalCount > 0 && (
              <span
                style={{
                  position: 'absolute',
                  top: -4,
                  right: -4,
                  background: badgeColor,
                  color: '#000',
                  borderRadius: 10,
                  minWidth: 18,
                  height: 18,
                  fontSize: FS.xxs,
                  fontWeight: 700,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: '0 4px',
                }}
              >
                {totalCount}
              </span>
            )}
          </motion.button>
        )}
      </AnimatePresence>

      {/* Expanded panel */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={{ duration: MOTION.base }}
            style={{
              position: 'fixed',
              bottom: 24,
              right: 24,
              zIndex: 1000,
              width: 320,
              maxWidth: 'min(320px, calc(100vw - 48px))',
              maxHeight: 420,
              borderRadius: 12,
              border: `1px solid ${T.border}`,
              background: T.surface,
              boxShadow: DEPTH.float,
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
              fontFamily: F,
            }}
          >
            {/* Header */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 14px',
                borderBottom: `1px solid ${T.border}`,
                background: T.surface2,
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <span style={{ fontSize: FS.md, color: T.cyan }}>
                  {'\u2728'}
                </span>
                <span
                  style={{
                    fontSize: FS.sm,
                    fontWeight: 600,
                    color: T.text,
                  }}
                >
                  Copilot
                </span>
                {totalCount > 0 && (
                  <span
                    style={{
                      fontSize: FS.xxs,
                      color: T.dim,
                      background: T.surface4,
                      borderRadius: 8,
                      padding: '1px 6px',
                    }}
                  >
                    {totalCount} alert{totalCount !== 1 ? 's' : ''}
                  </span>
                )}
              </div>
              <button
                onClick={() => setExpanded(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: T.dim,
                  cursor: 'pointer',
                  fontSize: FS.md,
                  padding: '2px 6px',
                  borderRadius: 4,
                  lineHeight: 1,
                }}
                title="Collapse"
              >
                {'\u2715'}
              </button>
            </div>

            {/* Alert list */}
            <div
              style={{
                flex: 1,
                overflowY: 'auto',
                padding: '8px 10px',
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
              }}
            >
              {visibleAlerts.length === 0 && (
                <div
                  style={{
                    textAlign: 'center',
                    color: T.dim,
                    fontSize: FS.sm,
                    padding: '24px 0',
                  }}
                >
                  No issues detected
                </div>
              )}

              {visibleAlerts.map((alert) => (
                <div
                  key={alert.id}
                  style={{
                    background: T.surface3,
                    border: `1px solid ${SEVERITY_COLOR[alert.severity]}30`,
                    borderRadius: 8,
                    padding: '8px 10px',
                    fontSize: FS.xs,
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      marginBottom: 4,
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                      }}
                    >
                      <span style={{ fontSize: FS.sm }}>
                        {SEVERITY_ICON[alert.severity]}
                      </span>
                      <span
                        style={{
                          fontWeight: 600,
                          color: SEVERITY_COLOR[alert.severity],
                          fontSize: FS.xs,
                        }}
                      >
                        {alert.title}
                      </span>
                    </div>
                    {alert.auto_dismissible && (
                      <button
                        onClick={() => handleDismiss(alert.id)}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: T.dim,
                          cursor: 'pointer',
                          fontSize: FS.xxs,
                          padding: '0 4px',
                          lineHeight: 1,
                        }}
                        title="Dismiss"
                      >
                        {'\u2715'}
                      </button>
                    )}
                  </div>
                  <div
                    style={{
                      color: T.sec,
                      fontSize: FS.xxs,
                      lineHeight: 1.4,
                      marginBottom: alert.affected_node_id || alert.suggested_action ? 6 : 0,
                    }}
                  >
                    {alert.message}
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      flexWrap: 'wrap',
                    }}
                  >
                    {alert.affected_node_id && (
                      <button
                        onClick={() => handleNodeClick(alert.affected_node_id!)}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: T.cyan,
                          cursor: 'pointer',
                          fontSize: FS.xxs,
                          padding: 0,
                          textDecoration: 'underline',
                        }}
                      >
                        Go to block
                      </button>
                    )}
                    {alert.suggested_action && (
                      <span
                        style={{
                          color: T.cyan,
                          fontSize: FS.xxs,
                          opacity: 0.8,
                        }}
                      >
                        {alert.suggested_action}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Footer: AI status + Explain button */}
            <div
              style={{
                borderTop: `1px solid ${T.border}`,
                padding: '8px 10px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                background: T.surface2,
              }}
            >
              <span style={{ fontSize: FS.xxs, color: T.dim }}>
                {aiStatus?.ai_available
                  ? 'AI active'
                  : 'AI features require Ollama'}
              </span>
              <button
                onClick={handleExplain}
                disabled={loading}
                style={{
                  background: `${T.cyan}18`,
                  border: `1px solid ${T.cyan}40`,
                  borderRadius: 6,
                  color: T.cyan,
                  fontSize: FS.xxs,
                  fontWeight: 600,
                  padding: '4px 10px',
                  cursor: loading ? 'wait' : 'pointer',
                  opacity: loading ? 0.6 : 1,
                  fontFamily: F,
                }}
              >
                {loading ? 'Thinking...' : 'Explain Pipeline'}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Explanation modal */}
      <AnimatePresence>
        {showExplanation && explanation && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowExplanation(false)}
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: 2000,
              background: 'rgba(0,0,0,0.6)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              style={{
                background: T.raised,
                border: `1px solid ${T.border}`,
                borderRadius: 12,
                padding: 24,
                maxWidth: 560,
                maxHeight: '70vh',
                overflowY: 'auto',
                boxShadow: DEPTH.modal,
                fontFamily: F,
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: 16,
                }}
              >
                <span
                  style={{
                    fontSize: FS.lg,
                    fontWeight: 700,
                    color: T.text,
                  }}
                >
                  Pipeline Explanation
                </span>
                <button
                  onClick={() => setShowExplanation(false)}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: T.dim,
                    cursor: 'pointer',
                    fontSize: FS.lg,
                  }}
                >
                  {'\u2715'}
                </button>
              </div>
              <div
                style={{
                  color: T.sec,
                  fontSize: FS.sm,
                  lineHeight: 1.6,
                  whiteSpace: 'pre-wrap',
                }}
              >
                {explanation}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
