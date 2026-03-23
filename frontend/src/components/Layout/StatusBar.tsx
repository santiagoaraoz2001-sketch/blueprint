import { T, F, FS, FCODE } from '@/lib/design-tokens'
import { useRunStore }      from '@/stores/runStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { Circle, Cpu, Sparkles } from 'lucide-react'
import NotificationBell from './NotificationBell'
import { useEffect }    from 'react'

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
        height: 28,
        background: `linear-gradient(180deg, ${T.surface1}f4 0%, ${T.surface0}f2 100%)`,
        borderTop: `0.5px solid ${T.border}`,
        display: 'flex',
        alignItems: 'center',
        padding: '0 12px',
        gap: 10,
        backdropFilter: 'blur(10px)',
      }}
    >
      {/* Status dot + label */}
      <div
        style={{ display: 'flex', alignItems: 'center', gap: 5 }}
        role="status"
        aria-live="polite"
      >
        <Circle
          size={5}
          fill={
            isRunning
              ? T.amber
              : status === 'failed'
                ? T.red
                : T.green
          }
          color={
            isRunning
              ? T.amber
              : status === 'failed'
                ? T.red
                : T.green
          }
        />
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.dim,
            letterSpacing: '0.10em',
            textTransform: 'uppercase',
          }}
        >
          {isRunning
            ? 'Running'
            : status === 'complete'
              ? 'Complete'
              : status === 'failed'
                ? 'Failed'
                : 'Ready'}
        </span>
      </div>

      {/* Progress bar + counters */}
      {isRunning && (
        <>
          {/* Refined 1.5px progress bar with glow fill */}
          <div
            style={{
              width: 128,
              height: 2,
              background: T.surface4,
              borderRadius: 999,
              overflow: 'hidden',
              flexShrink: 0,
            }}
          >
            <div
              style={{
                width: `${Math.round(overallProgress * 100)}%`,
                height: '100%',
                background: `linear-gradient(90deg, ${T.amber}, ${T.cyan})`,
                boxShadow: `0 0 6px ${T.cyan}88`,
                transition: 'width 0.28s ease',
                borderRadius: 999,
              }}
            />
          </div>
          <span
            style={{
              fontFamily: FCODE,
              fontSize: FS.xxs,
              color: T.cyan,
              letterSpacing: '0.04em',
            }}
          >
            {Math.round(overallProgress * 100)}%
          </span>
          <span
            style={{
              fontFamily: FCODE,
              fontSize: FS.xxs,
              color: T.dim,
              letterSpacing: '0.04em',
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
                letterSpacing: '0.04em',
              }}
            >
              ETA {formatTime(Math.round(eta))}
            </span>
          )}
        </>
      )}

      <div style={{ flex: 1 }} />

      {/* Hardware info */}
      {!hardwareLoading && hardware && (
        <div
          style={{ display: 'flex', alignItems: 'center', gap: 5 }}
          title={`VRAM ${hardware.max_vram_gb}GB • max ${hardware.max_model_size}`}
        >
          <Cpu size={11} color={hardware.gpu_available ? T.green : T.dim} />
          <span
            style={{
              fontFamily: FCODE,
              fontSize: FS.xxs,
              color: T.sec,
              letterSpacing: '0.04em',
              opacity: 0.75,
            }}
          >
            {hardware.gpu_backend !== 'none'
              ? hardware.gpu_backend.toUpperCase()
              : 'CPU'}{' '}
            · {hardware.usable_memory_gb}GB
          </span>
        </div>
      )}

      {/* Demo badge */}
      {demoMode && (
        <span
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 3,
            padding: '1px 6px',
            borderRadius: 999,
            background: `${T.amber}1a`,
            border: `0.5px solid ${T.amber}45`,
            color: T.amber,
            fontFamily: F,
            fontSize: FS.xxs,
            letterSpacing: '0.06em',
          }}
        >
          <Sparkles size={9} />
          Demo
        </span>
      )}

      <NotificationBell />
    </footer>
  )
}
