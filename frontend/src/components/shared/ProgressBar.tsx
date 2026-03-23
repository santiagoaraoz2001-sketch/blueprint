import { T, F, FS } from '@/lib/design-tokens'

interface ProgressBarProps {
  value: number // 0-100
  color?: string
  height?: number
  showLabel?: boolean
  label?: string
  /** Show pulse/shimmer animation for running state */
  animated?: boolean
}

export default function ProgressBar({
  value,
  color = T.cyan,
  height = 3,
  showLabel = false,
  label,
  animated = false,
}: ProgressBarProps) {
  const clampedValue = Math.min(100, Math.max(0, value))
  const isActive = animated && clampedValue > 0 && clampedValue < 100

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, width: '100%' }}>
      <div
        style={{
          flex: 1,
          height,
          background: T.surface6,
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        <div
          style={{
            height: '100%',
            width: `${clampedValue}%`,
            background: color,
            transition: 'width 0.5s ease-in-out',
            position: 'relative',
            animation: isActive ? 'progressPulse 2s ease-in-out infinite' : undefined,
          }}
        >
          {/* Shimmer overlay for running state */}
          {isActive && (
            <div
              style={{
                position: 'absolute',
                inset: 0,
                background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent)',
                animation: 'shimmer 2s infinite',
              }}
            />
          )}
        </div>
      </div>
      {showLabel && (
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, minWidth: 28, textAlign: 'right' }}>
          {label || `${Math.round(clampedValue)}%`}
        </span>
      )}
    </div>
  )
}
