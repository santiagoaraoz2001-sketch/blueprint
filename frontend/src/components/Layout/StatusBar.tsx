import { T, F, FS, FCODE, BRAND_TEAL } from '@/lib/design-tokens'
import { useRunStore }      from '@/stores/runStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { Cpu, Sparkles, Radio, HardDrive, Activity } from 'lucide-react'
import NotificationBell from './NotificationBell'
import { useEffect, useState, useCallback } from 'react'
import { api } from '@/api/client'

interface HealthData {
  cpu_percent: number
  memory_percent: number
  memory_total_gb: number
  gpu_percent: number | null
  gpu_name: string | null
  disk_free_gb: number
  ollama_connected: boolean
  active_runs: number
  queued_runs: number
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatDisk(gb: number): string {
  if (gb >= 1000) return `${(gb / 1000).toFixed(1)}TB`
  return `${Math.round(gb)}GB`
}

// Pulsing dot — instrument-panel style live indicator
function LiveDot({ color, pulse = false }: { color: string; pulse?: boolean }) {
  return (
    <span
      style={{
        position: 'relative',
        display: 'inline-flex',
        width: 7,
        height: 7,
        flexShrink: 0,
      }}
    >
      {pulse && (
        <span
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: '50%',
            background: color,
            opacity: 0.5,
            animation: 'pulse-ring 1.4s ease-out infinite',
          }}
        />
      )}
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: '50%',
          background: color,
          boxShadow: `0 0 6px ${color}cc`,
          display: 'block',
        }}
      />
    </span>
  )
}

