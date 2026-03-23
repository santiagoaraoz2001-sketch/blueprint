import { useMemo, useEffect, useState } from 'react'
import { T } from '@/lib/design-tokens'
import { useSettingsStore } from '@/stores/settingsStore'
import TopBar      from './TopBar'
import GuideBar    from '@/components/shared/GuideBar'
import Sidebar     from './Sidebar'
import StatusBar   from './StatusBar'
import Screensaver from './Screensaver'

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

// ── Tiered star data: micro / small / medium ──────────────────────────────
function seedStars() {
  let seed = 0xC0FFEE42
  const rand = () => {
    seed = (seed * 1664525 + 1013904223) & 0xFFFFFFFF
    return (seed >>> 0) / 0xFFFFFFFF
  }

  const micro  = Array.from({ length: 28 }, (_, i) => ({
    id: i, tier: 'micro' as const,
    left: `${rand() * 100}%`, top: `${rand() * 100}%`,
    delay: rand() * 8, duration: 9 + rand() * 9,
    size: 0.8 + rand() * 0.5,
    color: rand() > 0.85
      ? `rgba(62,232,196,${0.35 + rand() * 0.35})`
      : `rgba(240,242,245,${0.30 + rand() * 0.45})`,
  }))

  const small  = Array.from({ length: 14 }, (_, i) => ({
    id: 100 + i, tier: 'small' as const,
    left: `${rand() * 100}%`, top: `${rand() * 100}%`,
    delay: rand() * 7, duration: 12 + rand() * 10,
    size: 1.2 + rand() * 0.9,
    color: rand() > 0.7
      ? `rgba(152,128,232,${0.3 + rand() * 0.35})`
      : rand() > 0.4
        ? `rgba(62,232,196,${0.25 + rand() * 0.30})`
        : `rgba(240,242,245,${0.35 + rand() * 0.40})`,
  }))

  const medium = Array.from({ length: 6 }, (_, i) => ({
    id: 200 + i, tier: 'medium' as const,
    left: `${rand() * 100}%`, top: `${rand() * 100}%`,
    delay: rand() * 6, duration: 14 + rand() * 12,
    size: 2.0 + rand() * 1.5,
    color: [
      'rgba(62,232,196,0.65)',
      'rgba(152,128,232,0.55)',
      'rgba(232,168,74,0.50)',
      'rgba(216,124,184,0.50)',
      'rgba(72,200,216,0.55)',
      'rgba(240,242,245,0.65)',
    ][i % 6],
  }))

  return [...micro, ...small, ...medium]
}

function AmbientField() {
  const stars = useMemo(() => seedStars(), [])

  return (
    <div
      style={{ position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0 }}
      aria-hidden="true"
    >
      {/* Deep nebula — five-zone gradient, slow breathing */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          animation: 'nebula-breathe 18s ease-in-out infinite',
          background: `
            radial-gradient(ellipse 62% 48% at  8% 10%, color-mix(in srgb, var(--hue-secondary) 10%, transparent), transparent 100%),
            radial-gradient(ellipse 54% 42% at 90% 12%, color-mix(in srgb, var(--hue-glow)       9%, transparent), transparent 100%),
            radial-gradient(ellipse 44% 40% at 50% 88%, rgba(232,168,74,0.05), transparent 100%),
            radial-gradient(ellipse 30% 32% at  2% 54%, color-mix(in srgb, var(--hue-glow) 5%, transparent), transparent 100%),
            radial-gradient(ellipse 90% 40% at 50% 50%, rgba(0,0,0,0.28), transparent 100%)
          `,
        }}
      />

      {/* Stars */}
      {stars.map((s) => (
        <div
          key={s.id}
          style={{
            position: 'absolute',
            left: s.left,
            top:  s.top,
            width:  s.size,
            height: s.size,
            borderRadius: '50%',
            background: s.color,
            animation: s.tier === 'medium'
              ? `star-drift ${s.duration}s ${s.delay}s ease-in-out infinite`
              : `pulse ${s.duration}s ${s.delay}s ease-in-out infinite`,
            ...(s.tier === 'medium'
              ? { boxShadow: `0 0 ${s.size * 2.5}px ${s.color}` }
              : {}),
          }}
        />
      ))}
    </div>
  )
}

export default function AppShell({ children }: AppShellProps) {
  const theme               = useSettingsStore((s) => s.theme)
  const prefersReducedMotion = useReducedMotion()

  useEffect(() => {
    document.body.style.background = T.bg
    document.body.style.color      = T.text
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
      {!prefersReducedMotion && <AmbientField />}

      <div
        style={{
          position: 'relative',
          zIndex: 2,
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
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
              background: 'transparent',
              position: 'relative',
            }}
          >
            {children}
          </main>
        </div>
        <StatusBar />
      </div>

      {/* Idle screensaver — mounts above everything at z-index 9000 */}
      {!prefersReducedMotion && <Screensaver />}
    </div>
  )
}
