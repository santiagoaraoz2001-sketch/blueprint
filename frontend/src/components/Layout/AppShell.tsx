import { useMemo, useEffect } from 'react'
import { T } from '@/lib/design-tokens'
import { useSettingsStore } from '@/stores/settingsStore'
import TopBar from './TopBar'
import GuideBar from '@/components/shared/GuideBar'
import Sidebar from './Sidebar'
import StatusBar from './StatusBar'

interface AppShellProps {
  children: React.ReactNode
}

// Floating ambient particles
function AmbientParticles() {
  const particles = useMemo(
    () =>
      Array.from({ length: 18 }, (_, i) => ({
        id: i,
        left: `${Math.random() * 100}%`,
        delay: Math.random() * 12,
        duration: 8 + Math.random() * 10,
        size: 1 + Math.random() * 1.5,
        opacity: 0.15 + Math.random() * 0.25,
      })),
    []
  )

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1,
        pointerEvents: 'none',
        overflow: 'hidden',
      }}
    >
      {particles.map((p) => (
        <div
          key={p.id}
          style={{
            position: 'absolute',
            bottom: '-10px',
            left: p.left,
            width: p.size,
            height: p.size,
            background: '#4af6c3',
            opacity: p.opacity,
            animation: `particle-drift ${p.duration}s ${p.delay}s linear infinite`,
          }}
        />
      ))}
    </div>
  )
}

export default function AppShell({ children }: AppShellProps) {
  const theme = useSettingsStore((s) => s.theme)

  // Sync body background with current theme
  useEffect(() => {
    document.body.style.background = T.bg
    document.body.style.color = T.text
  }, [theme])

  return (
    <div
      style={{
        width: '100vw',
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        background: T.bg,
        overflow: 'hidden',
      }}
    >
      <TopBar />
      <GuideBar />
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <Sidebar />
        <main
          style={{
            flex: 1,
            overflow: 'auto',
            background: T.bg,
          }}
        >
          {children}
        </main>
      </div>
      <StatusBar />

      {/* Ambient floating particles */}
      <AmbientParticles />

      {/* Vignette overlay — subtle in light mode */}
      <div
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 9999,
          pointerEvents: 'none',
          background:
            theme === 'dark'
              ? `radial-gradient(ellipse at center, transparent 50%, ${T.shadowHeavy} 100%)`
              : `radial-gradient(ellipse at center, transparent 60%, ${T.shadowLight} 100%)`,
        }}
      />

      {/* CRT scanline overlay — only in dark mode */}
      {theme === 'dark' && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 9999,
            pointerEvents: 'none',
            background:
              'repeating-linear-gradient(0deg, transparent, transparent 1px, rgba(255,255,255,0.015) 1px, rgba(255,255,255,0.015) 2px)',
          }}
        />
      )}
    </div>
  )
}
