import { useMemo, useEffect, useState } from 'react'
import { T } from '@/lib/design-tokens'
import { useSettingsStore } from '@/stores/settingsStore'
import TopBar from './TopBar'
import GuideBar from '@/components/shared/GuideBar'
import Sidebar from './Sidebar'
import StatusBar from './StatusBar'

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() =>
    typeof window !== 'undefined'
      ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
      : false,
  )

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  return reduced
}

interface AppShellProps {
  children: React.ReactNode
}

function AmbientNebula() {
  const stars = useMemo(
    () =>
      Array.from({ length: 24 }, (_, i) => ({
        id: i,
        left: `${Math.random() * 100}%`,
        top: `${Math.random() * 100}%`,
        delay: Math.random() * 6,
        duration: 10 + Math.random() * 10,
        size: 1 + Math.random() * 2,
      })),
    [],
  )

  return (
    <div style={{ position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0 }}>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background:
            'radial-gradient(circle at 12% 14%, rgba(111,178,255,0.18), transparent 38%), radial-gradient(circle at 88% 12%, rgba(73,217,203,0.16), transparent 42%), radial-gradient(circle at 50% 82%, rgba(228,147,198,0.14), transparent 46%)',
          animation: 'nebula-pulse 8s ease-in-out infinite',
        }}
      />
      {stars.map((s) => (
        <div
          key={s.id}
          style={{
            position: 'absolute',
            left: s.left,
            top: s.top,
            width: s.size,
            height: s.size,
            borderRadius: '50%',
            background: 'rgba(248,249,255,0.75)',
            animation: `pulse ${s.duration}s ${s.delay}s ease-in-out infinite`,
          }}
        />
      ))}
    </div>
  )
}

export default function AppShell({ children }: AppShellProps) {
  const theme = useSettingsStore((s) => s.theme)
  const prefersReducedMotion = useReducedMotion()

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
        background: `linear-gradient(180deg, ${T.bgAlt} 0%, ${T.bg} 100%)`,
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      {!prefersReducedMotion && <AmbientNebula />}

      <div style={{ position: 'relative', zIndex: 2, display: 'flex', flexDirection: 'column', height: '100%' }}>
        <TopBar />
        <GuideBar />
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          <Sidebar />
          <main
            style={{
              flex: 1,
              overflow: 'auto',
              background: 'transparent',
              position: 'relative',
            }}
          >
            {children}
          </main>
        </div>
        <StatusBar />
      </div>
    </div>
  )
}
