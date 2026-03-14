import { useState, useMemo, useEffect } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore } from '@/stores/metricsStore'
import { api } from '@/api/client'
import { CheckCircle, Loader, TrendingUp, Minus } from 'lucide-react'

// ── Types ───────────────────────────────────────────────────────────────

interface BranchStats {
  n: number
  mean: number
  std: number
}

interface SignificanceReportData {
  metric: string
  test_type: string
  alpha: number
  branch_a: BranchStats
  branch_b: BranchStats
  test_statistic: number | null
  p_value: number
  cohens_d: number
  effect_size: string
  significant: boolean
  confidence_interval_95: [number, number]
  verdict: string
}

interface SignificanceDashboardProps {
  runId: string
  blockId: string
}

// ── Constants ───────────────────────────────────────────────────────────

const TEST_TYPE_LABELS: Record<string, string> = {
  welch_t: "Welch's t-test",
  mann_whitney: 'Mann-Whitney U',
  bootstrap: 'Bootstrap permutation',
}

// ── Color helpers ───────────────────────────────────────────────────────

function pColor(p: number, alpha: number): string {
  return p < alpha ? T.green : T.dim
}

function effectColor(label: string): string {
  if (label === 'large') return T.green
  if (label === 'medium') return T.amber
  if (label === 'small') return T.orange
  return T.dim
}

function effectWidth(d: number): number {
  // Map |d| to 0-100 width, capped at 2.0
  return Math.min(100, (Math.abs(d) / 2.0) * 100)
}

function safeFixed(val: number | null | undefined, decimals: number): string {
  if (val === null || val === undefined || typeof val !== 'number' || !isFinite(val)) return '--'
  return val.toFixed(decimals)
}

// ── Dashboard ───────────────────────────────────────────────────────────

export default function SignificanceDashboard({ runId, blockId }: SignificanceDashboardProps) {
  const blockMetrics = useMetricsStore((s) => s.runs[runId]?.blocks[blockId]?.metrics)
  const blockStatus = useMetricsStore((s) => s.runs[runId]?.blocks[blockId]?.status)
  const blockLabel = useMetricsStore((s) => s.runs[runId]?.blocks[blockId]?.label)

  const [report, setReport] = useState<SignificanceReportData | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  // Extract live metrics
  const liveMetrics = useMemo(() => {
    if (!blockMetrics) return null
    const latest = (key: string) => {
      const series = blockMetrics[key]
      return series?.length ? series[series.length - 1].value : null
    }
    return {
      p_value: latest('p_value'),
      cohens_d: latest('cohens_d'),
      significant: latest('significant'),
      mean_diff: latest('mean_diff'),
    }
  }, [blockMetrics])

  // Fetch full report once the block completes
  useEffect(() => {
    if (blockStatus !== 'complete') return
    let cancelled = false

    api.get<{ outputs: Record<string, any> }>(`/runs/${runId}/outputs`)
      .then((data) => {
        if (cancelled) return
        const reportPath = data?.outputs?.report
        if (!reportPath) return

        if (typeof reportPath === 'object' && reportPath.p_value !== undefined) {
          setReport(reportPath as SignificanceReportData)
          return
        }

        if (typeof reportPath === 'string') {
          return api.get<SignificanceReportData>(`/files?path=${encodeURIComponent(reportPath)}`)
            .then((r) => { if (!cancelled) setReport(r) })
        }
      })
      .catch((err) => {
        if (!cancelled) setLoadError(String(err))
      })

    return () => { cancelled = true }
  }, [blockStatus, runId, blockId])

  const hasLiveMetrics = liveMetrics && liveMetrics.p_value !== null
  const isRunning = blockStatus === 'running' || blockStatus === 'queued'

  // Waiting state
  if (!hasLiveMetrics && !report) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100%', gap: 8,
      }}>
        <Loader size={14} color={T.dim} style={{ animation: 'spin 1s linear infinite' }} />
        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>
          {isRunning ? 'Computing significance...' : 'Waiting for results...'}
        </span>
      </div>
    )
  }

  // Full report
  if (report) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'auto', padding: '8px 12px' }}>
        <div style={{ fontFamily: F, fontSize: FS.xs, color: T.text, fontWeight: 700, marginBottom: 8 }}>
          A/B Significance — {blockLabel || blockId}
        </div>
        <SignificanceReportView report={report} />
      </div>
    )
  }

  // Live metrics only (still running)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'auto', padding: '8px 12px', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.text, fontWeight: 700 }}>
          A/B Significance — {blockLabel || blockId}
        </span>
        {isRunning && (
          <Loader size={10} color={T.amber} style={{ animation: 'spin 1s linear infinite' }} />
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
        <StatCard
          label="p-value"
          value={liveMetrics?.p_value}
          format="fixed6"
          colorFn={(v) => pColor(v, 0.05)}
        />
        <StatCard
          label="Cohen's d"
          value={liveMetrics?.cohens_d}
          format="fixed4"
          colorFn={() => T.sec}
        />
        <StatCard
          label="Significant"
          value={liveMetrics?.significant}
          format="bool"
          colorFn={(v) => v === 1 ? T.green : T.dim}
        />
      </div>

      {loadError && (
        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.red }}>
          Could not load full report: {loadError}
        </div>
      )}
    </div>
  )
}

