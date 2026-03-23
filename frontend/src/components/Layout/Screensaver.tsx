/**
 * Screensaver — Blueprint / Specific Labs
 *
 * Activates after 90 s of inactivity. Full-screen bioluminescent ambient field
 * with the exact original animated logo SVG at centre stage.
 *
 * Layers (back → front):
 *   0  Void background
 *   1  Deep nebula gradients (slow drift)
 *   2  Perspective grid (receding into depth)
 *   3  60 floating particles (framer-motion)
 *   4  Central logo presentation with orbit rings
 *   5  Time display
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { FD } from '@/lib/design-tokens'

const IDLE_TIMEOUT_MS = 90_000   // 90 s
const DISMISS_EVENTS  = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'wheel'] as const

// ── Particle seed (deterministic so no layout thrash on re-render) ──
function seedParticles(n: number) {
  // Simple LCG for deterministic pseudo-random
  let seed = 0xDEADBEEF
  const rand = () => {
    seed = (seed * 1664525 + 1013904223) & 0xFFFFFFFF
    return (seed >>> 0) / 0xFFFFFFFF
  }
  const accentColors = [
    'rgba(62,232,196,VAL)',    // teal
    'rgba(152,128,232,VAL)',   // purple
    'rgba(232,168,74,VAL)',    // amber
    'rgba(216,124,184,VAL)',   // pink
    'rgba(82,217,117,VAL)',    // green
    'rgba(240,242,245,VAL)',   // white
    'rgba(240,242,245,VAL)',   // white (more common)
    'rgba(240,242,245,VAL)',   // white
  ]
  return Array.from({ length: n }, (_, i) => {
    const col = accentColors[i % accentColors.length]
    const opacity = 0.20 + rand() * 0.55
    return {
      id:       i,
      left:     `${rand() * 100}%`,
      startY:   `${60 + rand() * 40}vh`,   // start in lower portion
      size:     0.8 + rand() * 2.4,
      color:    col.replace('VAL', opacity.toFixed(2)),
      duration: 22 + rand() * 38,
      delay:    -(rand() * 30),             // negative delay = pre-started
      driftX:   -14 + rand() * 28,
    }
  })
}

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
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
  })

  useEffect(() => {
    const tick = () => {
      const d = new Date()
      setTime(`${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`)
    }
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  return time
}

export default function Screensaver() {
  const idle       = useIdleTimer(IDLE_TIMEOUT_MS)
  const time       = useClock()
  const particles  = useMemo(() => seedParticles(60), [])

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

          {/* ── Layer 1: Nebula gradients ── */}
          <div
            data-testid="screensaver-nebula"
            style={{
              position: 'absolute',
              inset: 0,
              animation: 'screensaver-void-pulse 22s ease-in-out infinite',
              background: `
                radial-gradient(ellipse 70% 52% at 12% 14%, rgba(62,232,196,0.07)  0%, transparent 100%),
                radial-gradient(ellipse 60% 46% at 88% 10%, rgba(152,128,232,0.06) 0%, transparent 100%),
                radial-gradient(ellipse 50% 44% at 52% 92%, rgba(232,168,74,0.05)  0%, transparent 100%),
                radial-gradient(ellipse 40% 38% at  4% 60%, rgba(62,232,196,0.04)  0%, transparent 100%),
                radial-gradient(ellipse 80% 32% at 50% 50%, rgba(0,0,0,0.35)       0%, transparent 100%)
              `,
            }}
          />

          {/* ── Layer 2: Perspective grid ── */}
          <div
            style={{
              position: 'absolute',
              inset: 0,
              backgroundImage: `
                linear-gradient(rgba(62,232,196,0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(62,232,196,0.03) 1px, transparent 1px)
              `,
              backgroundSize: '36px 36px',
              animation: 'grid-recede 4s linear infinite',
              maskImage: 'linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.4) 30%, rgba(0,0,0,0.7) 60%, transparent 100%)',
              WebkitMaskImage: 'linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.4) 30%, rgba(0,0,0,0.7) 60%, transparent 100%)',
            }}
          />

          {/* ── Layer 3: Particle field ── */}
          {particles.map((p) => (
            <motion.div
              key={p.id}
              data-testid={p.id === 0 ? 'screensaver-particle' : undefined}
              style={{
                position: 'absolute',
                left: p.left,
                top: p.startY,
                width:  p.size,
                height: p.size,
                borderRadius: '50%',
                background: p.color,
                willChange: 'transform',
                ...(p.size > 2
                  ? { boxShadow: `0 0 ${p.size * 2}px ${p.color}` }
                  : {}),
              }}
              animate={{
                y:       [0, `-${100 + Math.random() * 30}vh`],
                x:       [0, p.driftX],
                opacity: [0, 1, 0.8, 0],
              }}
              transition={{
                duration: p.duration,
                delay:    p.delay,
                repeat:   Infinity,
                ease:     'linear',
              }}
            />
          ))}

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
                  border: '0.5px solid rgba(62,232,196,0.12)',
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
                    background: 'rgba(62,232,196,0.70)',
                    boxShadow: '0 0 8px rgba(62,232,196,0.55)',
                  }}
                />
              </div>

              {/* Inner reverse orbit ring */}
              <div
                style={{
                  position: 'absolute',
                  inset: -6,
                  borderRadius: '50%',
                  border: '0.5px solid rgba(152,128,232,0.10)',
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
                    background: 'rgba(152,128,232,0.65)',
                    boxShadow: '0 0 6px rgba(152,128,232,0.5)',
                  }}
                />
              </div>

              {/* Glow ring pulse */}
              <div
                style={{
                  position: 'absolute',
                  inset: -4,
                  borderRadius: '50%',
                  border: '1px solid rgba(62,232,196,0.14)',
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
