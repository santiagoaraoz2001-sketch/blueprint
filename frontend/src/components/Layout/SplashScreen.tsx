import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { FD } from '@/lib/design-tokens'

const CYAN = '#4af6c3'

interface SplashScreenProps {
  children: React.ReactNode
}

export default function SplashScreen({ children }: SplashScreenProps) {
  const [ready,     setReady]     = useState(false)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    let cancelled = false
    let attempts  = 0
    const maxAttempts = 10

    const check = async () => {
      try {
        const res = await fetch('/api/health', { signal: AbortSignal.timeout(2000) })
        if (!cancelled && res.ok) {
          setReady(true)
          return
        }
      } catch {
        // backend not ready yet
      }
      attempts++
      if (attempts >= maxAttempts) {
        if (!cancelled) setReady(true)
        return
      }
      if (!cancelled) setTimeout(check, 500)
    }

    check()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (ready) {
      const timer = setTimeout(() => setDismissed(true), 600)
      return () => clearTimeout(timer)
    }
  }, [ready])

  if (dismissed) return <>{children}</>

  return (
    <>
      <div style={{ visibility: dismissed ? 'visible' : 'hidden', height: '100%' }}>
        {children}
      </div>

      <AnimatePresence>
        {!dismissed && (
          <motion.div
            key="splash"
            initial={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.55, ease: 'easeInOut' }}
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: 99999,
              // Warmer deep void — not flat black
              background: 'radial-gradient(ellipse at 50% 44%, #0A0F14 0%, #030405 100%)',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 28,
            }}
          >
            {/* Ambient teal breathing glow behind logo */}
            <motion.div
              animate={{ opacity: [0.5, 1, 0.5], scale: [0.95, 1.06, 0.95] }}
              transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut' }}
              style={{
                position: 'absolute',
                width: 220,
                height: 220,
                borderRadius: '50%',
                background: 'radial-gradient(circle, rgba(62,232,196,0.07) 0%, transparent 70%)',
                pointerEvents: 'none',
              }}
            />
            {/* Secondary purple ambient */}
            <motion.div
              animate={{ opacity: [0.3, 0.7, 0.3], scale: [1, 1.08, 1] }}
              transition={{ duration: 8, repeat: Infinity, ease: 'easeInOut', delay: 1.5 }}
              style={{
                position: 'absolute',
                width: 280,
                height: 280,
                borderRadius: '50%',
                background: 'radial-gradient(circle, rgba(152,128,232,0.04) 0%, transparent 70%)',
                pointerEvents: 'none',
              }}
            />

            {/* Animated logo — exact SVG, immutable geometry */}
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
              style={{ position: 'relative', zIndex: 1 }}
            >
              <svg
                id="icon-animated-dark"
                xmlns="http://www.w3.org/2000/svg"
                viewBox="-84 -36 240 240"
                width={86}
                height={86}
                style={{
                  filter: 'drop-shadow(0 0 14px rgba(62,232,196,0.18))',
                  display: 'block',
                }}
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

            {/* Product name */}
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3, duration: 0.5 }}
              style={{ textAlign: 'center', position: 'relative', zIndex: 1 }}
            >
              <div
                style={{
                  fontFamily: FD,
                  fontSize: 18,
                  fontWeight: 700,
                  letterSpacing: '0.28em',
                  color: '#FFFFFF',
                  marginBottom: 7,
                  textTransform: 'uppercase',
                }}
              >
                BLUEPRINT
              </div>
              <div
                style={{
                  fontFamily: FD,
                  fontSize: 10,
                  fontWeight: 500,
                  letterSpacing: '0.22em',
                  color: 'rgba(255,255,255,0.32)',
                  textTransform: 'uppercase',
                }}
              >
                SPECIFIC LABS
              </div>
            </motion.div>

            {/* Loading dots */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.6 }}
              style={{
                display: 'flex',
                gap: 6,
                alignItems: 'center',
                position: 'relative',
                zIndex: 1,
              }}
            >
              {[0, 1, 2].map((i) => (
                <motion.div
                  key={i}
                  animate={{
                    opacity: [0.15, 1, 0.15],
                    scale:   [0.7, 1.1, 0.7],
                  }}
                  transition={{
                    duration: 1.2,
                    repeat: Infinity,
                    delay: i * 0.2,
                    ease: 'easeInOut',
                  }}
                  style={{
                    width: 3,
                    height: 3,
                    borderRadius: '50%',
                    background: ready ? CYAN : 'rgba(110,120,136,0.6)',
                    transition: 'background 0.35s ease',
                  }}
                />
              ))}
            </motion.div>

            {/* Status label */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.45 }}
              transition={{ delay: 1 }}
              style={{
                position: 'absolute',
                bottom: 38,
                fontFamily: FD,
                fontSize: 8,
                letterSpacing: '0.18em',
                color: 'rgba(110,120,136,0.7)',
                textTransform: 'uppercase',
              }}
            >
              {ready ? 'READY' : 'INITIALIZING'}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
