import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { T, F, FS, FD } from '@/lib/design-tokens'
import { GitBranch, Play, BarChart3 } from 'lucide-react'

const steps = [
  {
    icon: GitBranch,
    title: 'BUILD PIPELINES',
    description: 'Drag blocks from the library and connect them to create ML experiment workflows. 118 blocks across 9 categories.',
    accent: '#4af6c3',
  },
  {
    icon: Play,
    title: 'RUN EXPERIMENTS',
    description: 'Execute pipelines with real-time progress tracking. Monitor each block as it processes data.',
    accent: '#6C9EFF',
  },
  {
    icon: BarChart3,
    title: 'ANALYZE RESULTS',
    description: 'Compare metrics across runs, visualize trends, and identify the best configurations.',
    accent: '#B87EFF',
  },
]

export default function StartScreen() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (!localStorage.getItem('blueprint-onboarded')) {
      setVisible(true)
    }
  }, [])

  const dismiss = () => {
    localStorage.setItem('blueprint-onboarded', '1')
    setVisible(false)
  }

  return (
    <AnimatePresence mode="wait">
      {visible && (
        <motion.div
          key="start-screen-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 10001,
            background: T.shadowHeavy,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.92, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            style={{
              width: 520,
              background: `linear-gradient(180deg, ${T.surface3} 0%, ${T.surface1} 100%)`,
              border: `1px solid ${T.borderHi}`,
              boxShadow: `0 24px 64px ${T.shadowHeavy}`,
              overflow: 'hidden',
            }}
          >
            {/* Top accent */}
            <div
              style={{
                height: 1,
                background: `linear-gradient(90deg, transparent, ${T.cyan}80, transparent)`,
              }}
            />

            {/* Header */}
            <div style={{ padding: '28px 32px 20px', textAlign: 'center' }}>
              {/* Logo */}
              <motion.svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 120 120"
                width="36"
                height="36"
                style={{ margin: '0 auto 14px', display: 'block' }}
                animate={{
                  y: [0, -4, 0],
                  filter: [
                    'drop-shadow(0 0 4px rgba(74, 246, 195, 0.0))',
                    'drop-shadow(0 0 16px rgba(74, 246, 195, 0.5))',
                    'drop-shadow(0 0 4px rgba(74, 246, 195, 0.0))',
                  ],
                }}
                transition={{ duration: 2.5, repeat: Infinity, ease: 'easeInOut' }}
              >
                <path fill={T.text} d="M 0,0 H 120 V 120 H 96 V 24 H 0 Z" />
                <circle fill={T.cyan} cx="36" cy="84" r="36" />
              </motion.svg>

              <h1
                style={{
                  fontFamily: FD,
                  fontSize: 18,
                  fontWeight: 700,
                  color: T.text,
                  letterSpacing: '0.14em',
                  margin: '0 0 6px',
                }}
              >
                BLUEPRINT
              </h1>
              <p
                style={{
                  fontFamily: F,
                  fontSize: FS.md,
                  color: T.sec,
                  margin: 0,
                  lineHeight: 1.5,
                }}
              >
                ML Experiment Workbench for Apple Silicon
              </p>
            </div>

            {/* Steps */}
            <div style={{ padding: '0 32px 24px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {steps.map((step, i) => {
                const Icon = step.icon
                return (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 + i * 0.12, duration: 0.4 }}
                    whileHover={{ rotateX: -2, rotateY: 3, scale: 1.02 }}
                    style={{
                      perspective: 600,
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 12,
                      padding: '10px 12px',
                      background: T.surface1,
                      border: `1px solid ${T.border}`,
                      borderLeft: `2px solid ${step.accent}`,
                    }}
                  >
                    <Icon size={14} color={step.accent} style={{ flexShrink: 0, marginTop: 1 }} />
                    <div>
                      <span
                        style={{
                          fontFamily: F,
                          fontSize: FS.xs,
                          fontWeight: 900,
                          color: step.accent,
                          letterSpacing: '0.12em',
                          display: 'block',
                          marginBottom: 3,
                        }}
                      >
                        {step.title}
                      </span>
                      <span
                        style={{
                          fontFamily: F,
                          fontSize: FS.sm,
                          color: T.sec,
                          lineHeight: 1.4,
                        }}
                      >
                        {step.description}
                      </span>
                    </div>
                  </motion.div>
                )
              })}
            </div>

            {/* CTA */}
            <div
              style={{
                padding: '14px 32px 20px',
                borderTop: `1px solid ${T.border}`,
                textAlign: 'center',
              }}
            >
              <motion.button
                onClick={dismiss}
                whileHover={{ scale: 1.06, boxShadow: '0 0 24px rgba(74, 246, 195, 0.3)' }}
                whileTap={{ scale: 0.97 }}
                style={{
                  background: `${T.cyan}18`,
                  border: `1px solid ${T.cyan}60`,
                  color: T.cyan,
                  fontFamily: F,
                  fontSize: FS.sm,
                  fontWeight: 900,
                  letterSpacing: '0.14em',
                  padding: '8px 28px',
                  cursor: 'pointer',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = `${T.cyan}30` }}
                onMouseLeave={(e) => { e.currentTarget.style.background = `${T.cyan}18` }}
              >
                GET STARTED
              </motion.button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
