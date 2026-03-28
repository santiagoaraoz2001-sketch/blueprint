import { useState, useEffect } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { api } from '@/api/client'
import { ArrowLeft, Database, Brain, BarChart3, ChevronDown, ChevronRight, X, Clock, Fingerprint, Box } from 'lucide-react'

interface TraceabilityPanelProps {
  runId: string
  nodeId: string
  metricName?: string
  onClose: () => void
}

interface TraceNode {
  node_id: string
  block_type: string
  label: string
  category: string
  resolved_config: Record<string, any>
  config_fingerprint: string | null
  duration_seconds: number | null
  cache_decision: string
  is_source: boolean
  data_source?: Record<string, any>
  output_artifacts?: Record<string, any>
  input_lineage?: InputLineage[]
  circular?: boolean
}

interface InputLineage {
  input_port: string
  from_node: string
  from_node_label: string
  from_port: string
  upstream_artifact?: {
    artifact_id: string
    data_type: string
    size_bytes: number
    content_hash: string | null
    serializer: string
  }
  lineage: TraceNode
}

interface TraceData {
  run_id: string
  timestamp: string | null
  metric_source: {
    node_id: string
    block_type: string
    label: string
    output_port: string
  }
  provenance: TraceNode
}

function getCategoryIcon(category: string) {
  switch (category) {
    case 'data':
    case 'external':
      return Database
    case 'model':
    case 'training':
      return Brain
    case 'metrics':
    case 'evaluation':
      return BarChart3
    default:
      return Box
  }
}

