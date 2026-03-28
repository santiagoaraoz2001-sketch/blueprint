import { useState, useEffect } from 'react'
import { T, F, FS, DEPTH } from '@/lib/design-tokens'
import { X, AlertTriangle, CheckCircle, XCircle, ChevronDown, ChevronRight, Loader2, Zap, HardDrive, Clock, BarChart3 } from 'lucide-react'
import { api } from '@/api/client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface NodeEstimate {
  estimated_memory_mb: number
  estimated_duration_class: 'seconds' | 'minutes' | 'hours'
  confidence: 'high' | 'medium' | 'low'
}

interface TotalEstimate {
  peak_memory_mb: number
  total_artifact_volume_mb: number
  runtime_class: 'seconds' | 'minutes' | 'hours'
  confidence: 'high' | 'medium' | 'low'
}

interface DryRunResult {
  viable: boolean
  blockers: string[]
  warnings: string[]
  per_node_estimates: Record<string, NodeEstimate>
  total_estimate: TotalEstimate
}

interface DryRunModalProps {
  open: boolean
  onClose: () => void
  pipelineId: string
  nodeLabels: Record<string, string>  // node_id -> display label
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const CONFIDENCE_DOT: Record<string, string> = {
  high: T.green,
  medium: T.amber,
  low: T.red,
}

function formatMemory(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`
  return `${mb} MB`
}

function formatDuration(cls: string): string {
  if (cls === 'hours') return '2\u20134 hours'
  if (cls === 'minutes') return '2\u201320 minutes'
  return '< 1 minute'
}

function confidenceLabel(c: string): string {
  return c.charAt(0).toUpperCase() + c.slice(1)
}

function buildSummary(total: TotalEstimate): string {
  const time = formatDuration(total.runtime_class)
  const mem = formatMemory(total.peak_memory_mb)
  return `This pipeline will likely take ${time} and use about ${mem} of memory. Confidence: ${confidenceLabel(total.confidence)} (${total.confidence === 'high' ? 'based on historical runs' : total.confidence === 'medium' ? 'based on model size estimates' : 'insufficient data for precise estimates'}).`
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function DryRunModal({ open, onClose, pipelineId, nodeLabels }: DryRunModalProps) {
  const [result, setResult] = useState<DryRunResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (!open) return
    setResult(null)
    setError(null)
    setLoading(true)

    let cancelled = false
    api.post<DryRunResult>(`/pipelines/${pipelineId}/dry-run`)
      .then((res) => {
        if (!cancelled) setResult(res)
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || 'Dry run failed')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [open, pipelineId])

  if (!open) return null

  const toggleNode = (nid: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev)
      if (next.has(nid)) next.delete(nid)
      else next.add(nid)
      return next
    })
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: T.shadowHeavy,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: 620,
          maxWidth: '90vw',
          maxHeight: '80vh',
          background: T.surface1,
          border: `1px solid ${T.borderHi}`,
          borderRadius: 8,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxShadow: DEPTH.modal,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '14px 16px',
          borderBottom: `1px solid ${T.border}`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Zap size={16} color={T.cyan} />
            <span style={{ fontFamily: F, fontSize: FS.md, color: T.text, fontWeight: 700 }}>
              Dry Run Simulation
            </span>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 4 }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
          {loading && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: 40 }}>
              <Loader2 size={18} color={T.cyan} style={{ animation: 'spin 1s linear infinite' }} />
              <span style={{ fontFamily: F, fontSize: FS.sm, color: T.sec }}>
                Simulating pipeline execution...
              </span>
            </div>
          )}

          {error && (
            <div style={{
              padding: 16,
              background: `${T.red}10`,
              border: `1px solid ${T.red}30`,
              borderRadius: 6,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <XCircle size={16} color={T.red} />
                <span style={{ fontFamily: F, fontSize: FS.sm, color: T.red, fontWeight: 600 }}>
                  Simulation Failed
                </span>
              </div>
              <p style={{ fontFamily: F, fontSize: FS.xs, color: T.red, marginTop: 8, margin: '8px 0 0 0' }}>
                {error}
              </p>
            </div>
          )}

          {result && (
            <>
              {/* Viability banner */}
              <div style={{
                padding: '12px 16px',
                background: result.viable ? `${T.green}10` : `${T.red}10`,
                border: `1px solid ${result.viable ? `${T.green}30` : `${T.red}30`}`,
                borderRadius: 6,
                marginBottom: 12,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  {result.viable
                    ? <CheckCircle size={18} color={T.green} />
                    : <XCircle size={18} color={T.red} />}
                  <span style={{
                    fontFamily: F, fontSize: FS.lg, fontWeight: 700,
                    color: result.viable ? T.green : T.red,
                  }}>
                    {result.viable ? 'Pipeline is viable' : 'Pipeline cannot run'}
                  </span>
                  {/* Confidence badge */}
                  <span style={{
                    marginLeft: 'auto',
                    padding: '2px 8px',
                    background: `${CONFIDENCE_DOT[result.total_estimate.confidence]}18`,
                    border: `1px solid ${CONFIDENCE_DOT[result.total_estimate.confidence]}40`,
                    borderRadius: 4,
                    fontFamily: F,
                    fontSize: FS.xxs,
                    color: CONFIDENCE_DOT[result.total_estimate.confidence],
                    fontWeight: 600,
                    letterSpacing: '0.06em',
                  }}>
                    {confidenceLabel(result.total_estimate.confidence)} confidence
                  </span>
                </div>
                {/* Plain-language summary */}
                <p style={{
                  fontFamily: F, fontSize: FS.sm, color: T.sec,
                  margin: 0, lineHeight: 1.5,
                }}>
                  {buildSummary(result.total_estimate)}
                </p>
              </div>

              {/* Summary cards row */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 12 }}>
                <div style={{
                  padding: '10px 12px',
                  background: T.surface2,
                  border: `1px solid ${T.border}`,
                  borderRadius: 6,
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <Clock size={12} color={T.dim} />
                    <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>
                      EST. RUNTIME
                    </span>
                  </div>
                  <span style={{ fontFamily: F, fontSize: FS.lg, color: T.text, fontWeight: 700 }}>
                    {formatDuration(result.total_estimate.runtime_class)}
                  </span>
                </div>

                <div style={{
                  padding: '10px 12px',
                  background: T.surface2,
                  border: `1px solid ${T.border}`,
                  borderRadius: 6,
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <HardDrive size={12} color={T.dim} />
                    <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>
                      PEAK MEMORY
                    </span>
                  </div>
                  <span style={{ fontFamily: F, fontSize: FS.lg, color: T.text, fontWeight: 700 }}>
                    {formatMemory(result.total_estimate.peak_memory_mb)}
                  </span>
                </div>

                <div style={{
                  padding: '10px 12px',
                  background: T.surface2,
                  border: `1px solid ${T.border}`,
                  borderRadius: 6,
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <BarChart3 size={12} color={T.dim} />
                    <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>
                      ARTIFACT VOL.
                    </span>
                  </div>
                  <span style={{ fontFamily: F, fontSize: FS.lg, color: T.text, fontWeight: 700 }}>
                    {formatMemory(result.total_estimate.total_artifact_volume_mb)}
                  </span>
                </div>
              </div>

              {/* Blockers */}
              {result.blockers.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <span style={{
                    fontFamily: F, fontSize: FS.xxs, color: T.red, fontWeight: 700,
                    letterSpacing: '0.08em', display: 'block', marginBottom: 6,
                  }}>
                    BLOCKERS
                  </span>
                  {result.blockers.map((b, i) => (
                    <div key={i} style={{
                      padding: '8px 12px',
                      background: `${T.red}08`,
                      border: `1px solid ${T.red}25`,
                      borderRadius: 4,
                      marginBottom: 4,
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 8,
                    }}>
                      <XCircle size={14} color={T.red} style={{ marginTop: 1, flexShrink: 0 }} />
                      <span style={{ fontFamily: F, fontSize: FS.xs, color: T.red, lineHeight: 1.5 }}>
                        {b}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Warnings */}
              {result.warnings.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <span style={{
                    fontFamily: F, fontSize: FS.xxs, color: T.amber, fontWeight: 700,
                    letterSpacing: '0.08em', display: 'block', marginBottom: 6,
                  }}>
                    WARNINGS
                  </span>
                  {result.warnings.map((w, i) => (
                    <div key={i} style={{
                      padding: '8px 12px',
                      background: `${T.amber}08`,
                      border: `1px solid ${T.amber}25`,
                      borderRadius: 4,
                      marginBottom: 4,
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 8,
                    }}>
                      <AlertTriangle size={14} color={T.amber} style={{ marginTop: 1, flexShrink: 0 }} />
                      <span style={{ fontFamily: F, fontSize: FS.xs, color: T.amber, lineHeight: 1.5 }}>
                        {w}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Per-node table */}
              {Object.keys(result.per_node_estimates).length > 0 && (
                <div>
                  <span style={{
                    fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 700,
                    letterSpacing: '0.08em', display: 'block', marginBottom: 6,
                  }}>
                    PER-NODE ESTIMATES
                  </span>
                  <div style={{
                    border: `1px solid ${T.border}`,
                    borderRadius: 6,
                    overflow: 'hidden',
                  }}>
                    {/* Header row */}
                    <div style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr 100px 110px 80px',
                      padding: '6px 12px',
                      background: T.surface3,
                      borderBottom: `1px solid ${T.border}`,
                    }}>
                      {['Node', 'Memory', 'Duration', 'Confidence'].map((h) => (
                        <span key={h} style={{
                          fontFamily: F, fontSize: FS.xxs, color: T.dim,
                          fontWeight: 700, letterSpacing: '0.06em',
                        }}>
                          {h.toUpperCase()}
                        </span>
                      ))}
                    </div>

                    {/* Data rows */}
                    {Object.entries(result.per_node_estimates).map(([nid, est]) => (
                      <div key={nid}>
                        <div
                          style={{
                            display: 'grid',
                            gridTemplateColumns: '1fr 100px 110px 80px',
                            padding: '8px 12px',
                            borderBottom: `1px solid ${T.border}10`,
                            cursor: 'pointer',
                            transition: 'background 0.1s',
                          }}
                          onClick={() => toggleNode(nid)}
                          onMouseEnter={(e) => { e.currentTarget.style.background = T.surface2 }}
                          onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            {expandedNodes.has(nid)
                              ? <ChevronDown size={12} color={T.dim} />
                              : <ChevronRight size={12} color={T.dim} />}
                            <span style={{ fontFamily: F, fontSize: FS.xs, color: T.text }}>
                              {nodeLabels[nid] || nid.slice(0, 12)}
                            </span>
                          </div>
                          <span style={{ fontFamily: F, fontSize: FS.xs, color: T.sec }}>
                            {formatMemory(est.estimated_memory_mb)}
                          </span>
                          <span style={{ fontFamily: F, fontSize: FS.xs, color: T.sec }}>
                            {est.estimated_duration_class}
                          </span>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <div style={{
                              width: 8, height: 8, borderRadius: '50%',
                              background: CONFIDENCE_DOT[est.confidence],
                            }} />
                            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                              {est.confidence}
                            </span>
                          </div>
                        </div>

                        {/* Expanded detail */}
                        {expandedNodes.has(nid) && (
                          <div style={{
                            padding: '8px 12px 8px 32px',
                            background: T.surface2,
                            borderBottom: `1px solid ${T.border}10`,
                          }}>
                            <div style={{
                              display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4,
                              fontFamily: F, fontSize: FS.xxs, color: T.dim,
                            }}>
                              <span>Memory estimate: {formatMemory(est.estimated_memory_mb)}</span>
                              <span>Duration class: {est.estimated_duration_class}</span>
                              <span>Confidence: {confidenceLabel(est.confidence)}</span>
                              <span>Node ID: {nid.slice(0, 16)}...</span>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: '10px 16px',
          borderTop: `1px solid ${T.border}`,
          display: 'flex',
          justifyContent: 'flex-end',
        }}>
          <button
            onClick={onClose}
            style={{
              padding: '6px 16px',
              background: T.surface3,
              border: `1px solid ${T.border}`,
              borderRadius: 4,
              color: T.sec,
              fontFamily: F,
              fontSize: FS.xs,
              cursor: 'pointer',
              letterSpacing: '0.06em',
            }}
          >
            CLOSE
          </button>
        </div>
      </div>
    </div>
  )
}
