import { useEffect, useRef, useCallback, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Rocket, ChevronDown, ChevronUp, X, Lightbulb, CheckCircle2, ArrowRight, Sparkles } from 'lucide-react'
import { T, F, FD, FS } from '@/lib/design-tokens'
import { getMission } from '@/lib/missions'
import { useMissionStore } from '@/stores/missionStore'
import { usePipelineStore } from '@/stores/pipelineStore'

// ── Confetti Particle for celebration step ──────────────────────────────
function ConfettiParticles() {
  const particles = useMemo(() => {
    const colors = [T.cyan, T.green, T.amber, T.purple, T.pink, T.blue]
    return Array.from({ length: 24 }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      delay: Math.random() * 2,
      duration: 2 + Math.random() * 2,
      color: colors[i % colors.length],
      size: 3 + Math.random() * 4,
    }))
  }, [])

  return (
    <div style={{ position: 'absolute', inset: 0, overflow: 'hidden', pointerEvents: 'none', borderRadius: 12 }}>
      {particles.map((p) => (
        <motion.div
          key={p.id}
          initial={{ opacity: 0, y: -10, x: `${p.x}%`, scale: 0 }}
          animate={{
            opacity: [0, 1, 1, 0],
            y: ['-10%', '110%'],
            rotate: [0, 360 + Math.random() * 360],
            scale: [0, 1, 0.8, 0],
          }}
          transition={{
            duration: p.duration,
            delay: p.delay,
            repeat: Infinity,
            repeatDelay: Math.random() * 3,
            ease: 'easeOut',
          }}
          style={{
            position: 'absolute',
            left: `${p.x}%`,
            width: p.size,
            height: p.size,
            borderRadius: p.size > 5 ? 1 : '50%',
            background: p.color,
          }}
        />
      ))}
    </div>
  )
}

