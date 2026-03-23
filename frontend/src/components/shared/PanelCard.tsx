import { useState, useRef, useCallback, type ReactNode } from 'react'
import { motion } from 'framer-motion'
import { T, F, FS } from '@/lib/design-tokens'

interface PanelCardProps {
  title?: string
  subtitle?: string
  accent?: string
  children: ReactNode
  onClick?: () => void
  className?: string
  style?: React.CSSProperties
  padding?: number
}

export default function PanelCard({
  title,
  subtitle,
  accent = T.cyan,
  children,
  onClick,
  style: styleProp,
  padding = 6,
}: PanelCardProps) {
  const [hovered, setHovered] = useState(false)
  const cardRef = useRef<HTMLDivElement>(null)
  const rotateRef = useRef({ x: 0, y: 0 })
  const rafRef = useRef<number | null>(null)
  const [tilt, setTilt] = useState({ rotateX: 0, rotateY: 0 })

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!cardRef.current) return

    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
    }

    rafRef.current = requestAnimationFrame(() => {
      const rect = cardRef.current!.getBoundingClientRect()
      const x = (e.clientX - rect.left) / rect.width
      const y = (e.clientY - rect.top) / rect.height

      const rotateY = (x - 0.5) * 6   // -3 to +3 degrees
      const rotateX = (0.5 - y) * 6    // -3 to +3 degrees

      rotateRef.current = { x: rotateX, y: rotateY }
      setTilt({ rotateX, rotateY })
      rafRef.current = null
    })
  }, [])

  const handleMouseEnter = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    setHovered(true)
    handleMouseMove(e)
  }, [handleMouseMove])

  const handleMouseLeave = useCallback(() => {
    setHovered(false)
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    rotateRef.current = { x: 0, y: 0 }
    setTilt({ rotateX: 0, rotateY: 0 })
  }, [])

  return (
    <motion.div
      ref={cardRef}
      onClick={onClick}
      onMouseEnter={handleMouseEnter}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      style={{
        background: `linear-gradient(180deg, #0C0C0C 0%, ${T.surface3} 100%)`,
        border: `1px solid ${hovered ? T.borderHi : T.border}`,
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'border-color 0.18s, box-shadow 0.18s, transform 0.15s ease-out',
        boxShadow: hovered
          ? `0 0 0 1px ${accent}18, inset 0 0 24px rgba(0,0,0,0.4)`
          : 'inset 0 0 24px rgba(0,0,0,0.3)',
        transform: `perspective(600px) rotateX(${tilt.rotateX}deg) rotateY(${tilt.rotateY}deg)`,
        willChange: 'transform',
        ...styleProp,
      }}
    >
      {/* Top accent bar */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: 1,
          background: `linear-gradient(90deg, ${accent}80 0%, ${accent}20 60%, transparent 100%)`,
          opacity: hovered ? 1 : 0.35,
          transition: 'opacity 0.18s',
          pointerEvents: 'none',
          zIndex: 1,
        }}
      />

      {/* Left accent stripe */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          bottom: 0,
          width: 2,
          background: `linear-gradient(180deg, ${accent}50 0%, ${accent}15 60%, transparent 100%)`,
          opacity: hovered ? 1 : 0.5,
          transition: 'opacity 0.18s',
          pointerEvents: 'none',
        }}
      />

      {/* Title bar */}
      {title && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 6px 0 9px',
            borderBottom: `1px solid ${hovered ? T.borderHi : T.border}`,
            height: 21,
            minHeight: 21,
            flexShrink: 0,
            gap: 3,
            overflow: 'hidden',
            background: hovered ? T.surface5 : 'transparent',
            transition: 'background 0.18s, border-color 0.18s',
          }}
        >
          <span
            style={{
              fontSize: 7,
              fontWeight: 900,
              fontFamily: F,
              color: hovered ? accent : T.dim,
              letterSpacing: '0.11em',
              textTransform: 'uppercase',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              transition: 'color 0.18s',
              margin: 0,
              lineHeight: 1,
            }}
          >
            {title}
          </span>
          {subtitle && (
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, flexShrink: 0 }}>
              {subtitle}
            </span>
          )}
        </div>
      )}

      {/* Content */}
      <div style={{ flex: 1, padding, overflow: 'hidden', minHeight: 0 }}>
        {children}
      </div>
    </motion.div>
  )
}
