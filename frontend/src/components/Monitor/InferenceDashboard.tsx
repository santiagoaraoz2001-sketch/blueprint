import { useState, useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore } from '@/stores/metricsStore'
import AutoLineChart from './AutoLineChart'
import { Eye, EyeOff } from 'lucide-react'

interface Props { runId: string; blockId: string }

export default function InferenceDashboard({ runId, blockId }: Props) {
  const [showRaw, setShowRaw] = useState(false)
  const block = useMetricsStore((s) => s.runs[runId]?.blocks[blockId])
  if (!block) return null

  const metrics = block.metrics
  const tokensPerSec = metrics['inference/tokens_per_sec'] || metrics['tokens_per_sec'] || []
  const latency = metrics['inference/latency'] || metrics['latency'] || []

  const latencyStats = useMemo(() => {
    if (latency.length === 0) return null
    const values = latency.map((p) => p.value).sort((a, b) => a - b)
    const percentile = (p: number) => values[Math.floor(values.length * p / 100)] ?? 0
    return {
      min: values[0],
      max: values[values.length - 1],
      p50: percentile(50),
      p95: percentile(95),
      p99: percentile(99),
    }
  }, [latency])

  const allEvents = Object.entries(metrics).flatMap(([name, points]) =>
    points.map((p) => ({ name, ...p }))
  ).sort((a, b) => a.timestamp - b.timestamp)

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <span style={{ fontFamily: F, fontSize: FS.md, color: T.text, fontWeight: 700 }}>
          Inference Dashboard
        </span>
        <button
          onClick={() => setShowRaw(!showRaw)}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '3px 8px', background: showRaw ? `${T.cyan}14` : 'transparent',
            border: `1px solid ${showRaw ? T.cyan : T.border}`, color: showRaw ? T.cyan : T.dim,
            fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
          }}
        >
          {showRaw ? <EyeOff size={10} /> : <Eye size={10} />}
          {showRaw ? 'HIDE RAW' : 'RAW DATA'}
        </button>
      </div>

      {showRaw ? (
        <div style={{ overflow: 'auto', maxHeight: 500 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: F, fontSize: FS.xxs }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                <th style={{ padding: '4px 8px', textAlign: 'left', color: T.dim }}>Step</th>
                <th style={{ padding: '4px 8px', textAlign: 'left', color: T.dim }}>Metric</th>
                <th style={{ padding: '4px 8px', textAlign: 'right', color: T.dim }}>Value</th>
                <th style={{ padding: '4px 8px', textAlign: 'right', color: T.dim }}>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {allEvents.map((e, i) => (
                <tr key={i} style={{ borderBottom: `1px solid ${T.surface4}` }}>
                  <td style={{ padding: '3px 8px', color: T.sec }}>{e.step ?? '—'}</td>
                  <td style={{ padding: '3px 8px', color: T.text }}>{e.name}</td>
                  <td style={{ padding: '3px 8px', color: T.cyan, textAlign: 'right' }}>{e.value.toFixed(6)}</td>
                  <td style={{ padding: '3px 8px', color: T.dim, textAlign: 'right' }}>{new Date(e.timestamp).toLocaleTimeString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <>
          {tokensPerSec.length > 0 && (
            <AutoLineChart data={tokensPerSec} color={T.cyan} height={250} label="Tokens/sec" />
          )}

          {latencyStats && (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontFamily: F, fontSize: FS.xs, color: T.sec, marginBottom: 6, fontWeight: 600 }}>
                LATENCY DISTRIBUTION
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: F, fontSize: FS.xxs }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                    {['Min', 'P50', 'P95', 'P99', 'Max'].map((h) => (
                      <th key={h} style={{ padding: '4px 8px', textAlign: 'right', color: T.dim }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td style={{ padding: '3px 8px', color: T.green, textAlign: 'right' }}>{latencyStats.min.toFixed(2)}ms</td>
                    <td style={{ padding: '3px 8px', color: T.text, textAlign: 'right' }}>{latencyStats.p50.toFixed(2)}ms</td>
                    <td style={{ padding: '3px 8px', color: T.amber, textAlign: 'right' }}>{latencyStats.p95.toFixed(2)}ms</td>
                    <td style={{ padding: '3px 8px', color: T.orange, textAlign: 'right' }}>{latencyStats.p99.toFixed(2)}ms</td>
                    <td style={{ padding: '3px 8px', color: T.red, textAlign: 'right' }}>{latencyStats.max.toFixed(2)}ms</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}

          {latency.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <AutoLineChart data={latency} color={T.amber} height={200} label="Latency (ms)" />
            </div>
          )}

          {tokensPerSec.length === 0 && latency.length === 0 && (
            <div style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, textAlign: 'center', padding: 40, animation: 'pulse 2s ease-in-out infinite' }}>
              Waiting for inference metrics...
            </div>
          )}
        </>
      )}
    </div>
  )
}