// ── Main MissionController ──────────────────────────────────────────────
export default function MissionController() {
  const {
    activeMissionId,
    currentStepIndex,
    completedMissions,
    isMinimized,
    hintVisible,
    startMission,
    advanceStep,
    completeMission,
    skipMission,
    toggleMinimize,
    showHint,
    hideHint,
  } = useMissionStore()

  const hintTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const validationIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const hasAutoStarted = useRef(false)

  // ── Auto-start first mission on first visit ──
  useEffect(() => {
    if (hasAutoStarted.current) return
    hasAutoStarted.current = true

    if (!activeMissionId && !completedMissions.includes('first_pipeline')) {
      startMission('first_pipeline')
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const mission = activeMissionId ? getMission(activeMissionId) : null
  const step = mission?.steps[currentStepIndex] ?? null
  const totalSteps = mission?.steps.length ?? 0
  const isCelebrate = step?.id === 'celebrate'
  const isLastStep = currentStepIndex === totalSteps - 1

  // ── Hint timer: show hint after 15s of no progress ──
  useEffect(() => {
    if (!step || step.isManual) return
    hideHint()

    hintTimerRef.current = setTimeout(() => {
      showHint()
    }, 15000)

    return () => {
      if (hintTimerRef.current) clearTimeout(hintTimerRef.current)
    }
  }, [currentStepIndex, step]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Auto-advance: poll validation every 500ms ──
  useEffect(() => {
    if (!step || step.isManual) {
      if (validationIntervalRef.current) clearInterval(validationIntervalRef.current)
      return
    }

    validationIntervalRef.current = setInterval(() => {
      const { nodes: currentNodes, edges: currentEdges } = usePipelineStore.getState()
      const passed = step.validate({ nodes: currentNodes, edges: currentEdges })
      if (passed) {
        advanceStep()
      }
    }, 500)

    return () => {
      if (validationIntervalRef.current) clearInterval(validationIntervalRef.current)
    }
  }, [step, advanceStep])

  // ── Manual step handlers ──
  const handleContinue = useCallback(() => {
    if (isLastStep) {
      completeMission()
    } else {
      advanceStep()
    }
  }, [isLastStep, completeMission, advanceStep])

  const handleSkip = useCallback(() => {
    skipMission()
  }, [skipMission])

  // ── Don't render if no active mission ──
  if (!mission || !step) return null

  const progressPercent = ((currentStepIndex) / (totalSteps - 1)) * 100

  // ── Minimized beacon/pill ──
  if (isMinimized) {
    return (
      <motion.button
        initial={{ opacity: 0, scale: 0.8, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.8, y: 20 }}
        onClick={toggleMinimize}
        style={{
          position: 'fixed',
          bottom: 20,
          right: 20,
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 16px',
          background: T.surface2,
          border: `1px solid ${T.cyan}40`,
          borderRadius: 20,
          color: T.cyan,
          fontFamily: F,
          fontSize: FS.sm,
          fontWeight: 600,
          letterSpacing: '0.06em',
          cursor: 'pointer',
          boxShadow: `0 4px 20px ${T.shadow}, 0 0 15px ${T.cyan}15`,
          backdropFilter: 'blur(12px)',
          transition: 'all 0.2s',
        }}
        whileHover={{ scale: 1.05, boxShadow: `0 4px 24px ${T.shadow}, 0 0 20px ${T.cyan}25` }}
        whileTap={{ scale: 0.97 }}
      >
        <motion.div
          animate={{ rotate: [0, 10, -10, 0] }}
          transition={{ duration: 2, repeat: Infinity, repeatDelay: 3 }}
        >
          <Rocket size={13} />
        </motion.div>
        <span>MISSION {currentStepIndex + 1}/{totalSteps}</span>
        <ChevronUp size={12} />
      </motion.button>
    )
  }

  // ── Full panel ──
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key="mission-panel"
        initial={{ opacity: 0, y: 40, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 40, scale: 0.95 }}
        transition={{ type: 'spring', damping: 26, stiffness: 300 }}
        style={{
          position: 'fixed',
          bottom: 20,
          right: 20,
          width: 340,
          zIndex: 9999,
          borderRadius: 12,
          overflow: 'hidden',
          background: T.surface1,
          border: `1px solid ${T.border}`,
          boxShadow: `0 8px 40px ${T.shadowHeavy}, 0 0 1px ${T.borderHi}, inset 0 1px 0 ${T.surface3}`,
          backdropFilter: 'blur(16px)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Celebration confetti overlay */}
        {isCelebrate && <ConfettiParticles />}

        {/* Progress bar (thin, top-edge) */}
        <div style={{ height: 2, background: T.surface3, position: 'relative', flexShrink: 0 }}>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${progressPercent}%` }}
            transition={{ type: 'spring', damping: 20, stiffness: 200 }}
            style={{
              height: '100%',
              background: isCelebrate
                ? `linear-gradient(90deg, ${T.cyan}, ${T.green}, ${T.amber})`
                : T.cyan,
              borderRadius: 1,
              boxShadow: `0 0 8px ${T.cyan}60`,
            }}
          />
        </div>

        {/* Header row */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '10px 14px 0 14px',
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div
              style={{
                width: 24,
                height: 24,
                borderRadius: 6,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: `${T.cyan}15`,
                border: `1px solid ${T.cyan}30`,
              }}
            >
              {isCelebrate ? (
                <motion.div animate={{ rotate: [0, 15, -15, 0], scale: [1, 1.2, 1] }} transition={{ duration: 1.5, repeat: Infinity }}>
                  <Sparkles size={13} color={T.cyan} />
                </motion.div>
              ) : (
                <Rocket size={13} color={T.cyan} />
              )}
            </div>
            <div>
              <div
                style={{
                  fontFamily: FD,
                  fontSize: FS.sm,
                  fontWeight: 700,
                  color: T.text,
                  letterSpacing: '0.06em',
                  lineHeight: 1.2,
                }}
              >
                {mission.title}
              </div>
              <div
                style={{
                  fontFamily: F,
                  fontSize: FS.xxs,
                  color: T.dim,
                  letterSpacing: '0.04em',
                  marginTop: 1,
                }}
              >
                {mission.subtitle}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <button
              onClick={toggleMinimize}
              style={{
                background: 'none',
                border: 'none',
                color: T.dim,
                cursor: 'pointer',
                padding: 4,
                display: 'flex',
                borderRadius: 4,
                transition: 'color 0.15s',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.color = T.sec }}
              onMouseLeave={(e) => { e.currentTarget.style.color = T.dim }}
              title="Minimize"
            >
              <ChevronDown size={14} />
            </button>
            <button
              onClick={handleSkip}
              style={{
                background: 'none',
                border: 'none',
                color: T.dim,
                cursor: 'pointer',
                padding: 4,
                display: 'flex',
                borderRadius: 4,
                transition: 'color 0.15s',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.color = T.red }}
              onMouseLeave={(e) => { e.currentTarget.style.color = T.dim }}
              title="Skip mission"
            >
              <X size={14} />
            </button>
          </div>
        </div>

        {/* Step counter */}
        <div
          style={{
            padding: '6px 14px 0 14px',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            flexShrink: 0,
          }}
        >
          <span
            style={{
              fontFamily: F,
              fontSize: FS.xxs,
              color: T.cyan,
              fontWeight: 700,
              letterSpacing: '0.08em',
            }}
          >
            STEP {currentStepIndex + 1} / {totalSteps}
          </span>

          {/* Step dots */}
          <div style={{ display: 'flex', gap: 3, marginLeft: 4 }}>
            {mission.steps.map((_, i) => (
              <div
                key={i}
                style={{
                  width: 5,
                  height: 5,
                  borderRadius: '50%',
                  background: i < currentStepIndex
                    ? T.cyan
                    : i === currentStepIndex
                      ? T.text
                      : T.surface4,
                  transition: 'all 0.3s',
                  boxShadow: i === currentStepIndex ? `0 0 6px ${T.cyan}40` : 'none',
                }}
              />
            ))}
          </div>
        </div>

        {/* Step content with AnimatePresence */}
        <div style={{ padding: '10px 14px 12px 14px', flex: 1, position: 'relative' }}>
          <AnimatePresence mode="wait">
            <motion.div
              key={step.id}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
            >
              {/* Step title */}
              <div
                style={{
                  fontFamily: FD,
                  fontSize: FS.md,
                  fontWeight: 700,
                  color: isCelebrate ? T.cyan : T.text,
                  marginBottom: 6,
                  lineHeight: 1.3,
                }}
              >
                {isCelebrate && (
                  <CheckCircle2
                    size={14}
                    color={T.green}
                    style={{ marginRight: 6, verticalAlign: 'middle', position: 'relative', top: -1 }}
                  />
                )}
                {step.title}
              </div>

              {/* Step description */}
              <div
                style={{
                  fontFamily: F,
                  fontSize: FS.xs,
                  color: T.sec,
                  lineHeight: 1.6,
                  letterSpacing: '0.02em',
                }}
              >
                {step.description}
              </div>

              {/* Hint section */}
              <AnimatePresence>
                {hintVisible && (
                  <motion.div
                    initial={{ opacity: 0, height: 0, marginTop: 0 }}
                    animate={{ opacity: 1, height: 'auto', marginTop: 10 }}
                    exit={{ opacity: 0, height: 0, marginTop: 0 }}
                    transition={{ duration: 0.3, ease: 'easeOut' }}
                    style={{ overflow: 'hidden' }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: 8,
                        padding: '8px 10px',
                        background: `${T.amber}08`,
                        border: `1px solid ${T.amber}20`,
                        borderRadius: 6,
                      }}
                    >
                      <Lightbulb size={12} color={T.amber} style={{ marginTop: 1, flexShrink: 0 }} />
                      <span
                        style={{
                          fontFamily: F,
                          fontSize: FS.xxs,
                          color: T.amber,
                          lineHeight: 1.5,
                          letterSpacing: '0.02em',
                        }}
                      >
                        {step.hint}
                      </span>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Manual step buttons */}
              {step.isManual && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.15, duration: 0.25 }}
                  style={{ marginTop: 14, display: 'flex', gap: 8, alignItems: 'center' }}
                >
                  <motion.button
                    onClick={handleContinue}
                    whileHover={{ scale: 1.03 }}
                    whileTap={{ scale: 0.97 }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '7px 16px',
                      background: isCelebrate
                        ? `linear-gradient(135deg, ${T.cyan}, ${T.green})`
                        : T.cyan,
                      border: 'none',
                      borderRadius: 6,
                      color: '#000',
                      fontFamily: F,
                      fontSize: FS.xs,
                      fontWeight: 700,
                      letterSpacing: '0.06em',
                      cursor: 'pointer',
                      boxShadow: `0 2px 12px ${T.cyan}30`,
                      transition: 'all 0.15s',
                    }}
                  >
                    {isLastStep ? (
                      <>
                        FINISH
                        <Sparkles size={12} />
                      </>
                    ) : currentStepIndex === 0 ? (
                      <>
                        START
                        <ArrowRight size={12} />
                      </>
                    ) : (
                      <>
                        CONTINUE
                        <ArrowRight size={12} />
                      </>
                    )}
                  </motion.button>

                  {!isCelebrate && (
                    <button
                      onClick={handleSkip}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: T.dim,
                        fontFamily: F,
                        fontSize: FS.xxs,
                        cursor: 'pointer',
                        letterSpacing: '0.04em',
                        textDecoration: 'underline',
                        textDecorationColor: `${T.dim}40`,
                        textUnderlineOffset: 3,
                        transition: 'color 0.15s',
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.color = T.sec }}
                      onMouseLeave={(e) => { e.currentTarget.style.color = T.dim }}
                    >
                      Skip mission
                    </button>
                  )}
                </motion.div>
              )}

              {/* For non-manual, non-hint-visible steps, show hint trigger link */}
              {!step.isManual && !hintVisible && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.3 }}
                  style={{ marginTop: 12 }}
                >
                  <button
                    onClick={() => showHint()}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: T.dim,
                      fontFamily: F,
                      fontSize: FS.xxs,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                      letterSpacing: '0.04em',
                      padding: 0,
                      transition: 'color 0.15s',
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.color = T.amber }}
                    onMouseLeave={(e) => { e.currentTarget.style.color = T.dim }}
                  >
                    <Lightbulb size={10} />
                    Show hint
                  </button>
                </motion.div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Footer: skip link (only on non-manual, non-celebrate steps) */}
        {!step.isManual && (
          <div
            style={{
              padding: '0 14px 10px 14px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexShrink: 0,
            }}
          >
            <button
              onClick={handleSkip}
              style={{
                background: 'none',
                border: 'none',
                color: T.dim,
                fontFamily: F,
                fontSize: FS.xxs,
                cursor: 'pointer',
                letterSpacing: '0.04em',
                textDecoration: 'underline',
                textDecorationColor: `${T.dim}30`,
                textUnderlineOffset: 3,
                padding: 0,
                transition: 'color 0.15s',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.color = T.sec }}
              onMouseLeave={(e) => { e.currentTarget.style.color = T.dim }}
            >
              Skip mission
            </button>

            {/* Waiting indicator */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                fontFamily: F,
                fontSize: FS.xxs,
                color: T.dim,
                letterSpacing: '0.04em',
              }}
            >
              <motion.div
                animate={{ opacity: [0.3, 1, 0.3] }}
                transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
                style={{
                  width: 5,
                  height: 5,
                  borderRadius: '50%',
                  background: T.cyan,
                }}
              />
              Waiting...
            </div>
          </div>
        )}

        {/* Celebration glow overlay */}
        {isCelebrate && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              borderRadius: 12,
              pointerEvents: 'none',
              boxShadow: `inset 0 0 40px ${T.cyan}10, 0 0 30px ${T.cyan}15`,
            }}
          />
        )}
      </motion.div>
    </AnimatePresence>
  )
}
