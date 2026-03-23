import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore, type SystemMetricPoint } from '@/stores/metricsStore'
import { Cpu, HardDrive } from 'lucide-react'

const EMPTY_SYSTEM_METRICS: SystemMetricPoint[] = []

interface SystemPanelProps {
  runId: string
}

function GaugeRing({ value, label, detail, size = 60 }: { value: number; label: string; detail: string; size?: number }) {
  const radius = (size - 8) / 2
  const circumference = 2 * Math.PI * radius
  const progress = Math.min(Math.max(value, 0), 100) / 100
  const offset = circumference * (1 - progress)

  let color = '#22c55e' // green
  if (value > 80) color = '#ff433d' // red
  else if (value > 60) color = '#f59e0b' // yellow

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Background ring */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={T.surface3}
          strokeWidth={3}
        />
        {/* Progress ring */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={3}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: 'stroke-dashoffset 0.5s ease, stroke 0.3s ease' }}
        />
        {/* Center text */}
        <text
          x={size / 2}
          y={size / 2 - 2}
          textAnchor="middle"
          dominantBaseline="central"
          fill={T.text}
          fontFamily={F}
          fontSize={FS.sm}
          fontWeight={700}
        >
          {Math.round(value)}%
        </text>
        <text
          x={size / 2}
          y={size / 2 + 10}
          textAnchor="middle"
          dominantBaseline="central"
          fill={T.dim}
          fontFamily={F}
          fontSize={FS.xxs}
        >
          {detail}
        </text>
      </svg>
      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.08em' }}>
        {label}
      </span>
    </div>
  )
}

function MiniSparkline({ data, height = 20, width = 80 }: { data: number[]; height?: number; width?: number }) {
  if (data.length < 2) return null

  const max = Math.max(...data, 1)
  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * width
      const y = height - (v / max) * height
      return `${x},${y}`
    })
    .join(' ')

  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <polyline
        points={points}
        fill="none"
        stroke={T.cyan}
        strokeWidth={1}
        opacity={0.6}
      />
    </svg>
  )
}

export default function SystemPanel({ runId }: SystemPanelProps) {
  const latest = useMetricsStore((s) => s.getLatestSystemMetrics(runId))
  const systemHistory = useMetricsStore((s) => s.runs[runId]?.systemMetrics ?? EMPTY_SYSTEM_METRICS)
  const runStatus = useMetricsStore((s) => s.runs[runId]?.status)
  const isReplay = runStatus !== 'running'

  if (!latest && systemHistory.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          gap: 8,
          padding: 16,
        }}
      >
        <Cpu size={16} color={T.dim} />
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          System metrics loading...
        </span>
      </div>
    )
  }

  const cpuHistory = systemHistory.map((m: SystemMetricPoint) => m.cpu)
  const memHistory = systemHistory.map((m: SystemMetricPoint) => (m.memoryTotal > 0 ? (m.memory / m.memoryTotal) * 100 : 0))
  const gpuHistory = systemHistory.filter((m: SystemMetricPoint) => m.gpu != null).map((m: SystemMetricPoint) => m.gpu!)

  const cpu = latest?.cpu ?? (isReplay ? Math.max(...cpuHistory, 0) : 0)
  const memPct = latest && latest.memoryTotal > 0 ? (latest.memory / latest.memoryTotal) * 100 : (isReplay ? Math.max(...memHistory, 0) : 0)
  const memDetail = latest ? `${latest.memory.toFixed(0)} GB` : ''
  const hasGpu = latest?.gpu != null || gpuHistory.length > 0
  const gpuPct = latest?.gpu ?? (isReplay && gpuHistory.length > 0 ? Math.max(...gpuHistory) : 0)
  const gpuMemDetail = latest?.gpuMemory != null && latest?.gpuMemoryTotal != null
    ? `${latest.gpuMemory.toFixed(0)} GB`
    : ''

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
        padding: '10px 8px',
      }}
    >
      <div
        style={{
          fontFamily: F,
          fontSize: FS.xxs,
          color: T.dim,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <HardDrive size={9} />
        SYSTEM {isReplay ? '(PEAK)' : ''}
      </div>

      <div style={{ display: 'flex', justifyContent: 'center', gap: 16 }}>
        <GaugeRing value={cpu} label="CPU" detail={memDetail ? '' : '--'} size={56} />
        <GaugeRing value={memPct} label="MEM" detail={memDetail} size={56} />
        {hasGpu && (
          <GaugeRing value={gpuPct} label="GPU" detail={gpuMemDetail} size={56} />
        )}
      </div>

      {cpuHistory.length > 2 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>CPU History</span>
          <MiniSparkline data={cpuHistory} />
        </div>
      )}

      {memHistory.length > 2 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>Memory History</span>
          <MiniSparkline data={memHistory} />
        </div>
      )}
    </div>
  )
}
