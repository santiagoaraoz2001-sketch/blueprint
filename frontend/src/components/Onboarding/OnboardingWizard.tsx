/**
 * OnboardingWizard — 8-step guided walkthrough triggered on first-ever session.
 * Highlights key UI elements with a spotlight overlay and instruction tooltips.
 */
import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { T, F, FS } from '@/lib/design-tokens'
import {
  Sparkles, LayoutTemplate, Move, GripHorizontal,
  Cable, Settings, Play, BarChart3, ChevronRight,
} from 'lucide-react'

const STORAGE_KEY = 'blueprint-onboarding-completed'

interface OnboardingStep {
  title: string
  description: string
  icon: React.ElementType
  accent: string
  /** CSS selector for the element to spotlight. null = no spotlight. */
  spotlightSelector: string | null
  /** Alignment of the tooltip relative to the spotlight */
  tooltipPosition: 'center' | 'bottom-right' | 'bottom-left' | 'top-center'
}

const STEPS: OnboardingStep[] = [
  {
    title: 'Welcome to Blueprint',
    description: 'Blueprint is a visual ML experiment workbench. Build pipelines by connecting blocks, run experiments locally, and analyze results — all from a single canvas.',
    icon: Sparkles,
    accent: T.cyan,
    spotlightSelector: null,
    tooltipPosition: 'center',
  },
  {
    title: 'Choose a Template',
    description: 'Start fast with pre-built pipeline templates. Each template is a complete workflow you can customize. Browse the gallery and pick one that matches your goal.',
    icon: LayoutTemplate,
    accent: '#6C9EFF',
    spotlightSelector: null,
    tooltipPosition: 'center',
  },
  {
    title: 'The Canvas',
    description: 'The canvas is your workspace. Each rectangle is a block — a step in your pipeline. Lines between blocks show data flow. Drag to pan, scroll to zoom.',
    icon: Move,
    accent: '#4af6c3',
    spotlightSelector: '[data-testid="pipeline-canvas"]',
    tooltipPosition: 'bottom-right',
  },
  {
    title: 'Add a Block',
    description: 'Open the block palette on the left sidebar. Browse 130+ blocks across categories like Data, Inference, Training, and Evaluation. Drag a block onto the canvas.',
    icon: GripHorizontal,
    accent: '#F97316',
    spotlightSelector: '[data-testid="block-library"]',
    tooltipPosition: 'bottom-right',
  },
  {
    title: 'Connect Blocks',
    description: 'Each block has input and output ports (the small circles on the edges). Drag from an output port to an input port to connect two blocks and define data flow.',
    icon: Cable,
    accent: '#A78BFA',
    spotlightSelector: '[data-testid="pipeline-canvas"]',
    tooltipPosition: 'bottom-left',
  },
  {
    title: 'Configure',
    description: 'Click any block to open its configuration panel on the right. Set model names, parameters, file paths, and other options specific to each block type.',
    icon: Settings,
    accent: '#FBBF24',
    spotlightSelector: '[data-testid="block-config"]',
    tooltipPosition: 'bottom-left',
  },
  {
    title: 'Run',
    description: 'When your pipeline is ready, hit the Run button in the toolbar. Blueprint executes blocks in order, showing real-time progress for each step.',
    icon: Play,
    accent: '#34D399',
    spotlightSelector: '[data-testid="run-controls"]',
    tooltipPosition: 'bottom-right',
  },
  {
    title: 'View Results',
    description: 'After a run completes, check the Results view for metrics, charts, and outputs. Compare runs side-by-side to find the best configuration.',
    icon: BarChart3,
    accent: '#B87EFF',
    spotlightSelector: null,
    tooltipPosition: 'center',
  },
]

