import { create } from 'zustand'

const DISMISSED_KEY = 'blueprint-dismissed-tips'

function loadDismissed(): Set<string> {
  try {
    const raw = localStorage.getItem(DISMISSED_KEY)
    if (raw) return new Set(JSON.parse(raw))
  } catch { /* ignore corrupt data */ }
  return new Set<string>()
}

function saveDismissed(tips: Set<string>) {
  try {
    localStorage.setItem(DISMISSED_KEY, JSON.stringify([...tips]))
  } catch { /* ignore quota errors */ }
}

interface GuideState {
  guideActive: boolean
  toggleGuide: () => void
  dismissedTips: Set<string>
  dismissTip: (id: string) => void
}

export const useGuideStore = create<GuideState>((set) => ({
  guideActive: false,
  toggleGuide: () => set((s) => ({ guideActive: !s.guideActive })),
  dismissedTips: loadDismissed(),
  dismissTip: (id) => set((s) => {
    const next = new Set(s.dismissedTips)
    next.add(id)
    saveDismissed(next)
    return { dismissedTips: next }
  }),
}))
