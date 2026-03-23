import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { FD } from '@/lib/design-tokens'

const CYAN = '#4af6c3'
const BG = '#000000'

interface SplashScreenProps {
  children: React.ReactNode
}

export default function SplashScreen({ children }: SplashScreenProps) {
  const [ready, setReady] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    let cancelled = false
    let attempts = 0
    const maxAttempts = 10 // 5 seconds at 500ms intervals

    const check = async () => {
      try {
        const res = await fetch('/api/health', { signal: AbortSignal.timeout(2000) })
        if (!cancelled && res.ok) {
          setReady(true)
          return
        }
      } catch {
        // Backend not ready yet
      }

      attempts++
      if (attempts >= maxAttempts) {
        // Timeout — show app anyway (offline mode)
        if (!cancelled) setReady(true)
        return
      }

      if (!cancelled) {
        setTimeout(check, 500)
      }
    }

    check()

    return () => {
      cancelled = true
    }
  }, [])

  // Auto-dismiss after ready + brief hold for the exit animation to feel good
  useEffect(() => {
    if (ready) {
      const timer = setTimeout(() => setDismissed(true), 600)
      return () => clearTimeout(timer)
    }
  }, [ready])

  if (dismissed) return <>{children}</>

  return (
    <>
      {/* The app is always mounted underneath (for pre-loading) */}
      <div style={{ visibility: dismissed ? 'visible' : 'hidden', height: '100%' }}>
        {children}
      </div>

      {/* Splash overlay */}
      <AnimatePresence>
        {!dismissed && (
          <motion.div
            key="splash"
            initial={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5, ease: 'easeInOut' }}
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: 99999,
              background: BG,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 28,
            }}
          >
            {/* Animated logo */}
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            >
              <svg
                id="icon-animated-dark"
                xmlns="http://www.w3.org/2000/svg"
                viewBox="-84 -36 240 240"
                width={80}
                height={80}
                style={{
                  filter: 'drop-shadow(0 0 12px rgba(74, 246, 195, 0.2))',
                }}
              >
                <defs>
                  <style>
                    {`
                      @keyframes scanOrbitDark {
                          0%, 15% { transform: rotate(0deg); }
                          25%, 40% { transform: rotate(90deg); }
                          50%, 65% { transform: rotate(180deg); }
                          75%, 90% { transform: rotate(270deg); }
                          100% { transform: rotate(360deg); }
                      }
                      .sl-arm-dark {
                          transform-origin: 36px 84px;
                          animation: scanOrbitDark 6s cubic-bezier(0.8, 0, 0.2, 1) infinite;
                      }
                      @keyframes scanColorDark {
                          0%, 15% { fill: #0068ff; }
                          25%, 40% { fill: #4af6c3; }
                          50%, 65% { fill: #fb8b1e; }
                          75%, 90% { fill: #ff433d; }
                          100% { fill: #0068ff; }
                      }
                      .sl-core-scan-dark {
                          animation: scanColorDark 6s cubic-bezier(0.8, 0, 0.2, 1) infinite;
                      }
                    `}
                  </style>
                </defs>
                <g textRendering="geometricPrecision" shapeRendering="geometricPrecision">
                  <circle className="sl-core-scan-dark" cx="36" cy="84" r="36" />
                  <path className="sl-arm-dark" fill="#FFFFFF" d="M 0,0 H 120 V 120 H 96 V 24 H 0 Z" />
                </g>
              </svg>
            </motion.div>

            {/* Product name */}
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3, duration: 0.5 }}
              style={{ textAlign: 'center' }}
            >
              <div
                style={{
                  fontFamily: FD,
                  fontSize: 16,
                  fontWeight: 700,
                  letterSpacing: '0.28em',
                  color: '#FFFFFF',
                  marginBottom: 6,
                }}
              >
                BLUEPRINT
              </div>
              <div
                style={{
                  fontFamily: FD,
                  fontSize: 9,
                  fontWeight: 500,
                  letterSpacing: '0.18em',
                  color: '#666666',
                }}
              >
                SPECIFIC LABS
              </div>
            </motion.div>

            {/* Loading indicator */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.6 }}
              style={{
                display: 'flex',
                gap: 6,
                alignItems: 'center',
              }}
            >
              {[0, 1, 2].map((i) => (
                <motion.div
                  key={i}
                  animate={{
                    opacity: [0.2, 1, 0.2],
                    scale: [0.8, 1.1, 0.8],
                  }}
                  transition={{
                    duration: 1.2,
                    repeat: Infinity,
                    delay: i * 0.2,
                    ease: 'easeInOut',
                  }}
                  style={{
                    width: 4,
                    height: 4,
                    borderRadius: '50%',
                    background: ready ? CYAN : '#444444',
                    transition: 'background 0.3s ease',
                  }}
                />
              ))}
            </motion.div>

            {/* Status text */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.5 }}
              transition={{ delay: 1 }}
              style={{
                position: 'absolute',
                bottom: 40,
                fontFamily: FD,
                fontSize: 7,
                letterSpacing: '0.14em',
                color: '#444444',
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
