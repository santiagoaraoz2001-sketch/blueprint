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
        position: 'relative',
        background: `linear-gradient(180deg, ${T.surface2}ee 0%, ${T.surface1}d8 100%)`,
        borderBottom: `1px solid ${T.border}`,
        backdropFilter: 'blur(14px)',
        boxShadow: ELEVATION.panel,
        ...dragStyle,
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background:
            'linear-gradient(90deg, transparent 0%, rgba(73,217,203,0.15) 35%, rgba(111,178,255,0.18) 62%, transparent 100%)',
          pointerEvents: 'none',
        }}
      />
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: isElectron ? '10px 16px 10px 84px' : '10px 16px',
          gap: 12,
          position: 'relative',
          zIndex: 1,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, ...noDragStyle }}>
          <div
            style={{
              width: 28,
              height: 28,
              borderRadius: 9,
              background: `radial-gradient(circle at 28% 28%, ${T.cyan}, ${T.blue})`,
              boxShadow: `0 0 24px ${T.cyan}66`,
            }}
          />
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1 }}>
            <span style={{ fontFamily: FD, fontSize: FS.md, color: T.text, fontWeight: 600, letterSpacing: '0.04em' }}>
              BLUEPRINT
            </span>
            <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, letterSpacing: '0.08em' }}>
              local-first ml instrument
            </span>
          </div>
        </div>

        <div style={{ flex: 1 }} />

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            border: `1px solid ${T.borderHi}`,
            background: `${T.surface2}cc`,
            borderRadius: 999,
            padding: '6px 10px',
            color: T.sec,
            ...noDragStyle,
          }}
        >
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
