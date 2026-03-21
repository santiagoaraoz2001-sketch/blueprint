import { T, F, FS, FD } from '@/lib/design-tokens'
import { Loader2, ArrowRight } from 'lucide-react'
import { useUIStore } from '@/stores/uiStore'
import type { LiveRunItem } from '@/hooks/useOutputs'

function formatEta(seconds: number | null): string {
  if (seconds == null || seconds <= 0) return ''
  if (seconds < 60) return `${Math.round(seconds)}s`
  return `${Math.round(seconds / 60)}m`
}

export default function LiveRunBanner({ runs }: { runs: LiveRunItem[] }) {
  if (runs.length === 0) return null

  return (
    <div style={{ padding: '0 16px 8px' }}>
      <div
        style={{
          fontSize: FS.xxs,
          fontFamily: F,
          color: T.dim,
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          marginBottom: 6,
        }}
      >
        LIVE
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {runs.map((run) => (
          <button
            key={run.run_id}
            onClick={() => useUIStore.getState().openMonitor(run.run_id)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '8px 12px',
              background: `${T.green}08`,
              border: `1px solid ${T.green}22`,
              cursor: 'pointer',
              textAlign: 'left',
              width: '100%',
              transition: 'all 0.15s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = `${T.green}14`
              e.currentTarget.style.borderColor = `${T.green}33`
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = `${T.green}08`
              e.currentTarget.style.borderColor = `${T.green}22`
            }}
          >
            <Loader2
              size={12}
              color={T.green}
              style={{ animation: 'spin 1s linear infinite', flexShrink: 0 }}
            />

            <span
              style={{
                fontFamily: FD,
                fontSize: FS.sm,
                color: T.text,
                fontWeight: 500,
                flex: 1,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {run.pipeline_name || 'Pipeline'}
            </span>

            {/* Progress bar */}
            <div
              style={{
                width: 80,
                height: 3,
                background: T.surface3,
                borderRadius: 1,
                overflow: 'hidden',
                flexShrink: 0,
              }}
            >
              <div
                style={{
                  width: `${Math.round(run.overall_progress * 100)}%`,
                  height: '100%',
                  background: T.green,
                  transition: 'width 0.5s ease',
                }}
              />
            </div>

            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.green, flexShrink: 0, minWidth: 28, textAlign: 'right' }}>
              {Math.round(run.overall_progress * 100)}%
            </span>

            {run.eta_seconds != null && run.eta_seconds > 0 && (
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, flexShrink: 0 }}>
                {formatEta(run.eta_seconds)}
              </span>
            )}

            <ArrowRight size={10} color={T.dim} style={{ flexShrink: 0 }} />
          </button>
        ))}
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
