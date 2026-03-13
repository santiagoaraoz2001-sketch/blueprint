import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore } from '@/stores/metricsStore'
import { FileText } from 'lucide-react'
import { useUIStore } from '@/stores/uiStore'
import { LineChart, Line, ResponsiveContainer } from 'recharts'

interface Props {
  runId: string | null
  paperId: string | null
  elapsed: number
  formatElapsed: (s: number) => string
}

/** SVG circular gauge */
function CircularGauge({ value, label, unit, size = 64 }: {
  value: number; label: string; unit?: string; size?: number
}) {
  const radius = (size - 8) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - Math.min(1, value / 100))
  const gaugeColor = value < 60 ? T.green : value < 80 ? T.amber : T.red

  return (
    <div style={{ textAlign: 'center' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Background circle */}
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke={T.surface3} strokeWidth={3}
        />
        {/* Value arc */}
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke={gaugeColor} strokeWidth={3}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: 'stroke-dashoffset 0.5s ease, stroke 0.3s ease' }}
        />
        {/* Center text */}
        <text
          x={size / 2} y={size / 2}
          textAnchor="middle" dominantBaseline="central"
          fill={T.text}
          style={{ fontFamily: F, fontSize: 11, fontWeight: 700 }}
        >
          {Math.round(value)}%
        </text>
      </svg>
      <div style={{
        fontFamily: F, fontSize: FS.xxs, color: T.dim,
        letterSpacing: '0.06em', marginTop: 2,
      }}>
        {label}
        {unit && <span style={{ color: T.dim }}> ({unit})</span>}
      </div>
    </div>
  )
}

/** Mini sparkline for system history */
function SystemSparkline({ data, color }: { data: number[]; color: string }) {
  if (data.length < 2) return null
  const chartData = data.map((v, i) => ({ i, v }))
  return (
    <div style={{ width: '100%', height: 20, marginTop: 2 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <Line type="monotone" dataKey="v" stroke={color} strokeWidth={1} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function SystemPanel({ runId, paperId, elapsed, formatElapsed }: Props) {
  const system = useMetricsStore((s) => s.system)
  const systemHistory = useMetricsStore((s) => s.systemHistory)
  const executionOrder = useMetricsStore((s) => s.monitorExecutionOrder)
  const eta = useMetricsStore((s) => s.monitorEta)
  const runStatus = useMetricsStore((s) => s.runStatus)
  const pipelineId = useMetricsStore((s) => s.pipelineId)
  const setView = useUIStore((s) => s.setView)

  const completedBlocks = executionOrder.filter(b => b.status === 'complete').length
  const totalBlocks = executionOrder.length
  const overallProgress = totalBlocks > 0 ? completedBlocks / totalBlocks : 0
  const isRecorded = runStatus === 'recorded'

  const cpuHistory = systemHistory.map(h => h.cpu)
  const memHistory = systemHistory.map(h => h.memory)
  const gpuHistory = systemHistory.filter(h => h.gpuMemory != null).map(h => h.gpuMemory!)

  return (
    <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 12, height: '100%', overflow: 'auto' }}>
      {/* Title */}
      <div style={{
        fontFamily: F, fontSize: FS.xxs, fontWeight: 900,
        color: T.dim, letterSpacing: '0.1em',
        padding: '0 0 4px',
        borderBottom: `1px solid ${T.border}`,
      }}>
        SYSTEM
      </div>

      {/* Gauges */}
      <div style={{ display: 'flex', justifyContent: 'space-around', gap: 8 }}>
        <div style={{ flex: 1 }}>
          <CircularGauge value={system.cpu} label="CPU" />
          <SystemSparkline data={cpuHistory} color={T.green} />
          {isRecorded && cpuHistory.length > 0 && (
            <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, textAlign: 'center', marginTop: 2 }}>
              Peak: {Math.round(Math.max(...cpuHistory))}%
            </div>
          )}
        </div>
        <div style={{ flex: 1 }}>
          <CircularGauge value={system.memory} label="RAM" unit={`${system.memoryGB.toFixed(1)}GB`} />
          <SystemSparkline data={memHistory} color={T.amber} />
          {isRecorded && memHistory.length > 0 && (
            <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, textAlign: 'center', marginTop: 2 }}>
              Peak: {Math.round(Math.max(...memHistory))}%
            </div>
          )}
        </div>
        {system.gpuMemory != null && (
          <div style={{ flex: 1 }}>
            <CircularGauge value={system.gpuMemory} label="GPU" unit={system.gpuMemoryGB ? `${system.gpuMemoryGB.toFixed(1)}GB` : undefined} />
            <SystemSparkline data={gpuHistory} color={T.purple} />
            {isRecorded && gpuHistory.length > 0 && (
              <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, textAlign: 'center', marginTop: 2 }}>
                Peak: {Math.round(Math.max(...gpuHistory))}%
              </div>
            )}
          </div>
        )}
      </div>

      {/* Run Info */}
      <div style={{
        background: T.surface1, border: `1px solid ${T.border}`,
        padding: 8, display: 'flex', flexDirection: 'column', gap: 4,
      }}>
        <div style={{
          fontFamily: F, fontSize: FS.xxs, fontWeight: 700,
          color: T.dim, letterSpacing: '0.06em', marginBottom: 2,
        }}>
          RUN INFO
        </div>

        {runId && (
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>ID</span>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec, fontVariantNumeric: 'tabular-nums' }}>
              {runId.length > 12 ? `${runId.slice(0, 12)}...` : runId}
            </span>
          </div>
        )}

        {pipelineId && (
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>Pipeline</span>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>{pipelineId}</span>
          </div>
        )}

        {paperId && (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>Paper</span>
            <button
              onClick={() => setView('paper')}
              style={{
                display: 'flex', alignItems: 'center', gap: 3,
                background: `${T.cyan}10`, border: `1px solid ${T.cyan}30`,
                padding: '1px 6px', cursor: 'pointer',
                fontFamily: F, fontSize: FS.xxs, color: T.cyan,
              }}
            >
              <FileText size={8} /> {paperId}
            </button>
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>Elapsed</span>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.text, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
            {formatElapsed(elapsed)}
          </span>
        </div>

        {eta != null && eta > 0 && (
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>ETA</span>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec, fontVariantNumeric: 'tabular-nums' }}>
              {formatElapsed(Math.round(eta))}
            </span>
          </div>
        )}
      </div>

      {/* Pipeline progress */}
      <div style={{
        background: T.surface1, border: `1px solid ${T.border}`, padding: 8,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>Pipeline Progress</span>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec, fontVariantNumeric: 'tabular-nums' }}>
            Block {completedBlocks}/{totalBlocks} — {Math.round(overallProgress * 100)}%
          </span>
        </div>
        <div style={{
          width: '100%', height: 4, background: T.surface3, borderRadius: 2,
          overflow: 'hidden',
        }}>
          <div style={{
            width: `${Math.round(overallProgress * 100)}%`,
            height: '100%', background: T.cyan,
            transition: 'width 0.3s ease',
          }} />
        </div>
      </div>
    </div>
  )
}
