import { useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore } from '@/stores/metricsStore'
import AutoLineChart from './AutoLineChart'
import { Eye, EyeOff } from 'lucide-react'

interface Props { runId: string; blockId: string }

export default function TrainingDashboard({ runId, blockId }: Props) {
  const [showRaw, setShowRaw] = useState(false)
  const block = useMetricsStore((s) => s.runs[runId]?.blocks[blockId])
  if (!block) return null

  const metrics = block.metrics
  const trainLoss = metrics['train/loss'] || []
  const evalLoss = metrics['eval/loss'] || []
  const gradNorm = metrics['train/grad_norm'] || []
  const lr = metrics['train/lr'] || []

  // Collect all raw events for the raw data view
  const allEvents = Object.entries(metrics).flatMap(([name, points]) =>
    points.map((p) => ({ name, ...p }))
  ).sort((a, b) => a.timestamp - b.timestamp)

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <span style={{ fontFamily: F, fontSize: FS.md, color: T.text, fontWeight: 700 }}>
          Training Dashboard
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
                  <td style={{ padding: '3px 8px', color: T.cyan, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                    {e.value.toFixed(6)}
                  </td>
                  <td style={{ padding: '3px 8px', color: T.dim, textAlign: 'right' }}>
                    {new Date(e.timestamp).toLocaleTimeString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <>
          {/* Loss chart */}
          <AutoLineChart
            data={trainLoss}
            color="#00BFA5"
            height={300}
            label="Loss"
            overlay={evalLoss.length > 0 ? { data: evalLoss, color: '#F59E0B', label: 'Eval Loss' } : undefined}
          />

          {/* Gradient norm */}
          {gradNorm.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <AutoLineChart data={gradNorm} color={T.purple} height={150} label="Grad Norm" />
            </div>
          )}

          {/* Learning rate */}
          {lr.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <AutoLineChart data={lr} color={T.blue} height={120} label="Learning Rate" />
            </div>
          )}
        </>
      )}
    </div>
  )
}
