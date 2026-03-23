import { T, F, FD } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { useGuideStore } from '@/stores/guideStore'
import { motion } from 'framer-motion'

// Electron drag region style (not in CSSProperties type)
const dragStyle = { WebkitAppRegion: 'drag' } as React.CSSProperties
const noDragStyle = { WebkitAppRegion: 'no-drag' } as React.CSSProperties

// Detect Electron environment for traffic light padding
const isElectron = !!(window as any).blueprint?.isElectron

const viewLabels: Record<string, string> = {
  dashboard: 'PROJECTS',
  editor: 'PIPELINE EDITOR',
  results: 'RESULTS',
  datasets: 'DATASETS',
  marketplace: 'BLOCKS',
  settings: 'SETTINGS',
  paper: 'PAPER',
  help: 'HELP',
}

export default function TopBar() {
  const { activeView } = useUIStore()
  const guideActive = useGuideStore((s) => s.guideActive)
  const toggleGuide = useGuideStore((s) => s.toggleGuide)

  return (
    <header
      style={{
        flexShrink: 0,
        zIndex: 40,
        overflow: 'visible',
        position: 'relative',
        background: `linear-gradient(180deg, ${T.surface3} 0%, ${T.surface1} 100%)`,
        borderBottom: `1px solid ${T.borderHi}`,
        ...dragStyle,
      }}
    >
      {/* Cyan top-line accent — brand nominal state */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: 1,
          background: `linear-gradient(90deg, transparent 0%, ${T.cyan}70 20%, ${T.cyan}40 60%, transparent 100%)`,
          pointerEvents: 'none',
          overflow: 'hidden',
        }}
      >
        {/* Animated flowing accent line */}
        <motion.div
          animate={{ x: ['-100%', '200%'] }}
          transition={{ duration: 4, repeat: Infinity, ease: 'linear' }}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '40%',
            height: 1,
            background: `linear-gradient(90deg, transparent, ${T.cyan}, transparent)`,
            pointerEvents: 'none',
          }}
        />
      </div>

      {/* Tier 1 — Logo, product name, view label, status */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: isElectron ? '0 14px 0 80px' : '0 14px',
          height: 46,
          gap: 10,
        }}
      >
        {/* LEFT — logo mark + wordmark + product subtitle */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          {/* Specific Labs logo mark + wordmark */}
          {/* Specific Labs unified SVG logo */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              height: 28,
              ...noDragStyle,
            }}
          >
            {/* Animated glow wrapper for the logomark portion */}
            <motion.div
              animate={{
                filter: [
                  'drop-shadow(0 0 2px rgba(74, 246, 195, 0))',
                  'drop-shadow(0 0 8px rgba(74, 246, 195, 0.4))',
                  'drop-shadow(0 0 2px rgba(74, 246, 195, 0))',
                ],
              }}
              transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
              style={{ display: 'flex', alignItems: 'center', height: '100%' }}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 760 160"
                style={{ height: '100%', width: 'auto' }}
              >
                <g textRendering="geometricPrecision" shapeRendering="geometricPrecision">
                  {/* Logomark */}
                  <g transform="translate(0, 20)">
                    <path fill={T.text} d="M 0,0 H 120 V 120 H 96 V 24 H 0 Z" />
                    <circle fill={T.cyan} cx="36" cy="84" r="36" />
                  </g>
                  {/* Wordmark */}
                  <g transform="translate(160, 0)">
                    <text x="-3" y="70" style={{ fontFamily: FD, fontWeight: 700, fontSize: 72, letterSpacing: '0.4em', fill: T.text }}>SPECIFIC</text>
                    <text x="0" y="140" style={{ fontFamily: FD, fontWeight: 500, fontSize: 72, letterSpacing: '0.4em', fill: T.text }}>LABS</text>
                  </g>
                </g>
              </svg>
            </motion.div>
          </div>

          {/* Product subtitle — separated by border */}
          <div
            style={{
              borderLeft: `1px solid ${T.borderHi}`,
              paddingLeft: 10,
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <motion.span
              animate={{ opacity: [0.5, 0.8, 0.5] }}
              transition={{ duration: 3, repeat: Infinity }}
              style={{
                fontFamily: FD,
                fontSize: 15,
                letterSpacing: '0.18em',
                color: T.dim,
                whiteSpace: 'nowrap',
                lineHeight: 1,
                fontWeight: 500,
              }}
            >
              BLUEPRINT
            </motion.span>
          </div>

          {/* Connection badge */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              background: `${T.cyan}12`,
              border: `1px solid ${T.cyan}35`,
              padding: '2px 6px',
              flexShrink: 0,
              ...noDragStyle,
            }}
          >
            <div style={{ position: 'relative', width: 5, height: 5, flexShrink: 0 }}>
              <div
                style={{
                  width: 5,
                  height: 5,
                  borderRadius: '50%',
                  background: T.cyan,
                }}
              />
            </div>
            <span
              style={{
                fontSize: 6.5,
                color: T.cyan,
                fontFamily: F,
                fontWeight: 900,
                letterSpacing: '0.1em',
                lineHeight: 1,
              }}
            >
              LOCAL
            </span>
          </div>
        </div>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Current view label */}
        <span
          style={{
            fontFamily: FD,
            fontSize: 8,
            fontWeight: 700,
            color: T.cyan,
            letterSpacing: '0.18em',
            whiteSpace: 'nowrap',
            ...noDragStyle,
          }}
        >
          {viewLabels[activeView] || activeView.toUpperCase()}
        </span>

        {/* GUIDE toggle */}
        <button
          onClick={toggleGuide}
          style={{
            fontSize: 6,
            letterSpacing: '0.14em',
            fontWeight: 900,
            fontFamily: F,
            background: guideActive ? `${T.cyan}18` : T.surface5,
            border: guideActive ? `1px solid ${T.cyan}60` : `1px solid ${T.borderHi}`,
            color: guideActive ? T.cyan : T.dim,
            padding: '2px 7px',
            cursor: 'pointer',
            lineHeight: 1,
            ...noDragStyle,
          }}
        >
          GUIDE
        </button>
      </div>
    </header>
  )
}
