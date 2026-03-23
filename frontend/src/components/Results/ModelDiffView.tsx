import { useState, useMemo, useEffect } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore } from '@/stores/metricsStore'
import { api } from '@/api/client'
import { BarChart3, CheckCircle, XCircle, Loader } from 'lucide-react'

// ── Types ───────────────────────────────────────────────────────────────

interface TokenDiff {
  position: number
  model_a_top5: [string, number][]
  model_b_top5: [string, number][]
  kl_div: number
  top1_match: boolean
}

interface LayerSim {
  layer: number
  cosine_similarity: number
}

interface DiffReport {
  prompt: string
  model_a: string
  model_b: string
  tokens: TokenDiff[]
  overall_kl_divergence: number
  top1_agreement_rate: number
  cosine_similarity_mean: number
  layer_similarities?: LayerSim[]
  comparison_mode?: string
  model_a_response?: string
  model_b_response?: string
}

interface ModelDiffDashboardProps {
  runId: string
  blockId: string
}

// ── Color helpers ───────────────────────────────────────────────────────

function klColor(kl: number): string {
  if (kl < 0.05) return T.green
  if (kl < 0.3) return T.amber
  return T.red
}

function klBg(kl: number): string {
  if (kl < 0.05) return `${T.green}10`
  if (kl < 0.3) return `${T.amber}10`
  return `${T.red}10`
}

function simColor(sim: number): string {
  if (sim > 0.95) return T.green
  if (sim > 0.8) return T.amber
  return T.red
}

// ── Dashboard (live metrics + full report after completion) ─────────────

export default function ModelDiffDashboard({ runId, blockId }: ModelDiffDashboardProps) {
  const blockMetrics = useMetricsStore((s) => s.runs[runId]?.blocks[blockId]?.metrics)
  const blockStatus = useMetricsStore((s) => s.runs[runId]?.blocks[blockId]?.status)
  const blockLabel = useMetricsStore((s) => s.runs[runId]?.blocks[blockId]?.label)

  const [report, setReport] = useState<DiffReport | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  // Extract live metrics from the store
  const liveMetrics = useMemo(() => {
    if (!blockMetrics) return null
    const latest = (key: string) => {
      const series = blockMetrics[key]
      return series?.length ? series[series.length - 1].value : null
    }
    return {
      kl_divergence: latest('kl_divergence'),
      cosine_similarity: latest('cosine_similarity'),
      top1_agreement_rate: latest('top1_agreement_rate'),
      num_positions: latest('num_positions'),
    }
  }, [blockMetrics])

  // Fetch full diff report once the block completes
  useEffect(() => {
    if (blockStatus !== 'complete') return
    let cancelled = false

    api.get<{ outputs: Record<string, any> }>(`/runs/${runId}/outputs`)
      .then((data) => {
        if (cancelled) return
        const reportPath = data?.outputs?.diff_report
        if (!reportPath) return

        // If outputs contain the report inline
        if (typeof reportPath === 'object' && reportPath.tokens) {
          setReport(reportPath as DiffReport)
          return
        }

        // Fetch the report file from the backend
        if (typeof reportPath === 'string') {
          return api.get<DiffReport>(`/files?path=${encodeURIComponent(reportPath)}`)
            .then((r) => { if (!cancelled) setReport(r) })
        }
      })
      .catch((err) => {
        if (!cancelled) setLoadError(String(err))
      })

    return () => { cancelled = true }
  }, [blockStatus, runId])

  const hasLiveMetrics = liveMetrics && (
    liveMetrics.kl_divergence !== null ||
    liveMetrics.cosine_similarity !== null
  )
  const isRunning = blockStatus === 'running' || blockStatus === 'queued'

  // No data yet — waiting state
  if (!hasLiveMetrics && !report) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100%', gap: 8,
      }}>
        <Loader size={14} color={T.dim} style={{ animation: 'spin 1s linear infinite' }} />
        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>
          {isRunning ? 'Running model comparison...' : 'Waiting for diff results...'}
        </span>
      </div>
    )
  }

  // Full report available — render detailed view
  if (report) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'auto', padding: '8px 12px' }}>
        <div style={{ fontFamily: F, fontSize: FS.xs, color: T.text, fontWeight: 700, marginBottom: 8 }}>
          Model Diff — {blockLabel || blockId}
        </div>
        <ModelDiffReport report={report} />
      </div>
    )
  }

  // Live metrics only (still running or report not yet fetched)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'auto', padding: '8px 12px', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.text, fontWeight: 700 }}>
          Model Diff — {blockLabel || blockId}
        </span>
        {isRunning && (
          <Loader size={10} color={T.amber} style={{ animation: 'spin 1s linear infinite' }} />
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
        <StatCard
          label="KL Divergence"
          value={liveMetrics?.kl_divergence}
          colorFn={klColor}
        />
        <StatCard
          label="Top-1 Agreement"
          value={liveMetrics?.top1_agreement_rate}
          colorFn={simColor}
          format="percent"
        />
        <StatCard
          label="Cosine Similarity"
          value={liveMetrics?.cosine_similarity}
          colorFn={simColor}
        />
      </div>

      {liveMetrics?.num_positions !== null && (
        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          {liveMetrics?.num_positions} token positions compared
        </div>
      )}

      {loadError && (
        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.red }}>
          Could not load full report: {loadError}
        </div>
      )}
    </div>
  )
}

