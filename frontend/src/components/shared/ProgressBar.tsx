import { T, F, FS } from '@/lib/design-tokens'

interface ProgressBarProps {
  value: number // 0-100
  color?: string
  height?: number
  showLabel?: boolean
  label?: string
}

export default function ProgressBar({
  value,
  color = T.cyan,
  height = 3,
  showLabel = false,
  label,
}: ProgressBarProps) {
  const clampedValue = Math.min(100, Math.max(0, value))

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
            transition: 'width 0.3s ease',
          }}
        />
      </div>
      {showLabel && (
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, minWidth: 28, textAlign: 'right' }}>
          {label || `${Math.round(clampedValue)}%`}
        </span>
      )}
    </div>
  )
}