export default function OnboardingWizard() {
  const [active, setActive] = useState(false)
  const [step, setStep] = useState(0)
  const [spotlightRect, setSpotlightRect] = useState<DOMRect | null>(null)

  // Wait for BOTH the StartScreen and WelcomeModal to be completed before showing.
  // Poll localStorage for both keys so we don't overlap with earlier onboarding steps.
  useEffect(() => {
    if (localStorage.getItem(STORAGE_KEY)) return // Already completed — never show again

    const check = () => {
      const onboarded = localStorage.getItem('blueprint-onboarded')
      // settingsStore persists hasSeenWelcome inside the 'blueprint-settings' key
      let welcomeDone = false
      try {
        const raw = localStorage.getItem('blueprint-settings')
        if (raw) {
          const parsed = JSON.parse(raw)
          welcomeDone = !!parsed?.state?.hasSeenWelcome
        }
      } catch { /* ignore */ }
      return !!(onboarded && welcomeDone)
    }

    // If both are already done (returning user who hasn't done the wizard), show immediately
    if (check()) {
      const timer = setTimeout(() => setActive(true), 600)
      return () => clearTimeout(timer)
    }

    // Otherwise poll until both are done
    const interval = setInterval(() => {
      if (check()) {
        clearInterval(interval)
        setTimeout(() => setActive(true), 600)
      }
    }, 500)
    return () => clearInterval(interval)
  }, [])

  // Update spotlight position when step changes
  useEffect(() => {
    if (!active) return
    const currentStep = STEPS[step]
    if (!currentStep.spotlightSelector) {
      setSpotlightRect(null)
      return
    }

    const updateRect = () => {
      const el = document.querySelector(currentStep.spotlightSelector!)
      if (el) {
        setSpotlightRect(el.getBoundingClientRect())
      } else {
        setSpotlightRect(null)
      }
    }

    updateRect()
    // Re-measure on resize
    window.addEventListener('resize', updateRect)
    return () => window.removeEventListener('resize', updateRect)
  }, [active, step])

  const handleNext = useCallback(() => {
    if (step < STEPS.length - 1) {
      setStep(step + 1)
    } else {
      handleFinish()
    }
  }, [step])

  const handleFinish = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, '1')
    setActive(false)
  }, [])

  if (!active) return null

  const currentStep = STEPS[step]
  const Icon = currentStep.icon
  const isLastStep = step === STEPS.length - 1
  const isCentered = !spotlightRect || currentStep.tooltipPosition === 'center'

  // Calculate tooltip position
  let tooltipStyle: React.CSSProperties = {}
  if (isCentered) {
    tooltipStyle = {
      position: 'fixed',
      top: '50%', left: '50%',
      transform: 'translate(-50%, -50%)',
    }
  } else if (spotlightRect) {
    const pad = 20
    if (currentStep.tooltipPosition === 'bottom-right') {
      tooltipStyle = {
        position: 'fixed',
        top: Math.min(spotlightRect.top + 40, window.innerHeight - 300),
        left: Math.min(spotlightRect.right + pad, window.innerWidth - 420),
      }
    } else if (currentStep.tooltipPosition === 'bottom-left') {
      tooltipStyle = {
        position: 'fixed',
        top: Math.min(spotlightRect.top + 40, window.innerHeight - 300),
        left: Math.max(spotlightRect.left - 420, pad),
      }
    } else if (currentStep.tooltipPosition === 'top-center') {
      tooltipStyle = {
        position: 'fixed',
        top: Math.max(spotlightRect.top - 200, pad),
        left: spotlightRect.left + spotlightRect.width / 2 - 200,
      }
    }
  }

  return (
    <AnimatePresence>
      <motion.div
        key="onboarding-overlay"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        style={{
          position: 'fixed', inset: 0, zIndex: 10002,
          pointerEvents: 'auto',
        }}
      >
        {/* Translucent overlay with spotlight cutout */}
        <svg
          width="100%"
          height="100%"
          style={{ position: 'absolute', inset: 0 }}
        >
          <defs>
            <mask id="onboarding-mask">
              <rect width="100%" height="100%" fill="white" />
              {spotlightRect && (
                <rect
                  x={spotlightRect.left - 8}
                  y={spotlightRect.top - 8}
                  width={spotlightRect.width + 16}
                  height={spotlightRect.height + 16}
                  rx={8}
                  fill="black"
                />
              )}
            </mask>
          </defs>
          <rect
            width="100%"
            height="100%"
            fill="rgba(0, 0, 0, 0.65)"
            mask="url(#onboarding-mask)"
          />
          {/* Spotlight border glow */}
          {spotlightRect && (
            <rect
              x={spotlightRect.left - 8}
              y={spotlightRect.top - 8}
              width={spotlightRect.width + 16}
              height={spotlightRect.height + 16}
              rx={8}
              fill="none"
              stroke={currentStep.accent}
              strokeWidth={2}
              opacity={0.6}
            />
          )}
        </svg>

        {/* Tooltip card */}
        <motion.div
          key={`step-${step}`}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -12 }}
          transition={{ duration: 0.25 }}
          style={{
            ...tooltipStyle,
            width: 400,
            background: `linear-gradient(180deg, ${T.surface3} 0%, ${T.surface1} 100%)`,
            border: `1px solid ${T.borderHi}`,
            borderTop: `2px solid ${currentStep.accent}`,
            boxShadow: `0 16px 48px rgba(0,0,0,0.5), 0 0 20px ${currentStep.accent}20`,
            zIndex: 10003,
            overflow: 'hidden',
          }}
        >
          {/* Content */}
          <div style={{ padding: '20px 24px 16px' }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10,
            }}>
              <div style={{
                width: 28, height: 28,
                background: `${currentStep.accent}15`,
                border: `1px solid ${currentStep.accent}30`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                borderRadius: 6,
              }}>
                <Icon size={14} color={currentStep.accent} />
              </div>
              <h3 style={{
                fontFamily: F, fontSize: 16, fontWeight: 700,
                color: T.text, margin: 0, letterSpacing: '0.03em',
              }}>
                {currentStep.title}
              </h3>
            </div>
            <p style={{
              fontFamily: F, fontSize: FS.sm, color: T.sec,
              lineHeight: 1.6, margin: 0,
            }}>
              {currentStep.description}
            </p>
          </div>

          {/* Footer */}
          <div style={{
            padding: '10px 24px 16px',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          }}>
            {/* Progress dots */}
            <div style={{ display: 'flex', gap: 5 }}>
              {STEPS.map((_, i) => (
                <div
                  key={i}
                  style={{
                    width: i === step ? 16 : 6, height: 6,
                    borderRadius: 3,
                    background: i === step ? currentStep.accent : `${T.dim}40`,
                    transition: 'all 0.2s',
                  }}
                />
              ))}
            </div>

            {/* Buttons */}
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={handleFinish}
                style={{
                  padding: '5px 12px',
                  background: 'none', border: `1px solid ${T.border}`,
                  color: T.dim, fontFamily: F, fontSize: FS.xs,
                  fontWeight: 600, letterSpacing: '0.06em',
                  cursor: 'pointer',
                }}
              >
                SKIP
              </button>
              <motion.button
                onClick={handleNext}
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                style={{
                  padding: '5px 14px',
                  background: `${currentStep.accent}18`,
                  border: `1px solid ${currentStep.accent}50`,
                  color: currentStep.accent,
                  fontFamily: F, fontSize: FS.xs, fontWeight: 700,
                  letterSpacing: '0.08em', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 4,
                }}
              >
                {isLastStep ? 'FINISH' : 'NEXT'}
                {!isLastStep && <ChevronRight size={12} />}
              </motion.button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
