import { T, F, FS } from '@/lib/design-tokens'
import { useRunStore } from '@/stores/runStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { Circle, Cpu } from 'lucide-react'
import NotificationBell from './NotificationBell'
import { useEffect } from 'react'

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

export default function StatusBar() {
  const { status, overallProgress, elapsed, eta } = useRunStore()
  const { demoMode, hardware, hardwareLoading, fetchHardware } = useSettingsStore()
  const isRunning = status === 'running'

  useEffect(() => {
    fetchHardware()
  }, [fetchHardware])

  return (
    <div
      style={{
        height: 24,
        background: T.surface1,
        borderTop: `1px solid ${T.border}`,
        display: 'flex',
        alignItems: 'center',
        padding: '0 12px',
        gap: 12,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }} role="status" aria-live="polite">
        <Circle
          size={4}
          fill={isRunning ? T.cyan : status === 'failed' ? T.red : T.green}
          color={isRunning ? T.cyan : status === 'failed' ? T.red : T.green}
          aria-hidden="true"
        />
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.1em', fontWeight: 900 }}>
          {isRunning
            ? 'RUNNING'
            : status === 'complete'
              ? 'COMPLETE'
              : status === 'failed'
                ? 'FAILED'
                : 'READY'}
        </span>
      </div>

      {isRunning && (
        <>
          <div
            style={{
              width: 120,
              height: 3,
              background: T.surface3,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${Math.round(overallProgress * 100)}%`,
                height: '100%',
                background: T.cyan,
                transition: 'width 0.3s ease',
              }}
            />
          </div>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
            {Math.round(overallProgress * 100)}%
          </span>

          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
            {formatTime(elapsed)}
          </span>

          {eta != null && eta > 0 && (
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
              ETA {formatTime(Math.round(eta))}
            </span>
          )}
        </>
      )}

      <div style={{ flex: 1 }} />

      {!hardwareLoading && hardware && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, opacity: 0.8 }} title={`VRAM: ${hardware.max_vram_gb}GB, Max Model: ${hardware.max_model_size}`}>
          <Cpu size={12} color={hardware.gpu_available ? T.green : T.dim} />
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.text }}>
            {hardware.gpu_backend !== 'none' ? hardware.gpu_backend.toUpperCase() : 'CPU'} • {hardware.usable_memory_gb}GB RAM
          </span>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.cyan, padding: '1px 4px', background: `${T.cyan}15`, borderRadius: 2 }}>
            UP TO {hardware.max_model_size.toUpperCase()}
          </span>
        </div>
      )}

      <NotificationBell />

      {demoMode && (
        <span
          style={{
            fontFamily: F, fontSize: FS.xxs, fontWeight: 900,
            letterSpacing: '0.1em', color: T.amber,
            background: `${T.amber}15`, border: `1px solid ${T.amber}30`,
            padding: '1px 6px',
          }}
        >
          DEMO
        </span>
      )}

      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
        {demoMode ? 'DEMO MODE' : 'LOCAL MODE'}
      </span>
    </div>
  )
}