function NodeAccordion({ node, depth = 0 }: { node: TraceNode; depth?: number }) {
  const [expanded, setExpanded] = useState(depth < 2)
  const Icon = getCategoryIcon(node.category)

  if (node.circular) {
    return (
      <div style={{ marginLeft: depth * 16, padding: '4px 0', color: T.dim, fontFamily: F, fontSize: FS.xxs }}>
        (circular reference to {node.node_id})
      </div>
    )
  }

  return (
    <div style={{ marginLeft: depth > 0 ? 12 : 0 }}>
      {/* Node header */}
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          width: '100%',
          padding: '6px 8px',
          background: expanded ? `${T.cyan}08` : 'transparent',
          border: `1px solid ${expanded ? T.cyan + '22' : T.border}`,
          borderRadius: 4,
          cursor: 'pointer',
          marginBottom: 4,
        }}
      >
        {expanded ? <ChevronDown size={12} color={T.dim} /> : <ChevronRight size={12} color={T.dim} />}
        <Icon size={13} color={node.is_source ? T.green : T.cyan} />
        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.text, fontWeight: 600 }}>
          {node.label}
        </span>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          {node.block_type}
        </span>
        {node.cache_decision === 'cache_hit' && (
          <span style={{
            fontFamily: F, fontSize: 9, color: T.amber,
            background: `${T.amber}15`, padding: '1px 5px', borderRadius: 3,
          }}>
            CACHED
          </span>
        )}
        {node.is_source && (
          <span style={{
            fontFamily: F, fontSize: 9, color: T.green,
            background: `${T.green}15`, padding: '1px 5px', borderRadius: 3,
          }}>
            SOURCE
          </span>
        )}
      </button>

      {/* Expanded details */}
      {expanded && (
        <div style={{ paddingLeft: 20, paddingBottom: 8 }}>
          {/* Duration + cache */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 6, flexWrap: 'wrap' }}>
            {node.duration_seconds != null && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <Clock size={10} color={T.dim} />
                <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
                  {node.duration_seconds.toFixed(2)}s
                </span>
              </div>
            )}
            {node.config_fingerprint && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <Fingerprint size={10} color={T.dim} />
                <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                  {node.config_fingerprint.slice(0, 12)}
                </span>
              </div>
            )}
          </div>

          {/* Resolved config */}
          {Object.keys(node.resolved_config).length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontFamily: F, fontSize: 9, color: T.dim, letterSpacing: '0.1em', marginBottom: 3 }}>
                RESOLVED CONFIG
              </div>
              <div style={{
                background: T.surface2, border: `1px solid ${T.border}`, borderRadius: 3,
                padding: '4px 8px', maxHeight: 120, overflow: 'auto',
              }}>
                {Object.entries(node.resolved_config).slice(0, 10).map(([k, v]) => (
                  <div key={k} style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec, lineHeight: 1.6 }}>
                    <span style={{ color: T.dim }}>{k}:</span>{' '}
                    <span style={{ color: v === '[REDACTED]' ? T.red : T.text }}>
                      {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Data source info */}
          {node.data_source && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontFamily: F, fontSize: 9, color: T.dim, letterSpacing: '0.1em', marginBottom: 3 }}>
                DATA SOURCE
              </div>
              <div style={{
                background: `${T.green}08`, border: `1px solid ${T.green}22`, borderRadius: 3,
                padding: '4px 8px',
              }}>
                {Object.entries(node.data_source).map(([k, v]) => (
                  <div key={k} style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
                    <span style={{ color: T.green }}>{k}:</span> {String(v)}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Output artifacts */}
          {node.output_artifacts && Object.keys(node.output_artifacts).length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontFamily: F, fontSize: 9, color: T.dim, letterSpacing: '0.1em', marginBottom: 3 }}>
                OUTPUT ARTIFACTS
              </div>
              {Object.entries(node.output_artifacts).map(([port, art]: [string, any]) => (
                <div key={port} style={{
                  fontFamily: F, fontSize: FS.xxs, color: T.sec,
                  display: 'flex', gap: 8, padding: '2px 0',
                }}>
                  <span style={{ color: T.cyan }}>{port}</span>
                  <span>{art.data_type}</span>
                  <span style={{ color: T.dim }}>{(art.size_bytes / 1024).toFixed(1)}KB</span>
                  {art.content_hash && (
                    <span style={{ color: T.dim, fontFamily: 'monospace', fontSize: 10 }}>
                      #{art.content_hash}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Input lineage */}
          {node.input_lineage && node.input_lineage.length > 0 && (
            <div>
              <div style={{ fontFamily: F, fontSize: 9, color: T.dim, letterSpacing: '0.1em', marginBottom: 3 }}>
                INPUT LINEAGE
              </div>
              {node.input_lineage.map((input, i) => (
                <div key={i} style={{ marginBottom: 6 }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 4,
                    fontFamily: F, fontSize: FS.xxs, color: T.sec, marginBottom: 2,
                  }}>
                    <ArrowLeft size={10} color={T.cyan} />
                    <span style={{ color: T.dim }}>{input.input_port}</span>
                    <span>from</span>
                    <span style={{ color: T.text, fontWeight: 600 }}>{input.from_node_label}</span>
                    <span style={{ color: T.dim }}>:{input.from_port}</span>
                  </div>
                  {input.upstream_artifact && (
                    <div style={{
                      fontFamily: F, fontSize: 10, color: T.dim, paddingLeft: 14,
                      display: 'flex', gap: 6,
                    }}>
                      <span>{input.upstream_artifact.data_type}</span>
                      <span>{(input.upstream_artifact.size_bytes / 1024).toFixed(1)}KB</span>
                      {input.upstream_artifact.content_hash && (
                        <span style={{ fontFamily: 'monospace' }}>
                          #{input.upstream_artifact.content_hash}
                        </span>
                      )}
                    </div>
                  )}
                  <NodeAccordion node={input.lineage} depth={depth + 1} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function TraceabilityPanel({ runId, nodeId, metricName, onClose }: TraceabilityPanelProps) {
  const [trace, setTrace] = useState<TraceData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    api
      .get<TraceData>(`/runs/${runId}/traceability/${nodeId}`)
      .then(setTrace)
      .catch((e) => setError(e.message || 'Failed to load traceability'))
      .finally(() => setLoading(false))
  }, [runId, nodeId])

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        right: 0,
        width: 400,
        height: '100vh',
        background: T.bg,
        borderLeft: `1px solid ${T.border}`,
        zIndex: 1000,
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '0 0 40px rgba(0,0,0,0.5)',
      }}
    >
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '12px 16px', borderBottom: `1px solid ${T.border}`,
        flexShrink: 0,
      }}>
        <BarChart3 size={14} color={T.cyan} />
        <span style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 700, flex: 1 }}>
          Traceability
        </span>
        {metricName && (
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.cyan }}>
            {metricName}
          </span>
        )}
        <button
          onClick={onClose}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            padding: 4, display: 'flex',
          }}
        >
          <X size={14} color={T.dim} />
        </button>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto', padding: '12px 16px' }}>
        {loading && (
          <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, textAlign: 'center', padding: 20 }}>
            Loading provenance chain...
          </div>
        )}

        {error && (
          <div style={{ fontFamily: F, fontSize: FS.xs, color: T.red, textAlign: 'center', padding: 20 }}>
            {error}
          </div>
        )}

        {trace && (
          <div>
            {/* Metric source header */}
            <div style={{
              background: `${T.cyan}08`, border: `1px solid ${T.cyan}22`,
              borderRadius: 4, padding: '8px 12px', marginBottom: 12,
            }}>
              <div style={{ fontFamily: F, fontSize: 9, color: T.dim, letterSpacing: '0.1em', marginBottom: 4 }}>
                METRIC SOURCE
              </div>
              <div style={{ fontFamily: F, fontSize: FS.xs, color: T.text }}>
                <span style={{ fontWeight: 600 }}>{trace.metric_source.label}</span>
                <span style={{ color: T.dim }}> ({trace.metric_source.block_type})</span>
              </div>
              <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                Run: {trace.run_id.slice(0, 8)} | Port: {trace.metric_source.output_port}
                {trace.timestamp && ` | ${new Date(trace.timestamp).toLocaleString()}`}
              </div>
            </div>

            {/* Provenance tree */}
            <div style={{ fontFamily: F, fontSize: 9, color: T.dim, letterSpacing: '0.1em', marginBottom: 6 }}>
              PROVENANCE CHAIN
            </div>
            <NodeAccordion node={trace.provenance} />
          </div>
        )}
      </div>
    </div>
  )
}
