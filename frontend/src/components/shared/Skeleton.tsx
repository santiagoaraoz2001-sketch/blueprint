import { T } from '@/lib/design-tokens'

interface SkeletonProps {
  width?: number | string
  height?: number | string
  style?: React.CSSProperties
}

export default function Skeleton({ width = '100%', height = 12, style }: SkeletonProps) {
  return (
    <div
      style={{
        width,
        height,
        background: `linear-gradient(90deg, ${T.surface3} 25%, ${T.surface5} 50%, ${T.surface3} 75%)`,
        backgroundSize: '200% 100%',
        animation: 'shimmer 1.5s infinite linear',
        ...style,
      }}
    />
  )
}

export function SkeletonCard({ height = 80 }: { height?: number }) {
  return (
    <div
      style={{
        height,
        background: T.surface2,
        border: `1px solid ${T.border}`,
        padding: 8,
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}
    >
      <Skeleton width="60%" height={8} />
      <Skeleton width="100%" height={6} />
      <Skeleton width="40%" height={6} />
    </div>
  )
}
