import { T, F, FD, FS, ELEVATION } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { useGuideStore } from '@/stores/guideStore'
import { motion } from 'framer-motion'
import { Command, Compass, PanelTop } from 'lucide-react'

const dragStyle = { WebkitAppRegion: 'drag' } as React.CSSProperties
const noDragStyle = { WebkitAppRegion: 'no-drag' } as React.CSSProperties
const isElectron = !!(window as any).blueprint?.isElectron

const viewLabels: Record<string, string> = {
  dashboard: 'Projects',
  editor: 'Build',
  results: 'Analyze',
  datasets: 'Datasets',
  marketplace: 'Blocks',
  settings: 'Settings',
  paper: 'Write',
  help: 'Help',
  monitor: 'Mission Control',
  research: 'Research',
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
        background: `linear-gradient(180deg, ${T.surface3}f0 0%, ${T.surface1}e8 100%)`,
        borderBottom: `1px solid ${T.borderHi}`,
        boxShadow: ELEVATION.panel,
        ...dragStyle,
      }}
    >
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: 1,
          background: `linear-gradient(90deg, transparent 0%, var(--hue-glow) 28%, var(--hue-secondary) 72%, transparent 100%)`,
          pointerEvents: 'none',
          overflow: 'hidden',
        }}
      >
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

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: isElectron ? '8px 14px 8px 80px' : '8px 14px',
          height: 54,
          gap: 12,
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            flexShrink: 0,
            border: `1px solid ${T.border}`,
            background: `${T.surface2}e8`,
            borderRadius: 12,
            padding: '6px 10px',
            boxShadow: `0 0 24px ${T.cyan}20`,
            ...noDragStyle,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', height: 30 }}>
            <motion.div
              animate={{
                filter: [
                  'drop-shadow(0 0 2px rgba(80, 216, 192, 0))',
                  'drop-shadow(0 0 8px rgba(80, 216, 192, 0.32))',
                  'drop-shadow(0 0 2px rgba(80, 216, 192, 0))',
                ],
              }}
              transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
              style={{ display: 'flex', alignItems: 'center', height: '100%' }}
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 160" style={{ height: '100%', width: 'auto' }}>
                <g textRendering="geometricPrecision" shapeRendering="geometricPrecision">
                  <g transform="translate(0, 20)">
                    <path fill={T.text} d="M 0,0 H 120 V 120 H 96 V 24 H 0 Z" />
                    <circle fill={T.cyan} cx="36" cy="84" r="36" />
                  </g>
                  <g transform="translate(160, 0)">
                    <text x="-3" y="70" style={{ fontFamily: FD, fontWeight: 700, fontSize: 72, letterSpacing: '0.4em', fill: T.text }}>SPECIFIC</text>
                    <text x="0" y="140" style={{ fontFamily: FD, fontWeight: 500, fontSize: 72, letterSpacing: '0.4em', fill: T.text }}>LABS</text>
                  </g>
                </g>
              </svg>
            </motion.div>
          </div>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
            Blueprint
          </span>
        </div>

        <div style={{ flex: 1 }} />

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, border: `1px solid ${T.border}`, background: `${T.surface2}d8`, borderRadius: 999, padding: '6px 10px', ...noDragStyle }}>
          <Compass size={14} color={T.cyan} />
          <span style={{ fontFamily: F, fontSize: FS.xs, letterSpacing: '0.06em', color: T.text }}>
            {viewLabels[activeView] || activeView}
          </span>
        </div>

        <button
          onClick={toggleGuide}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            borderRadius: 10,
            padding: '6px 10px',
            background: guideActive ? `${T.cyan}22` : `${T.surface3}cc`,
            border: `1px solid ${guideActive ? `${T.cyan}66` : T.border}`,
            color: guideActive ? T.cyan : T.dim,
            fontFamily: F,
            fontSize: FS.xs,
            letterSpacing: '0.06em',
            cursor: 'pointer',
            ...noDragStyle,
          }}
        >
          <PanelTop size={12} />
          Guide
        </button>

        <motion.div
          initial={false}
          animate={{ opacity: [0.5, 1, 0.5] }}
          transition={{ duration: 2.5, repeat: Infinity }}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            borderRadius: 10,
            padding: '6px 10px',
            border: `1px solid ${T.border}`,
            background: `${T.surface3}cc`,
            color: T.dim,
            fontFamily: F,
            fontSize: FS.xs,
            ...noDragStyle,
          }}
        >
          <Command size={12} />
          Cmd/Ctrl+K
        </motion.div>
      </div>
    </header>
  )
}
