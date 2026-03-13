import { useMetricsStore } from '@/stores/metricsStore'
import { T, F, FS } from '@/lib/design-tokens'
import { Cpu, HardDrive, MonitorSpeaker } from 'lucide-react'

interface SystemPanelProps {
  runId: string
}

function Gauge({ label, pct, absValue, absUnit, icon }: {
  label: string; pct: number; absValue: number; absUnit: string
  icon: React.ReactNode
}) {
  const size = 72
  const stroke = 6
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (pct / 100) * circumference
  const color = pct > 90 ? T.red : pct > 70 ? T.amber : T.cyan

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, padding: 8 }}>
      <div style={{ position: 'relative', width: size, height: size }}>
        <svg width={size} height={size}>
          <circle cx={size / 2} cy={size / 2} r={radius}
            fill="none" stroke={T.surface4} strokeWidth={stroke} />
          <circle cx={size / 2} cy={size / 2} r={radius}
            fill="none" stroke={color} strokeWidth={stroke}
            strokeDasharray={circumference} strokeDashoffset={offset}
            strokeLinecap="round"
            style={{ transform: 'rotate(-90deg)', transformOrigin: 'center', transition: 'stroke-dashoffset 0.5s ease' }}
          />
        </svg>
        <div style={{
          position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
        }}>
          <span style={{ fontFamily: F, fontSize: FS.xs, color: T.text, fontWeight: 700 }}>
            {Math.round(pct)}%
          </span>
          <span style={{ fontFamily: F, fontSize: 5, color: T.dim }}>
            {absValue.toFixed(1)} {absUnit}
          </span>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
        {icon}
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec, letterSpacing: '0.06em' }}>
          {label}
        </span>
      </div>
    </div>
  )
}

export default function SystemPanel({ runId }: SystemPanelProps) {
  const systemMetrics = useMetricsStore((s) => s.runs[runId]?.systemMetrics ?? [])
  const latest = systemMetrics.length > 0 ? systemMetrics[systemMetrics.length - 1] : null

  return (
    <div style={{ padding: 8 }}>
      <div style={{
        fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.12em',
        textTransform: 'uppercase', marginBottom: 8, padding: '0 4px',
      }}>
        SYSTEM
      </div>

      {!latest ? (
        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, textAlign: 'center', padding: 16 }}>
          Waiting for system metrics...
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
          <Gauge
            label="CPU"
            pct={latest.cpu_pct}
            absValue={latest.cpu_pct}
            absUnit="%"
            icon={<Cpu size={8} color={T.sec} />}
          />
          <Gauge
            label="RAM"
            pct={latest.mem_pct}
            absValue={latest.mem_gb}
            absUnit="GB"
            icon={<HardDrive size={8} color={T.sec} />}
          />
          {latest.gpu_mem_pct != null && (
            <Gauge
              label="GPU"
              pct={latest.gpu_mem_pct}
              absValue={latest.gpu_mem_gb ?? 0}
              absUnit="GB"
              icon={<MonitorSpeaker size={8} color={T.sec} />}
            />
          )}
        </div>
      )}
    </div>
  )
}
