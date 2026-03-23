import { T, F, FS } from '@/lib/design-tokens'
import { useGuideStore } from '@/stores/guideStore'
import { useUIStore } from '@/stores/uiStore'
import { VIEW_TIPS, type ViewId } from '@/lib/tips'
import { X } from 'lucide-react'

export default function GuideBar() {
  const guideActive = useGuideStore((s) => s.guideActive)
  const dismissedTips = useGuideStore((s) => s.dismissedTips)
  const dismissTip = useGuideStore((s) => s.dismissTip)
  const activeView = useUIStore((s) => s.activeView) as ViewId

  if (!guideActive) return null

  const tips = (VIEW_TIPS[activeView] || []).filter((t) => !dismissedTips.has(t.id))

  if (tips.length === 0) return null

  return (
    <div
      style={{
        background: `linear-gradient(180deg, ${T.surface2} 0%, ${T.surface3} 100%)`,
        borderBottom: `1px solid ${T.border}`,
        padding: '6px 14px',
        display: 'flex',
        gap: 8,
        overflow: 'auto',
        flexShrink: 0,
      }}
    >
      {tips.map((tip) => (
        <div
          key={tip.id}
          style={{
            flex: '0 0 auto',
            maxWidth: 280,
            background: T.surface1,
            border: `1px solid ${T.border}`,
            borderLeft: `2px solid ${T.cyan}50`,
            padding: '5px 8px',
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
            position: 'relative',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span
              style={{
                fontFamily: F,
                fontSize: FS.xxs,
                color: T.cyan,
                fontWeight: 900,
                letterSpacing: '0.1em',
              }}
            >
              {tip.label}
            </span>
            <button
              onClick={() => dismissTip(tip.id)}
              style={{
                background: 'none',
                border: 'none',
                color: T.dim,
                padding: 0,
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <X size={8} />
            </button>
          </div>
          <span
            style={{
              fontFamily: F,
              fontSize: FS.xxs,
              color: T.sec,
              lineHeight: 1.4,
            }}
          >
            {tip.description}
          </span>
        </div>
      ))}
    </div>
  )
}
