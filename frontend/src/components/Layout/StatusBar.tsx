import { T, F, FS } from '@/lib/design-tokens'
import { useRunStore } from '@/stores/runStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { Circle, Cpu, Sparkles } from 'lucide-react'
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
    <footer
      style={{
        height: 30,
        background: `linear-gradient(180deg, ${T.surface1}f0 0%, ${T.surface0}ef 100%)`,
        borderTop: `1px solid ${T.border}`,
        display: 'flex',
        alignItems: 'center',
        padding: '0 12px',
        gap: 12,
        backdropFilter: 'blur(8px)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }} role="status" aria-live="polite">
        <Circle size={6} fill={isRunning ? T.amber : status === 'failed' ? T.red : T.green} color={isRunning ? T.amber : status === 'failed' ? T.red : T.green} />
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          {isRunning ? 'Running' : status === 'complete' ? 'Complete' : status === 'failed' ? 'Failed' : 'Ready'}
        </span>
      </div>

      {isRunning && (
        <>
          <div style={{ width: 140, height: 5, background: T.surface3, borderRadius: 999, overflow: 'hidden' }}>
            <div
              style={{
                width: `${Math.round(overallProgress * 100)}%`,
                height: '100%',
                background: `linear-gradient(90deg, ${T.amber}, ${T.cyan})`,
                transition: 'width 0.25s ease',
              }}
            />
          </div>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.cyan }}>{Math.round(overallProgress * 100)}%</span>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>{formatTime(elapsed)}</span>
          {eta != null && eta > 0 && <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>ETA {formatTime(Math.round(eta))}</span>}
        </>
      )}

      <div style={{ flex: 1 }} />

      {!hardwareLoading && hardware && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }} title={`VRAM ${hardware.max_vram_gb}GB • max ${hardware.max_model_size}`}>
          <Cpu size={13} color={hardware.gpu_available ? T.green : T.dim} />
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
            {hardware.gpu_backend !== 'none' ? hardware.gpu_backend.toUpperCase() : 'CPU'} • {hardware.usable_memory_gb}GB
          </span>
        </div>
      )}

      {demoMode && (
        <span style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '2px 7px', borderRadius: 999, background: `${T.amber}1d`, border: `1px solid ${T.amber}4f`, color: T.amber, fontFamily: F, fontSize: FS.xxs }}>
          <Sparkles size={10} /> Demo
        </span>
      )}

      <NotificationBell />
    </footer>
  )
}
