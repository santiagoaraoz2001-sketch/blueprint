import { useSettingsStore, type UiMode } from '@/stores/settingsStore'
import { motion, AnimatePresence } from 'framer-motion'
import { T, F, FS, FD } from '@/lib/design-tokens'
import { Layers, Rocket } from 'lucide-react'
import { useState, useEffect, useCallback } from 'react'

export default function WelcomeModal() {
  const hasSeenWelcome = useSettingsStore((s) => s.hasSeenWelcome)
  const setHasSeenWelcome = useSettingsStore((s) => s.setHasSeenWelcome)
  const setUiMode = useSettingsStore((s) => s.setUiMode)

  // Wait for StartScreen to be dismissed before showing
  const [startScreenDone, setStartScreenDone] = useState(
    () => !!localStorage.getItem('blueprint-onboarded'),
  )

  useEffect(() => {
    if (startScreenDone || hasSeenWelcome) return
    const interval = setInterval(() => {
      if (localStorage.getItem('blueprint-onboarded')) {
        setStartScreenDone(true)
        clearInterval(interval)
      }
    }, 500)
    return () => clearInterval(interval)
  }, [startScreenDone, hasSeenWelcome])

  const handleSelect = useCallback((mode: UiMode) => {
    setUiMode(mode)
    setHasSeenWelcome(true)
  }, [setUiMode, setHasSeenWelcome])

  // Keyboard shortcuts: 1 for Simple, 2 for Professional
  useEffect(() => {
    if (hasSeenWelcome || !startScreenDone) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === '1') handleSelect('simple')
      else if (e.key === '2') handleSelect('professional')
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [hasSeenWelcome, startScreenDone, handleSelect])

  if (hasSeenWelcome || !startScreenDone) return null

  const modeOptions: {
    mode: UiMode
    icon: React.ReactNode
    title: string
    description: string
    features: string[]
  }[] = [
    {
      mode: 'simple',
      icon: <Layers size={20} color={T.cyan} />,
      title: 'Simple',
      description: "I'm new to ML or want a clean workspace",
      features: [
        'Core block categories only',
        'Streamlined navigation',
        'Flat config — no inheritance',
      ],
    },
    {
      mode: 'professional',
      icon: <Rocket size={20} color={T.cyan} />,
      title: 'Professional',
      description: 'I know what I\'m doing, show me everything',
      features: [
        'All 11 block categories',
        'Paper writing & Workshop',
        'Config inheritance & custom blocks',
      ],
    },
  ]

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.3 }}
        role="dialog"
        aria-modal="true"
        aria-label="Welcome to Blueprint — choose your UI mode"
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 10002,
          background: T.shadowHeavy,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <motion.div
          initial={{ opacity: 0, y: 20, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.35, ease: 'easeOut', delay: 0.1 }}
          style={{
            width: 520,
            background: T.surface1,
            border: `1px solid ${T.borderHi}`,
            boxShadow: `0 16px 48px ${T.shadowHeavy}`,
            overflow: 'hidden',
          }}
        >
          {/* Header */}
          <div style={{
            padding: '24px 28px 16px',
            borderBottom: `1px solid ${T.border}`,
          }}>
            <div style={{
              fontFamily: FD,
              fontSize: FS.h3,
              fontWeight: 700,
              color: T.text,
              letterSpacing: '0.04em',
              marginBottom: 6,
            }}>
              WELCOME TO BLUEPRINT
            </div>
            <div style={{
              fontFamily: F,
              fontSize: FS.sm,
              color: T.dim,
              lineHeight: 1.5,
            }}>
              How would you like to start? You can change this anytime in Settings.
            </div>
          </div>

          {/* Mode options */}
          <div style={{ padding: '16px 28px 24px', display: 'flex', gap: 12 }}>
            {modeOptions.map((opt) => (
              <button
                key={opt.mode}
                onClick={() => handleSelect(opt.mode)}
                style={{
                  flex: 1,
                  padding: '16px',
                  background: T.surface2,
                  border: `1px solid ${T.border}`,
                  cursor: 'pointer',
                  outline: 'none',
                  borderRadius: 0,
                  textAlign: 'left',
                  transition: 'all 0.15s ease',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = T.cyan
                  e.currentTarget.style.background = `${T.cyan}08`
                  e.currentTarget.style.boxShadow = `0 0 8px ${T.cyan}30`
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = T.border
                  e.currentTarget.style.background = T.surface2
                  e.currentTarget.style.boxShadow = 'none'
                }}
              >
                <div style={{ marginBottom: 10 }}>{opt.icon}</div>
                <div style={{
                  fontFamily: F,
                  fontSize: FS.md,
                  fontWeight: 900,
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  color: T.text,
                  marginBottom: 6,
                }}>
                  {opt.title}
                </div>
                <div style={{
                  fontFamily: F,
                  fontSize: FS.xs,
                  color: T.sec,
                  lineHeight: 1.5,
                  marginBottom: 10,
                }}>
                  {opt.description}
                </div>
                <ul style={{ margin: 0, paddingLeft: 16 }}>
                  {opt.features.map((f, i) => (
                    <li key={i} style={{
                      fontFamily: F,
                      fontSize: FS.xxs,
                      color: T.dim,
                      lineHeight: 1.6,
                    }}>
                      {f}
                    </li>
                  ))}
                </ul>
              </button>
            ))}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
