/**
 * VariantConfigDialog — modal for creating pipeline variants with config autofill.
 *
 * Shown when the user clones a pipeline as an experiment variant.
 * Combines rule-based field highlighting (always available) with AI-powered
 * config suggestions (requires Ollama/MLX).
 */

import { useState, useCallback, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { T, F, FS, DEPTH, MOTION } from '@/lib/design-tokens'
import { api } from '@/api/client'

// ── Types ─────────────────────────────────────────────────────────

interface VariantFieldChange {
  field: string
  current_value: unknown
  suggested_value: unknown
}

interface VariantNodeChanges {
  node_id: string
  node_label: string
  changes: VariantFieldChange[]
}

interface SuggestVariantResponse {
  suggestions: VariantNodeChanges[]
  field_hints: Record<string, string[]>
}

interface Props {
  visible: boolean
  pipelineId: string
  pipelineName: string
  /** Pipeline definition with nodes/edges for local field hint display */
  definition: { nodes?: any[]; edges?: any[] }
  onClose: () => void
  onConfirm: (configOverrides: Record<string, Record<string, unknown>>) => void
}

// ── Helpers ───────────────────────────────────────────────────────

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '(not set)'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

// ── Component ─────────────────────────────────────────────────────

export default function VariantConfigDialog({
  visible,
  pipelineId,
  pipelineName,
  definition,
  onClose,
  onConfirm,
}: Props) {
  const [intent, setIntent] = useState('')
  const [loading, setLoading] = useState(false)
  const [suggestions, setSuggestions] = useState<VariantNodeChanges[]>([])
  const [fieldHints, setFieldHints] = useState<Record<string, string[]>>({})
  const [accepted, setAccepted] = useState<Record<string, Record<string, boolean>>>({})
  const [hasSuggested, setHasSuggested] = useState(false)

  // Fetch rule-based field hints on mount
  useEffect(() => {
    if (!visible || !pipelineId) return
    api
      .post<SuggestVariantResponse>('/copilot/suggest-variant', {
        source_pipeline_id: pipelineId,
        intent: '',
      })
      .then((res) => {
        setFieldHints(res.field_hints)
      })
      .catch(() => {})
  }, [visible, pipelineId])

  // Request AI suggestions
  const handleSuggest = useCallback(async () => {
    if (!intent.trim()) return
    setLoading(true)
    try {
      const res = await api.post<SuggestVariantResponse>('/copilot/suggest-variant', {
        source_pipeline_id: pipelineId,
        intent: intent.trim(),
      })
      setSuggestions(res.suggestions)
      setFieldHints(res.field_hints)
      // Auto-accept all suggestions by default
      const acc: Record<string, Record<string, boolean>> = {}
      for (const node of res.suggestions) {
        acc[node.node_id] = {}
        for (const change of node.changes) {
          acc[node.node_id][change.field] = true
        }
      }
      setAccepted(acc)
      setHasSuggested(true)
    } catch {
      // AI unavailable — show a note
      setHasSuggested(true)
    } finally {
      setLoading(false)
    }
  }, [intent, pipelineId])

  const toggleAccept = useCallback((nodeId: string, field: string) => {
    setAccepted((prev) => ({
      ...prev,
      [nodeId]: {
        ...prev[nodeId],
        [field]: !prev[nodeId]?.[field],
      },
    }))
  }, [])

  const handleConfirm = useCallback(() => {
    const overrides: Record<string, Record<string, unknown>> = {}
    for (const node of suggestions) {
      for (const change of node.changes) {
        if (accepted[node.node_id]?.[change.field]) {
          if (!overrides[node.node_id]) overrides[node.node_id] = {}
          overrides[node.node_id][change.field] = change.suggested_value
        }
      }
    }
    onConfirm(overrides)
  }, [suggestions, accepted, onConfirm])

  const handleReset = useCallback(() => {
    setIntent('')
    setSuggestions([])
    setAccepted({})
    setHasSuggested(false)
  }, [])

  // Build highlighted fields display from rule-based hints
  const nodes = definition?.nodes || []
  const nodeMap = Object.fromEntries(nodes.map((n: any) => [n.id, n]))

  if (!visible) return null

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
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
            width: 500,
            maxHeight: '75vh',
            overflowY: 'auto',
            boxShadow: DEPTH.modal,
            fontFamily: F,
          }}
        >
          {/* Title */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 16,
            }}
          >
            <span style={{ fontSize: FS.lg, fontWeight: 700, color: T.text }}>
              Clone as Variant
            </span>
            <button
              onClick={onClose}
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

          <div style={{ fontSize: FS.sm, color: T.sec, marginBottom: 16 }}>
            Creating variant of <strong>{pipelineName}</strong>
          </div>

          {/* Rule-based field hints */}
          {Object.keys(fieldHints).length > 0 && (
            <div
              style={{
                background: T.surface3,
                border: `1px solid ${T.border}`,
                borderRadius: 8,
                padding: '10px 12px',
                marginBottom: 16,
                fontSize: FS.xs,
              }}
            >
              <div
                style={{
                  color: T.dim,
                  fontWeight: 600,
                  marginBottom: 6,
                  fontSize: FS.xxs,
                  textTransform: 'uppercase',
                  letterSpacing: 0.5,
                }}
              >
                Commonly varied fields
              </div>
              {Object.entries(fieldHints).map(([nodeId, fields]) => {
                const node = nodeMap[nodeId]
                const label = node?.data?.label || nodeId
                return (
                  <div key={nodeId} style={{ marginBottom: 4 }}>
                    <span style={{ color: T.sec }}>{label}: </span>
                    <span style={{ color: T.cyan }}>
                      {fields.join(', ')}
                    </span>
                  </div>
                )
              })}
            </div>
          )}

          {/* Intent input */}
          <div style={{ marginBottom: 12 }}>
            <label
              style={{
                fontSize: FS.xs,
                color: T.sec,
                display: 'block',
                marginBottom: 4,
              }}
            >
              What's different?
            </label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                value={intent}
                onChange={(e) => setIntent(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !loading) handleSuggest()
                }}
                placeholder="e.g. same but with a larger model, or try higher learning rate"
                style={{
                  flex: 1,
                  background: T.surface3,
                  border: `1px solid ${T.border}`,
                  borderRadius: 6,
                  padding: '8px 10px',
                  color: T.text,
                  fontSize: FS.sm,
                  fontFamily: F,
                  outline: 'none',
                }}
              />
              <button
                onClick={handleSuggest}
                disabled={loading || !intent.trim()}
                style={{
                  background: `${T.cyan}18`,
                  border: `1px solid ${T.cyan}40`,
                  borderRadius: 6,
                  color: T.cyan,
                  fontSize: FS.xs,
                  fontWeight: 600,
                  padding: '8px 14px',
                  cursor: loading || !intent.trim() ? 'not-allowed' : 'pointer',
                  opacity: loading || !intent.trim() ? 0.5 : 1,
                  fontFamily: F,
                  whiteSpace: 'nowrap',
                }}
              >
                {loading ? 'Thinking...' : 'Suggest Changes'}
              </button>
            </div>
          </div>

          {/* AI suggestions */}
          {hasSuggested && suggestions.length === 0 && (
            <div
              style={{
                textAlign: 'center',
                color: T.dim,
                fontSize: FS.xs,
                padding: '12px 0',
              }}
            >
              {loading
                ? 'Analyzing...'
                : 'No AI suggestions available. You can manually adjust configs after cloning.'}
            </div>
          )}

          {suggestions.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <div
                style={{
                  fontSize: FS.xxs,
                  color: T.dim,
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: 0.5,
                  marginBottom: 8,
                }}
              >
                Suggested config changes
              </div>
              {suggestions.map((node) => (
                <div
                  key={node.node_id}
                  style={{
                    background: T.surface3,
                    border: `1px solid ${T.border}`,
                    borderRadius: 8,
                    padding: '8px 10px',
                    marginBottom: 6,
                  }}
                >
                  <div
                    style={{
                      fontSize: FS.xs,
                      fontWeight: 600,
                      color: T.text,
                      marginBottom: 6,
                    }}
                  >
                    {node.node_label}
                  </div>
                  {node.changes.map((change) => (
                    <label
                      key={`${node.node_id}-${change.field}`}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        padding: '3px 0',
                        cursor: 'pointer',
                        fontSize: FS.xs,
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={accepted[node.node_id]?.[change.field] ?? false}
                        onChange={() => toggleAccept(node.node_id, change.field)}
                        style={{ accentColor: T.cyan }}
                      />
                      <span style={{ color: T.sec, minWidth: 100 }}>
                        {change.field}
                      </span>
                      <span style={{ color: T.dim }}>
                        {formatValue(change.current_value)}
                      </span>
                      <span style={{ color: T.dim }}>{'\u2192'}</span>
                      <span style={{ color: T.cyan, fontWeight: 600 }}>
                        {formatValue(change.suggested_value)}
                      </span>
                    </label>
                  ))}
                </div>
              ))}
            </div>
          )}

          {/* Actions */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'flex-end',
              gap: 8,
              paddingTop: 8,
              borderTop: `1px solid ${T.border}`,
            }}
          >
            {hasSuggested && (
              <button
                onClick={handleReset}
                style={{
                  background: 'none',
                  border: `1px solid ${T.border}`,
                  borderRadius: 6,
                  color: T.dim,
                  fontSize: FS.xs,
                  padding: '8px 14px',
                  cursor: 'pointer',
                  fontFamily: F,
                }}
              >
                Reset
              </button>
            )}
            <button
              onClick={onClose}
              style={{
                background: 'none',
                border: `1px solid ${T.border}`,
                borderRadius: 6,
                color: T.sec,
                fontSize: FS.xs,
                padding: '8px 14px',
                cursor: 'pointer',
                fontFamily: F,
              }}
            >
              Cancel
            </button>
            <button
              onClick={handleConfirm}
              style={{
                background: T.cyan,
                border: 'none',
                borderRadius: 6,
                color: '#000',
                fontSize: FS.xs,
                fontWeight: 600,
                padding: '8px 18px',
                cursor: 'pointer',
                fontFamily: F,
              }}
            >
              Clone Variant
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