// ── Full Report View ────────────────────────────────────────────────────

function SignificanceReportView({ report }: { report: SignificanceReportData }) {
  const { branch_a, branch_b } = report
  const testLabel = TEST_TYPE_LABELS[report.test_type] ?? report.test_type

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Verdict banner */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '8px 12px',
        background: report.significant ? `${T.green}10` : `${T.dim}10`,
        border: `1px solid ${report.significant ? T.green : T.border}`,
        borderRadius: 6,
      }}>
        {report.significant
          ? <CheckCircle size={14} color={T.green} />
          : <Minus size={14} color={T.dim} />}
        <span style={{
          fontFamily: F, fontSize: FS.xs,
          color: report.significant ? T.green : T.sec,
          fontWeight: 600, flex: 1,
        }}>
          {report.verdict}
        </span>
      </div>

      {/* Test metadata */}
      <div style={{
        display: 'flex', gap: 16, flexWrap: 'wrap',
        fontFamily: F, fontSize: FS.xxs, color: T.dim,
      }}>
        <span>Metric: <span style={{ color: T.sec, fontWeight: 600 }}>{report.metric}</span></span>
        <span>Test: <span style={{ color: T.sec, fontWeight: 600 }}>{testLabel}</span></span>
        <span>Alpha: <span style={{ color: T.sec, fontWeight: 600 }}>{report.alpha}</span></span>
        {report.test_statistic !== null && (
          <span>
            Statistic: <span style={{ color: T.sec, fontWeight: 600 }}>
              {safeFixed(report.test_statistic, 4)}
            </span>
          </span>
        )}
      </div>

      {/* Two-column branch stats */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <BranchCard label="Branch A" stats={branch_a} color={T.blue} />
        <BranchCard label="Branch B" stats={branch_b} color={T.purple} />
      </div>

      {/* Key statistics row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
        <StatCard
          label="p-value"
          value={report.p_value}
          format="fixed6"
          colorFn={(v) => pColor(v, report.alpha)}
        />
        <StatCard
          label="Cohen's d"
          value={report.cohens_d}
          format="fixed4"
          colorFn={() => effectColor(report.effect_size)}
        />
        <StatCard
          label="Effect Size"
          value={null}
          format="label"
          labelOverride={report.effect_size.toUpperCase()}
          colorFn={() => effectColor(report.effect_size)}
        />
      </div>

      {/* Cohen's d visual bar */}
      <div>
        <div style={{
          fontFamily: F, fontSize: FS.xxs, color: T.dim,
          fontWeight: 700, letterSpacing: '0.12em',
          textTransform: 'uppercase', marginBottom: 4,
        }}>
          EFFECT SIZE
        </div>
        <div style={{
          background: T.surface1,
          border: `1px solid ${T.border}`,
          borderRadius: 6,
          padding: '8px 12px',
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            marginBottom: 4,
          }}>
            <TrendingUp size={10} color={effectColor(report.effect_size)} />
            <span style={{
              fontFamily: F, fontSize: FS.xxs, color: T.sec,
            }}>
              |d| = {safeFixed(Math.abs(report.cohens_d), 4)}
            </span>
            <span style={{
              fontFamily: F, fontSize: FS.xxs, color: effectColor(report.effect_size),
              fontWeight: 700, marginLeft: 'auto',
            }}>
              {report.effect_size}
            </span>
          </div>
          <div style={{
            height: 8, background: T.surface3,
            borderRadius: 4, overflow: 'hidden',
            position: 'relative',
          }}>
            <div style={{
              height: '100%',
              width: `${effectWidth(report.cohens_d)}%`,
              background: effectColor(report.effect_size),
              borderRadius: 4,
              opacity: 0.8,
            }} />
            {/* Threshold markers */}
            {[0.2, 0.5, 0.8].map((threshold) => (
              <div
                key={threshold}
                style={{
                  position: 'absolute', top: 0, bottom: 0,
                  left: `${(threshold / 2.0) * 100}%`,
                  width: 1, background: T.dim, opacity: 0.3,
                }}
              />
            ))}
          </div>
          <div style={{
            display: 'flex', justifyContent: 'space-between',
            fontFamily: F, fontSize: FS.xxs, color: T.dim,
            marginTop: 2, opacity: 0.6,
          }}>
            <span>0</span>
            <span>small</span>
            <span>medium</span>
            <span>large</span>
            <span>2.0</span>
          </div>
        </div>
      </div>

      {/* Confidence interval */}
      <div>
        <div style={{
          fontFamily: F, fontSize: FS.xxs, color: T.dim,
          fontWeight: 700, letterSpacing: '0.12em',
          textTransform: 'uppercase', marginBottom: 4,
        }}>
          95% CONFIDENCE INTERVAL (MEAN DIFF)
        </div>
        <ConfidenceIntervalBar
          lower={report.confidence_interval_95[0]}
          upper={report.confidence_interval_95[1]}
          mean={branch_a.mean - branch_b.mean}
          significant={report.significant}
        />
      </div>
    </div>
  )
}

