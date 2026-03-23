import { T, F, FD, FS, ELEVATION } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { useGuideStore } from '@/stores/guideStore'
import { motion } from 'framer-motion'
import { Command, Compass, PanelTop } from 'lucide-react'

const dragStyle   = { WebkitAppRegion: 'drag'    } as React.CSSProperties
const noDragStyle = { WebkitAppRegion: 'no-drag' } as React.CSSProperties
const isElectron  = !!(window as any).blueprint?.isElectron

const viewLabels: Record<string, string> = {
  dashboard:  'Projects',
  editor:     'Build',
  results:    'Analyze',
  datasets:   'Datasets',
  marketplace:'Blocks',
  settings:   'Settings',
  paper:      'Write',
  help:       'Help',
  monitor:    'Mission Control',
  research:   'Research',
}

export default function TopBar() {
  const { activeView } = useUIStore()
  const guideActive  = useGuideStore((s) => s.guideActive)
  const toggleGuide  = useGuideStore((s) => s.toggleGuide)

  return (
    <header
      style={{
        flexShrink: 0,
        zIndex: 40,
        overflow: 'visible',
        position: 'relative',
        background: `linear-gradient(180deg, ${T.surface2}f2 0%, ${T.surface1}ee 100%)`,
        borderBottom: `0.5px solid ${T.border}`,
        boxShadow: ELEVATION.panel,
        ...dragStyle,
      }}
    >
      {/* Hairline accent sweep at very top */}
      <div
        style={{
          position: 'absolute',
          top: 0, left: 0, right: 0,
          height: '0.5px',
          background: `linear-gradient(90deg, transparent 0%, var(--hue-glow) 30%, var(--hue-secondary) 70%, transparent 100%)`,
          opacity: 0.65,
          pointerEvents: 'none',
          overflow: 'hidden',
        }}
      >
        {/* Slow shimmer sweep */}
        <motion.div
          animate={{ x: ['-100%', '200%'] }}
          transition={{ duration: 8, repeat: Infinity, ease: 'linear' }}
          style={{
            position: 'absolute',
            top: 0, left: 0,
            width: '35%',
            height: '0.5px',
            background: `linear-gradient(90deg, transparent, ${T.cyan}, transparent)`,
            pointerEvents: 'none',
          }}
        />
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: isElectron ? '0 14px 0 80px' : '0 14px',
          height: 46,
          gap: 10,
        }}
      >
        {/* ── Exact original logotype, new framing only ── */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 0,
            flexShrink: 0,
            position: 'relative',
            ...noDragStyle,
          }}
        >
          {/* Left vertical accent bar */}
          <div
            style={{
              width: 2,
              height: 18,
              borderRadius: 999,
              background: `var(--hue-glow)`,
              opacity: 0.45,
              marginRight: 10,
              flexShrink: 0,
            }}
          />

          <div style={{ display: 'flex', alignItems: 'center', height: 26 }}>
            {/* Organic breathing glow — not harsh pulse */}
            <motion.div
              animate={{
                filter: [
                  `drop-shadow(0 0 0px rgba(62,232,196,0))`,
                  `drop-shadow(0 0 7px rgba(62,232,196,0.28))`,
                  `drop-shadow(0 0 0px rgba(62,232,196,0))`,
                ],
              }}
              transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
              style={{ display: 'flex', alignItems: 'center', height: '100%' }}
            >
              {/*
                EXACT original logotype SVG — geometry immutable.
                viewBox="0 0 760 160", same path, same circle, same text groups.
                Only the container/framing around it has changed.
              */}
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 760 160"
                style={{ height: '100%', width: 'auto' }}
                aria-label="Specific Labs — Blueprint"
              >
                <g textRendering="geometricPrecision" shapeRendering="geometricPrecision">
                  <g transform="translate(0, 20)">
                    <path fill={T.text} d="M 0,0 H 120 V 120 H 96 V 24 H 0 Z" />
                    <circle fill={T.cyan} cx="36" cy="84" r="36" />
                  </g>
                  <g transform="translate(160, 0)">
                    <text
                      x="-3" y="70"
                      style={{
                        fontFamily: FD,
                        fontWeight: 700,
                        fontSize: 72,
                        letterSpacing: '0.4em',
                        fill: T.text,
                      }}
                    >
                      SPECIFIC
                    </text>
                    <text
                      x="0" y="140"
                      style={{
                        fontFamily: FD,
                        fontWeight: 500,
                        fontSize: 72,
                        letterSpacing: '0.4em',
                        fill: T.text,
                      }}
                    >
                      LABS
                    </text>
                  </g>
                </g>
              </svg>
            </motion.div>
          </div>
        </div>

        <div style={{ flex: 1 }} />

        {/* Active view breadcrumb */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            borderRadius: 999,
            padding: '5px 10px',
            background: `${T.surface3}cc`,
            border: `0.5px solid ${T.border}`,
            ...noDragStyle,
          }}
        >
          <Compass size={12} color={T.cyan} />
          <span
            style={{
              fontFamily: F,
              fontSize: FS.xs,
              letterSpacing: '0.05em',
              color: T.sec,
            }}
          >
            {viewLabels[activeView] || activeView}
          </span>
        </div>

        {/* Guide toggle */}
        <button
          onClick={toggleGuide}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 5,
            borderRadius: 8,
            padding: '5px 9px',
            background: guideActive ? `${T.cyan}1e` : `${T.surface3}bb`,
            border: `0.5px solid ${guideActive ? `${T.cyan}55` : T.border}`,
            color: guideActive ? T.cyan : T.dim,
            fontFamily: F,
            fontSize: FS.xs,
            letterSpacing: '0.05em',
            cursor: 'pointer',
            transition: 'all 0.16s ease',
            ...noDragStyle,
          }}
        >
          <PanelTop size={11} />
          Guide
        </button>

        {/* Cmd+K hint — static, reveals on hover */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 5,
            borderRadius: 8,
            padding: '5px 9px',
            border: `0.5px solid ${T.border}`,
            background: `${T.surface3}88`,
            color: T.dim,
            fontFamily: F,
            fontSize: FS.xs,
            userSelect: 'none',
            ...noDragStyle,
          }}
        >
          <Command size={11} />
          <span style={{ fontFamily: "'JetBrains Mono','SF Mono',monospace", fontSize: FS.xxs }}>K</span>
        </div>
      </div>
    </header>
  )
}