/** Micro usage bar for CPU/MEM/GPU in the status bar */
function UsageBar({ value, label, warn = 80, crit = 95 }: {
  value: number; label: string; warn?: number; crit?: number
}) {
  const color = value >= crit ? T.red : value >= warn ? T.amber : T.green
  return (
    <div
      style={{ display: 'flex', alignItems: 'center', gap: 4 }}
      title={`${label}: ${Math.round(value)}%`}
    >
      <span style={{ fontFamily: FCODE, fontSize: FS.xxs, color: T.dim, width: 22, textAlign: 'right' }}>
        {label}
      </span>
      <div
        style={{
          width: 40,
          height: 3,
          background: T.surface4,
          borderRadius: 999,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${Math.min(value, 100)}%`,
            height: '100%',
            background: color,
            transition: 'width 0.5s ease, background 0.3s ease',
            borderRadius: 999,
          }}
        />
      </div>
      <span
        style={{
          fontFamily: FCODE,
          fontSize: FS.xxs,
          color,
          width: 26,
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {Math.round(value)}%
      </span>
    </div>
  )
}

export default function StatusBar() {
  const { status, overallProgress, elapsed, eta } = useRunStore()
  const { demoMode, hardware, hardwareLoading, fetchHardware } = useSettingsStore()
  const isRunning  = status === 'running'
  const isComplete = status === 'complete'
  const isFailed   = status === 'failed'

  const [health, setHealth] = useState<HealthData | null>(null)

  useEffect(() => { fetchHardware() }, [fetchHardware])

  // Poll /api/system/health every 5 seconds
  const fetchHealth = useCallback(async () => {
    try {
      const data = await api.get<HealthData>('/system/health')
      if (data) setHealth(data)
    } catch {
      // Silently ignore — status bar is non-critical
    }
  }, [])

  useEffect(() => {
    fetchHealth()
    const interval = setInterval(fetchHealth, 5000)
    return () => clearInterval(interval)
  }, [fetchHealth])

  const dotColor = isRunning ? T.amber : isFailed ? T.red : isComplete ? T.green : BRAND_TEAL
  const statusLabel = isRunning ? 'RUNNING' : isComplete ? 'COMPLETE' : isFailed ? 'FAILED' : 'READY'

  return (
    <footer
      role="contentinfo"
      aria-label="Pipeline status bar"
      style={{
        height: 28,
        background: `linear-gradient(180deg, ${T.surface2}f6 0%, ${T.surface0}f4 100%)`,
        borderTop: `1px solid ${T.border}`,
        boxShadow: `inset 0 1px 0 rgba(255,255,255,0.04), 0 -1px 0 rgba(0,0,0,0.3)`,
        display: 'flex',
        alignItems: 'center',
        padding: '0 14px',
        gap: 12,
        backdropFilter: 'blur(10px)',
      }}
    >
      {/* System status — instrument panel dot + label */}
      <div
        style={{ display: 'flex', alignItems: 'center', gap: 6 }}
        role="status"
        aria-live="polite"
      >
        <LiveDot color={dotColor} pulse={isRunning} />
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: isRunning ? T.amber : isComplete ? T.green : isFailed ? T.red : T.dim,
            letterSpacing: '0.14em',
            fontWeight: 700,
          }}
        >
          {statusLabel}
        </span>
      </div>

      {/* Separator pip */}
      <div style={{ width: 1, height: 12, background: T.border, flexShrink: 0 }} />

      {/* Progress bar + counters — visible while running */}
      {isRunning && (
        <>
          <div
            style={{
              width: 140,
              height: 3,
              background: T.surface4,
              borderRadius: 999,
              overflow: 'hidden',
              flexShrink: 0,
              boxShadow: `inset 0 1px 2px rgba(0,0,0,0.4)`,
            }}
          >
            <div
              style={{
                width: `${Math.round(overallProgress * 100)}%`,
                height: '100%',
                background: `linear-gradient(90deg, ${T.amber}, ${BRAND_TEAL})`,
                boxShadow: `0 0 8px ${BRAND_TEAL}aa, 0 0 3px ${BRAND_TEAL}`,
                transition: 'width 0.3s ease',
                borderRadius: 999,
              }}
            />
          </div>
          <span
            style={{
              fontFamily: FCODE,
              fontSize: FS.xxs,
              color: BRAND_TEAL,
              letterSpacing: '0.06em',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {Math.round(overallProgress * 100)}%
          </span>
          <span
            style={{
              fontFamily: FCODE,
              fontSize: FS.xxs,
              color: T.sec,
              letterSpacing: '0.06em',
              fontVariantNumeric: 'tabular-nums',
              opacity: 0.7,
            }}
          >
            {formatTime(elapsed)}
          </span>
          {eta != null && eta > 0 && (
            <span
              style={{
                fontFamily: FCODE,
                fontSize: FS.xxs,
                color: T.dim,
                letterSpacing: '0.06em',
              }}
            >
              ETA {formatTime(Math.round(eta))}
            </span>
          )}
        </>
      )}

      <div style={{ flex: 1 }} />

      {/* System health gauges */}
      {health && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <UsageBar value={health.cpu_percent} label="CPU" />
          <UsageBar value={health.memory_percent} label="MEM" />
          {health.gpu_percent != null && (
            <UsageBar value={health.gpu_percent} label="GPU" />
          )}
        </div>
      )}

      {/* Separator */}
      {health && (
        <div style={{ width: 1, height: 12, background: T.border, flexShrink: 0 }} />
      )}

      {/* Ollama status */}
      {health && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            padding: '1px 6px',
            borderRadius: 5,
            background: health.ollama_connected ? `${T.green}12` : `${T.red}12`,
            border: `0.5px solid ${health.ollama_connected ? T.green : T.red}35`,
          }}
          title={health.ollama_connected ? 'Ollama connected' : 'Ollama disconnected'}
        >
          <Activity size={8} color={health.ollama_connected ? T.green : T.red} />
          <span
            style={{
              fontFamily: F,
              fontSize: FS.xxs,
              color: health.ollama_connected ? T.green : T.red,
              letterSpacing: '0.08em',
              fontWeight: 600,
            }}
          >
            LLM
          </span>
        </div>
      )}

      {/* Disk space */}
      {health && (
        <div
          style={{ display: 'flex', alignItems: 'center', gap: 3 }}
          title={`${health.disk_free_gb}GB free disk space`}
        >
          <HardDrive size={9} color={T.dim} />
          <span style={{ fontFamily: FCODE, fontSize: FS.xxs, color: T.dim }}>
            {formatDisk(health.disk_free_gb)}
          </span>
        </div>
      )}

      {/* Active runs */}
      {health && health.active_runs > 0 && (
        <span
          style={{
            fontFamily: FCODE,
            fontSize: FS.xxs,
            color: T.amber,
            fontVariantNumeric: 'tabular-nums',
          }}
          title={`${health.active_runs} active, ${health.queued_runs} queued`}
        >
          {health.active_runs}R{health.queued_runs > 0 ? `+${health.queued_runs}Q` : ''}
        </span>
      )}

      {/* Hardware readout */}
      {!health && !hardwareLoading && hardware && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 5,
            padding: '2px 8px',
            borderRadius: 5,
            background: `${T.surface3}88`,
            border: `0.5px solid ${T.border}`,
          }}
          title={`VRAM ${hardware.max_vram_gb}GB \u00B7 max ${hardware.max_model_size}`}
        >
          <Cpu size={10} color={hardware.gpu_available ? T.green : T.dim} />
          <span
            style={{
              fontFamily: FCODE,
              fontSize: FS.xxs,
              color: hardware.gpu_available ? T.sec : T.dim,
              letterSpacing: '0.06em',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {hardware.gpu_backend !== 'none' ? hardware.gpu_backend.toUpperCase() : 'CPU'}
            {' \u00B7 '}
            {hardware.usable_memory_gb}
            <span style={{ opacity: 0.6 }}>GB</span>
          </span>
        </div>
      )}

      {/* Local connection indicator */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          padding: '1px 6px',
          borderRadius: 5,
          background: `${BRAND_TEAL}12`,
          border: `0.5px solid ${BRAND_TEAL}35`,
        }}
      >
        <Radio size={9} color={BRAND_TEAL} />
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: BRAND_TEAL,
            letterSpacing: '0.10em',
            fontWeight: 700,
          }}
        >
          LOCAL
        </span>
      </div>

      {/* Demo badge */}
      {demoMode && (
        <span
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 3,
            padding: '1px 6px',
            borderRadius: 5,
            background: `${T.amber}1a`,
            border: `0.5px solid ${T.amber}50`,
            color: T.amber,
            fontFamily: F,
            fontSize: FS.xxs,
            letterSpacing: '0.08em',
            fontWeight: 600,
          }}
        >
          <Sparkles size={9} />
          DEMO
        </span>
      )}

      <NotificationBell />
    </footer>
  )
}