// ── Sub-components ──────────────────────────────────────────────────────

function BranchCard({ label, stats, color }: {
  label: string
  stats: BranchStats
  color: string
}) {
  return (
    <div style={{
      background: T.surface1,
      border: `1px solid ${T.border}`,
      borderRadius: 6,
      padding: '8px 12px',
    }}>
      <div style={{
        fontFamily: F, fontSize: FS.xxs, color,
        fontWeight: 700, marginBottom: 6,
      }}>
        {label}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        <StatRow label="n" value={String(stats.n)} />
        <StatRow label="mean" value={safeFixed(stats.mean, 6)} />
        <StatRow label="std" value={safeFixed(stats.std, 6)} />
      </div>
    </div>
  )
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between',
      fontFamily: F, fontSize: FS.xxs,
    }}>
      <span style={{ color: T.dim }}>{label}</span>
      <span style={{ color: T.sec, fontFamily: 'monospace', fontWeight: 600 }}>{value}</span>
    </div>
  )
}

function StatCard({ label, value, format, colorFn, labelOverride }: {
  label: string
  value: number | null | undefined
  format: 'fixed4' | 'fixed6' | 'bool' | 'label'
  colorFn: (v: number) => string
  labelOverride?: string
}) {
  let displayVal: string
  let color: string

  if (format === 'label' && labelOverride) {
    displayVal = labelOverride
    color = colorFn(0)
  } else if (value === null || value === undefined || (typeof value === 'number' && !isFinite(value))) {
    displayVal = '--'
    color = T.dim
  } else if (format === 'bool') {
    displayVal = value === 1 ? 'YES' : 'NO'
    color = colorFn(value)
  } else if (format === 'fixed6') {
    displayVal = safeFixed(value, 6)
    color = colorFn(value)
  } else {
    displayVal = safeFixed(value, 4)
    color = colorFn(value)
  }

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

function ConfidenceIntervalBar({ lower, upper, mean, significant }: {
  lower: number
  upper: number
  mean: number
  significant: boolean
}) {
  // Guard against degenerate values
  const safeLower = isFinite(lower) ? lower : 0
  const safeUpper = isFinite(upper) ? upper : 0
  const safeMean = isFinite(mean) ? mean : 0

  // Determine scale: center around 0, show the CI range with padding
  const absMax = Math.max(Math.abs(safeLower), Math.abs(safeUpper), 0.001) * 1.3
  const toPercent = (v: number) => Math.max(0, Math.min(100, ((v + absMax) / (2 * absMax)) * 100))
  const zeroPos = toPercent(0)
  const lowerPos = toPercent(safeLower)
  const upperPos = toPercent(safeUpper)
  const meanPos = toPercent(safeMean)

  const barColor = significant ? T.green : T.dim
  const crossesZero = safeLower <= 0 && safeUpper >= 0

  return (
    <div style={{
      background: T.surface1,
      border: `1px solid ${T.border}`,
      borderRadius: 6,
      padding: '10px 12px',
    }}>
      <div style={{
        position: 'relative',
        height: 28,
        marginBottom: 4,
      }}>
        {/* Background track */}
        <div style={{
          position: 'absolute', top: 12, left: 0, right: 0,
          height: 4, background: T.surface3, borderRadius: 2,
        }} />

        {/* Zero line */}
        <div style={{
          position: 'absolute', top: 4, height: 20,
          left: `${zeroPos}%`, width: 1,
          background: T.dim, opacity: 0.5,
        }} />

        {/* Zero label */}
        <div style={{
          position: 'absolute', top: -1,
          left: `${zeroPos}%`, transform: 'translateX(-50%)',
          fontFamily: F, fontSize: FS.xxs, color: T.dim, opacity: 0.6,
        }}>
          0
        </div>

        {/* CI bar */}
        <div style={{
          position: 'absolute', top: 11,
          left: `${lowerPos}%`,
          width: `${Math.max(1, upperPos - lowerPos)}%`,
          height: 6, background: barColor,
          borderRadius: 3, opacity: 0.6,
        }} />

        {/* Mean marker */}
        <div style={{
          position: 'absolute', top: 8,
          left: `${meanPos}%`,
          width: 8, height: 12,
          marginLeft: -4,
          background: barColor,
          borderRadius: 2,
        }} />
      </div>

      {/* Labels */}
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        fontFamily: F, fontSize: FS.xxs,
      }}>
        <span style={{ color: T.dim }}>
          [{safeFixed(lower, 6)}, {safeFixed(upper, 6)}]
        </span>
        <span style={{ color: crossesZero ? T.dim : barColor, fontWeight: 600 }}>
          {crossesZero ? 'Crosses zero' : 'Does not cross zero'}
        </span>
      </div>
    </div>
  )
}
