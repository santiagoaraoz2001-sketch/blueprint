/**
 * Screensaver — Blueprint / Specific Labs
 *
 * Activates after 90 s of inactivity. Full-screen ambient field
 * with the exact original animated logo SVG at centre stage.
 *
 * Layers (back → front):
 *   0  Void background
 *   1  Deep nebula gradients (slow drift, accent-responsive)
 *   2  Perspective grid (receding into depth, accent-responsive)
 *   3  Aurora light ribbons (canvas-based, accent-responsive)
 *   4  Central logo presentation with orbit rings
 *   5  Time display
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { FD, T, hexToRgba } from '@/lib/design-tokens'

const IDLE_TIMEOUT_MS = 90_000   // 90 s
const DISMISS_EVENTS  = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'wheel'] as const

function useIdleTimer(idleMs: number) {
  const [idle, setIdle] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const reset = () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      setIdle(false)
      timerRef.current = setTimeout(() => setIdle(true), idleMs)
    }

    reset() // kick off on mount
    DISMISS_EVENTS.forEach((ev) => document.addEventListener(ev, reset, { passive: true }))

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      DISMISS_EVENTS.forEach((ev) => document.removeEventListener(ev, reset))
    }
  }, [idleMs])

  return idle
}

function useClock() {
  const [time, setTime] = useState(() => {
    const d = new Date()
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  })

  useEffect(() => {
    const tick = () => {
      const d = new Date()
      setTime(d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))
    }
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  return time
}

// ── Aurora Canvas ─────────────────────────────────────────────────
// Renders flowing bezier ribbon curves that undulate like an aurora borealis.

function hexToRgbValues(hex: string): [number, number, number] {
  const clean = hex.replace('#', '')
  const v = clean.length === 3
    ? clean.split('').map((x) => x + x).join('')
    : clean
  const int = Number.parseInt(v, 16)
  return [(int >> 16) & 255, (int >> 8) & 255, int & 255]
}

interface Ribbon {
  yBase: number       // vertical center (0–1 of canvas height)
  amplitude: number   // wave height in px
  frequency: number   // how many waves across the screen
  speed: number       // radians per millisecond
  opacity: number     // max ribbon opacity
  width: number       // ribbon thickness in px
  phase: number       // initial phase offset
  hueShift: number    // offset from accent color (degrees)
}

function AuroraCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animRef = useRef<number>(0)
  const ribbonsRef = useRef<Ribbon[]>([])

  const initRibbons = useCallback(() => {
    return [
      { yBase: 0.22, amplitude: 50,  frequency: 0.0018, speed: 0.00012, opacity: 0.06, width: 120, phase: 0,    hueShift: 0 },
      { yBase: 0.32, amplitude: 70,  frequency: 0.0014, speed: 0.00018, opacity: 0.05, width: 150, phase: 1.5,  hueShift: 30 },
      { yBase: 0.45, amplitude: 40,  frequency: 0.0022, speed: 0.00010, opacity: 0.07, width: 100, phase: 3.0,  hueShift: -20 },
      { yBase: 0.58, amplitude: 60,  frequency: 0.0016, speed: 0.00015, opacity: 0.04, width: 130, phase: 4.2,  hueShift: 60 },
      { yBase: 0.72, amplitude: 45,  frequency: 0.0020, speed: 0.00013, opacity: 0.05, width: 110, phase: 5.8,  hueShift: -40 },
    ]
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const resize = () => {
      canvas.width = window.innerWidth * window.devicePixelRatio
      canvas.height = window.innerHeight * window.devicePixelRatio
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio)
    }
    resize()
    window.addEventListener('resize', resize)

    ribbonsRef.current = initRibbons()

    const w = () => window.innerWidth
    const h = () => window.innerHeight

    function draw(time: number) {
      ctx!.clearRect(0, 0, w(), h())

      const [acR, acG, acB] = hexToRgbValues(T.cyan)

      for (const ribbon of ribbonsRef.current) {
        const centerY = ribbon.yBase * h()
        const t = time * ribbon.speed + ribbon.phase

        // Apply a subtle hue rotation using channel mixing
        const shift = ribbon.hueShift / 360
        const r = Math.min(255, Math.max(0, acR + shift * 60))
        const g = Math.min(255, Math.max(0, acG - shift * 30))
        const b = Math.min(255, Math.max(0, acB + shift * 40))

        ctx!.beginPath()

        // Draw a flowing path across the screen width
        const segments = 80
        const segW = w() / segments

        for (let i = 0; i <= segments; i++) {
          const x = i * segW
          // Multiple sine waves at different frequencies create organic undulation
          const wave1 = Math.sin(x * ribbon.frequency + t) * ribbon.amplitude
          const wave2 = Math.sin(x * ribbon.frequency * 0.6 + t * 1.3 + 2.1) * ribbon.amplitude * 0.4
          const wave3 = Math.sin(x * ribbon.frequency * 1.8 + t * 0.7 + 4.5) * ribbon.amplitude * 0.15
          const y = centerY + wave1 + wave2 + wave3

          if (i === 0) ctx!.moveTo(x, y)
          else ctx!.lineTo(x, y)
        }

        // Draw return path (bottom of ribbon) slightly offset
        for (let i = segments; i >= 0; i--) {
          const x = i * segW
          const wave1 = Math.sin(x * ribbon.frequency + t + 0.3) * ribbon.amplitude
          const wave2 = Math.sin(x * ribbon.frequency * 0.6 + t * 1.3 + 2.4) * ribbon.amplitude * 0.4
          const wave3 = Math.sin(x * ribbon.frequency * 1.8 + t * 0.7 + 4.8) * ribbon.amplitude * 0.15
          const y = centerY + wave1 + wave2 + wave3 + ribbon.width

          ctx!.lineTo(x, y)
        }

        ctx!.closePath()

        // Gradient fill — transparent at edges, accent color in the center
        const grad = ctx!.createLinearGradient(0, centerY - ribbon.amplitude, 0, centerY + ribbon.width + ribbon.amplitude)
        grad.addColorStop(0, `rgba(${r},${g},${b},0)`)
        grad.addColorStop(0.3, `rgba(${r},${g},${b},${ribbon.opacity})`)
        grad.addColorStop(0.5, `rgba(${r},${g},${b},${ribbon.opacity * 1.4})`)
        grad.addColorStop(0.7, `rgba(${r},${g},${b},${ribbon.opacity})`)
        grad.addColorStop(1, `rgba(${r},${g},${b},0)`)

        ctx!.fillStyle = grad
        ctx!.fill()
      }

      animRef.current = requestAnimationFrame(draw)
    }

    animRef.current = requestAnimationFrame(draw)

    return () => {
      cancelAnimationFrame(animRef.current)
      window.removeEventListener('resize', resize)
    }
  }, [initRibbons])

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
      }}
    />
  )
}

export default function Screensaver() {
  const idle = useIdleTimer(IDLE_TIMEOUT_MS)
  const time = useClock()

  // Resolve accent-responsive colors at render time
  const accent = T.cyan
  const purple = T.purple

  return (
    <AnimatePresence>
      {idle && (
        <motion.div
          key="screensaver"
          data-testid="screensaver-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0, transition: { duration: 0.35, ease: 'easeIn' } }}
          transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 9000,
            overflow: 'hidden',
            cursor: 'none',
          }}
        >
          {/* ── Layer 0: Void ── */}
          <div
            style={{
              position: 'absolute',
              inset: 0,
              background: 'radial-gradient(ellipse at 50% 44%, #0A0F14 0%, #030405 100%)',
            }}
          />

          {/* ── Layer 1: Nebula gradients (accent-responsive) ── */}
          <div
            data-testid="screensaver-nebula"
            style={{
              position: 'absolute',
              inset: 0,
              animation: 'screensaver-void-pulse 22s ease-in-out infinite',
              background: `
                radial-gradient(ellipse 70% 52% at 12% 14%, ${hexToRgba(accent, 0.14)}  0%, transparent 100%),
                radial-gradient(ellipse 60% 46% at 88% 10%, ${hexToRgba(purple, 0.12)} 0%, transparent 100%),
                radial-gradient(ellipse 50% 44% at 52% 92%, ${hexToRgba(T.amber, 0.09)}  0%, transparent 100%),
                radial-gradient(ellipse 40% 38% at  4% 60%, ${hexToRgba(accent, 0.07)}  0%, transparent 100%),
                radial-gradient(ellipse 80% 32% at 50% 50%, rgba(0,0,0,0.28)       0%, transparent 100%)
              `,
            }}
          />

          {/* ── Layer 2: Perspective grid (accent-responsive) ── */}
          <div
            style={{
              position: 'absolute',
              inset: 0,
              backgroundImage: `
                linear-gradient(${hexToRgba(accent, 0.05)} 1px, transparent 1px),
                linear-gradient(90deg, ${hexToRgba(accent, 0.05)} 1px, transparent 1px)
              `,
              backgroundSize: '36px 36px',
              animation: 'grid-recede 4s linear infinite',
              maskImage: 'linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.4) 30%, rgba(0,0,0,0.7) 60%, transparent 100%)',
              WebkitMaskImage: 'linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.4) 30%, rgba(0,0,0,0.7) 60%, transparent 100%)',
            }}
          />

          {/* ── Layer 3: Aurora light ribbons ── */}
          <AuroraCanvas />

          {/* ── Layer 4: Central logo ── */}
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 24,
            }}
          >
            {/* Orbit rings */}
            <div style={{ position: 'relative', width: 180, height: 180, flexShrink: 0 }}>
              {/* Outer slow orbit ring */}
              <div
                style={{
                  position: 'absolute',
                  inset: -22,
                  borderRadius: '50%',
                  border: `0.5px solid ${hexToRgba(accent, 0.12)}`,
                  animation: 'screensaver-ring-orbit 45s linear infinite',
                }}
              >
                {/* Orbit dot */}
                <div
                  style={{
                    position: 'absolute',
                    top: -3,
                    left: '50%',
                    transform: 'translateX(-50%)',
                    width: 5,
                    height: 5,
                    borderRadius: '50%',
                    background: hexToRgba(accent, 0.70),
                    boxShadow: `0 0 8px ${hexToRgba(accent, 0.55)}`,
                  }}
                />
              </div>

              {/* Inner reverse orbit ring */}
              <div
                style={{
                  position: 'absolute',
                  inset: -6,
                  borderRadius: '50%',
                  border: `0.5px solid ${hexToRgba(purple, 0.10)}`,
                  animation: 'screensaver-ring-orbit-rev 30s linear infinite',
                }}
              >
                {/* Orbit dot */}
                <div
                  style={{
                    position: 'absolute',
                    bottom: -2,
                    left: '50%',
                    transform: 'translateX(-50%)',
                    width: 4,
                    height: 4,
                    borderRadius: '50%',
                    background: hexToRgba(purple, 0.65),
                    boxShadow: `0 0 6px ${hexToRgba(purple, 0.5)}`,
                  }}
                />
              </div>

              {/* Glow ring pulse */}
              <div
                style={{
                  position: 'absolute',
                  inset: -4,
                  borderRadius: '50%',
                  border: `1px solid ${hexToRgba(accent, 0.14)}`,
                  animation: 'idle-glow-ring 4s ease-out infinite',
                }}
              />

              {/* Logo — exact animated SVG, immutable geometry */}
              <motion.div
                style={{
                  width: '100%',
                  height: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  animation: 'screensaver-logo-breathe 8s ease-in-out infinite',
                }}
                data-testid="screensaver-logo"
              >
                <svg
                  id="icon-animated-dark"
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="-84 -36 240 240"
                  width={130}
                  height={130}
                >
                  <defs>
                    <style>
                      {`
                        @keyframes scanOrbitDark {
                          0%, 15%  { transform: rotate(0deg);   }
                          25%, 40% { transform: rotate(90deg);  }
                          50%, 65% { transform: rotate(180deg); }
                          75%, 90% { transform: rotate(270deg); }
                          100%     { transform: rotate(360deg); }
                        }
                        .sl-arm-dark {
                          transform-origin: 36px 84px;
                          animation: scanOrbitDark 6s cubic-bezier(0.8, 0, 0.2, 1) infinite;
                        }
                        @keyframes scanColorDark {
                          0%, 15%  { fill: #0068ff; }
                          25%, 40% { fill: #4af6c3; }
                          50%, 65% { fill: #fb8b1e; }
                          75%, 90% { fill: #ff433d; }
                          100%     { fill: #0068ff; }
                        }
                        .sl-core-scan-dark {
                          animation: scanColorDark 6s cubic-bezier(0.8, 0, 0.2, 1) infinite;
                        }
                      `}
                    </style>
                  </defs>
                  <g textRendering="geometricPrecision" shapeRendering="geometricPrecision">
                    <circle className="sl-core-scan-dark" cx="36" cy="84" r="36" />
                    <path   className="sl-arm-dark" fill="#FFFFFF" d="M 0,0 H 120 V 120 H 96 V 24 H 0 Z" />
                  </g>
                </svg>
              </motion.div>
            </div>

            {/* Product identity below logo */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5, duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
              style={{ textAlign: 'center' }}
            >
              <div
                style={{
                  fontFamily: FD,
                  fontSize: 13,
                  fontWeight: 700,
                  letterSpacing: '0.32em',
                  color: 'rgba(240,242,245,0.72)',
                  marginBottom: 6,
                  textTransform: 'uppercase',
                }}
              >
                BLUEPRINT
              </div>
              <div
                style={{
                  fontFamily: FD,
                  fontSize: 8,
                  fontWeight: 500,
                  letterSpacing: '0.16em',
                  color: 'rgba(240,242,245,0.28)',
                  textTransform: 'uppercase',
                }}
              >
                SPECIFIC LABS
              </div>
            </motion.div>
          </div>

          {/* ── Layer 5: Time display ── */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.8, duration: 0.6 }}
            data-testid="screensaver-clock"
            style={{
              position: 'absolute',
              bottom: 32,
              right: 36,
              fontFamily: FD,
              fontSize: 11,
              fontWeight: 400,
              letterSpacing: '0.12em',
              color: 'rgba(110,120,136,0.70)',
              userSelect: 'none',
            }}
          >
            {time}
          </motion.div>

          {/* ── Dismiss hint ── */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 2, duration: 0.6 }}
            style={{
              position: 'absolute',
              bottom: 32,
              left: '50%',
              transform: 'translateX(-50%)',
              fontFamily: FD,
              fontSize: 8,
              letterSpacing: '0.16em',
              color: 'rgba(110,120,136,0.35)',
              userSelect: 'none',
              textTransform: 'uppercase',
            }}
          >
            Move cursor to continue
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