// ── Full Report Visualization ───────────────────────────────────────────

function ModelDiffReport({ report }: { report: DiffReport }) {
  const [selectedPos, setSelectedPos] = useState<number | null>(null)

  const selectedToken = useMemo(() => {
    if (selectedPos === null) return null
    return report.tokens.find((t) => t.position === selectedPos) ?? null
  }, [selectedPos, report.tokens])

  const thStyle: React.CSSProperties = {
    fontFamily: F,
    fontSize: FS.xxs,
    color: T.dim,
    fontWeight: 700,
    letterSpacing: '0.1em',
    textTransform: 'uppercase',
    textAlign: 'left',
    padding: '4px 8px',
    borderBottom: `1px solid ${T.border}`,
    background: T.surface2,
    position: 'sticky',
    top: 0,
    zIndex: 1,
  }

  const tdStyle: React.CSSProperties = {
    fontFamily: F,
    fontSize: FS.xs,
    color: T.sec,
    padding: '5px 8px',
    borderBottom: `1px solid ${T.border}`,
  }

  return (
    <div>
      {/* Summary Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 12 }}>
        <StatCard label="KL Divergence" value={report.overall_kl_divergence} colorFn={klColor} />
        <StatCard label="Top-1 Agreement" value={report.top1_agreement_rate} colorFn={simColor} format="percent" />
        <StatCard label="Cosine Similarity" value={report.cosine_similarity_mean} colorFn={simColor} />
      </div>

      {/* Model Names */}
      <div style={{
        display: 'flex', gap: 16, marginBottom: 10,
        fontFamily: F, fontSize: FS.xxs, color: T.dim,
      }}>
        <span>Model A: <span style={{ color: T.blue, fontWeight: 600 }}>{report.model_a}</span></span>
        <span>Model B: <span style={{ color: T.purple, fontWeight: 600 }}>{report.model_b}</span></span>
        {report.comparison_mode && (
          <span style={{ marginLeft: 'auto', opacity: 0.7 }}>
            Mode: {report.comparison_mode}
          </span>
        )}
      </div>

      {/* Empty state */}
      {report.tokens.length === 0 ? (
        <div style={{ padding: 24, textAlign: 'center', fontFamily: F, fontSize: FS.xs, color: T.dim }}>
          No token positions to compare — models may have generated empty responses.
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 16 }}>
          {/* Token-by-Token Comparison Table */}
          <div style={{ flex: 1, overflow: 'auto', maxHeight: 480 }}>
            <div style={{
              fontFamily: F, fontSize: FS.xxs, color: T.dim,
              fontWeight: 700, letterSpacing: '0.12em',
              textTransform: 'uppercase', marginBottom: 6,
            }}>
              TOKEN COMPARISON ({report.tokens.length} positions)
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={thStyle}>Pos</th>
                  <th style={thStyle}>Model A</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Prob</th>
                  <th style={thStyle}>Model B</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Prob</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>KL Div</th>
                  <th style={{ ...thStyle, textAlign: 'center' }}>Match</th>
                </tr>
              </thead>
              <tbody>
                {report.tokens.map((tok) => {
                  const aTop = tok.model_a_top5?.[0]
                  const bTop = tok.model_b_top5?.[0]
                  const isSelected = selectedPos === tok.position

                  return (
                    <tr
                      key={tok.position}
                      onClick={() => setSelectedPos(tok.position === selectedPos ? null : tok.position)}
                      style={{
                        cursor: 'pointer',
                        background: isSelected ? `${T.cyan}12` : 'transparent',
                      }}
                    >
                      <td style={{ ...tdStyle, color: T.dim, fontWeight: 600 }}>
                        {tok.position}
                      </td>
                      <td style={{
                        ...tdStyle, fontWeight: 600,
                        color: T.blue, fontFamily: 'monospace',
                        maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {aTop ? aTop[0] || '""' : '-'}
                      </td>
                      <td style={{
                        ...tdStyle, textAlign: 'right',
                        fontFamily: 'monospace', fontSize: FS.xxs,
                      }}>
                        {aTop ? safeFixed(aTop[1], 3) : '-'}
                      </td>
                      <td style={{
                        ...tdStyle, fontWeight: 600,
                        color: T.purple, fontFamily: 'monospace',
                        maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {bTop ? bTop[0] || '""' : '-'}
                      </td>
                      <td style={{
                        ...tdStyle, textAlign: 'right',
                        fontFamily: 'monospace', fontSize: FS.xxs,
                      }}>
                        {bTop ? safeFixed(bTop[1], 3) : '-'}
                      </td>
                      <td style={{
                        ...tdStyle, textAlign: 'right',
                        fontFamily: 'monospace', fontWeight: 700,
                        color: klColor(tok.kl_div ?? 0),
                        background: klBg(tok.kl_div ?? 0),
                      }}>
                        {safeFixed(tok.kl_div, 4)}
                      </td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>
                        {tok.top1_match
                          ? <CheckCircle size={10} color={T.green} />
                          : <XCircle size={10} color={T.red} />}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Right panel: Distribution + Layer similarities */}
          <div style={{ width: 280, flexShrink: 0 }}>
            {/* Distribution Bar Chart (selected position) */}
            <div style={{
              fontFamily: F, fontSize: FS.xxs, color: T.dim,
              fontWeight: 700, letterSpacing: '0.12em',
              textTransform: 'uppercase', marginBottom: 6,
            }}>
              {selectedToken
                ? `DISTRIBUTION — POSITION ${selectedToken.position}`
                : 'SELECT A TOKEN'}
            </div>

            {selectedToken ? (
              <div style={{
                background: T.surface1,
                border: `1px solid ${T.border}`,
                borderRadius: 6,
                padding: 12,
              }}>
                {selectedToken.model_a_top5?.length > 0 && (
                  <DistributionBars label="Model A" color={T.blue} items={selectedToken.model_a_top5} />
                )}
                {selectedToken.model_a_top5?.length > 0 && selectedToken.model_b_top5?.length > 0 && (
                  <div style={{ height: 12 }} />
                )}
                {selectedToken.model_b_top5?.length > 0 && (
                  <DistributionBars label="Model B" color={T.purple} items={selectedToken.model_b_top5} />
                )}
                <div style={{
                  marginTop: 10, paddingTop: 8,
                  borderTop: `1px solid ${T.border}`,
                  fontFamily: F, fontSize: FS.xxs, color: T.dim,
                  display: 'flex', justifyContent: 'space-between',
                }}>
                  <span>KL: <span style={{ color: klColor(selectedToken.kl_div ?? 0), fontWeight: 700 }}>
                    {safeFixed(selectedToken.kl_div, 4)}
                  </span></span>
                  <span>{selectedToken.top1_match ? 'Match' : 'Divergent'}</span>
                </div>
              </div>
            ) : (
              <div style={{
                background: T.surface1,
                border: `1px solid ${T.border}`,
                borderRadius: 6,
                padding: 24,
                textAlign: 'center',
              }}>
                <BarChart3 size={20} color={T.dim} style={{ marginBottom: 8 }} />
                <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>
                  Click a row to see probability distributions
                </div>
              </div>
            )}

            {/* Layer similarities (if available) */}
            {report.layer_similarities && report.layer_similarities.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div style={{
                  fontFamily: F, fontSize: FS.xxs, color: T.dim,
                  fontWeight: 700, letterSpacing: '0.12em',
                  textTransform: 'uppercase', marginBottom: 6,
                }}>
                  LAYER SIMILARITIES ({report.layer_similarities.length} layers)
                </div>
                <div style={{
                  background: T.surface1,
                  border: `1px solid ${T.border}`,
                  borderRadius: 6,
                  padding: 8,
                  maxHeight: 200,
                  overflow: 'auto',
                }}>
                  {report.layer_similarities.map((ls) => (
                    <div
                      key={ls.layer}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        padding: '3px 4px',
                      }}
                    >
                      <span style={{
                        fontFamily: F, fontSize: FS.xxs, color: T.dim,
                        width: 40, flexShrink: 0,
                      }}>
                        L{ls.layer}
                      </span>
                      <div style={{
                        flex: 1, height: 6,
                        background: T.surface3, borderRadius: 3,
                        overflow: 'hidden',
                      }}>
                        <div style={{
                          height: '100%',
                          width: `${Math.max(0, Math.min(100, (ls.cosine_similarity ?? 0) * 100))}%`,
                          background: simColor(ls.cosine_similarity ?? 0),
                          borderRadius: 3,
                        }} />
                      </div>
                      <span style={{
                        fontFamily: 'monospace', fontSize: FS.xxs,
                        color: simColor(ls.cosine_similarity ?? 0),
                        fontWeight: 600, width: 36, textAlign: 'right',
                      }}>
                        {safeFixed(ls.cosine_similarity, 3)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Full text responses for text-based comparison */}
            {report.comparison_mode === 'text_based' && (report.model_a_response || report.model_b_response) && (
              <div style={{ marginTop: 16 }}>
                <div style={{
                  fontFamily: F, fontSize: FS.xxs, color: T.dim,
                  fontWeight: 700, letterSpacing: '0.12em',
                  textTransform: 'uppercase', marginBottom: 6,
                }}>
                  FULL RESPONSES
                </div>
                {report.model_a_response && (
                  <div style={{
                    background: T.surface1, border: `1px solid ${T.border}`,
                    borderRadius: 6, padding: 8, marginBottom: 6,
                  }}>
                    <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.blue, fontWeight: 700, marginBottom: 4 }}>
                      Model A
                    </div>
                    <div style={{
                      fontFamily: F, fontSize: FS.xxs, color: T.sec,
                      whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 80, overflow: 'auto',
                    }}>
                      {report.model_a_response}
                    </div>
                  </div>
                )}
                {report.model_b_response && (
                  <div style={{
                    background: T.surface1, border: `1px solid ${T.border}`,
                    borderRadius: 6, padding: 8,
                  }}>
                    <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.purple, fontWeight: 700, marginBottom: 4 }}>
                      Model B
                    </div>
                    <div style={{
                      fontFamily: F, fontSize: FS.xxs, color: T.sec,
                      whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 80, overflow: 'auto',
                    }}>
                      {report.model_b_response}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Sub-components ──────────────────────────────────────────────────────

function StatCard({ label, value, colorFn, format }: {
  label: string
  value: number | null | undefined
  colorFn: (v: number) => string
  format?: 'percent'
}) {
  const numVal = typeof value === 'number' ? value : null
  const displayVal = numVal !== null
    ? (format === 'percent' ? `${(numVal * 100).toFixed(1)}%` : numVal.toFixed(4))
    : '--'
  const color = numVal !== null ? colorFn(numVal) : T.dim

  return (
    <div style={{
      background: T.surface1,
      border: `1px solid ${T.border}`,
      borderRadius: 6,
      padding: '8px 12px',
    }}>
      <div style={{
        fontFamily: F, fontSize: FS.xxs, color: T.dim,
        fontWeight: 600, letterSpacing: '0.08em',
        textTransform: 'uppercase', marginBottom: 3,
      }}>
        {label}
      </div>
      <div style={{
        fontFamily: 'monospace', fontSize: FS.lg,
        color, fontWeight: 700,
      }}>
        {displayVal}
      </div>
    </div>
  )
}

function DistributionBars({ label, color, items }: {
  label: string
  color: string
  items: [string, number][]
}) {
  if (!items || items.length === 0) return null
  const probs = items.map(([, p]) => (typeof p === 'number' ? p : 0))
  const maxProb = Math.max(...probs, 0.01)

  return (
    <div>
      <div style={{
        fontFamily: F, fontSize: FS.xxs, color,
        fontWeight: 700, marginBottom: 4,
      }}>
        {label}
      </div>
      {items.map(([token, prob], i) => {
        const safePr = typeof prob === 'number' ? prob : 0
        return (
          <div key={i} style={{
            display: 'flex', alignItems: 'center', gap: 4,
            marginBottom: 3,
          }}>
            <span style={{
              fontFamily: 'monospace', fontSize: FS.xxs,
              color: T.sec, width: 50, overflow: 'hidden',
              textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              flexShrink: 0,
            }}>
              {token || '""'}
            </span>
            <div style={{
              flex: 1, height: 8,
              background: T.surface3, borderRadius: 2,
              overflow: 'hidden',
            }}>
              <div style={{
                height: '100%',
                width: `${Math.min(100, (safePr / maxProb) * 100)}%`,
                background: color,
                borderRadius: 2,
                opacity: 0.7,
              }} />
            </div>
            <span style={{
              fontFamily: 'monospace', fontSize: FS.xxs,
              color: T.dim, width: 32, textAlign: 'right',
              flexShrink: 0,
            }}>
              {safePr.toFixed(2)}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ── Helpers ─────────────────────────────────────────────────────────────

function safeFixed(val: number | null | undefined, decimals: number): string {
  if (val === null || val === undefined || typeof val !== 'number' || !isFinite(val)) return '--'
  return val.toFixed(decimals)
}
