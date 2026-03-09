import { create } from 'zustand'

interface GuideState {
  guideActive: boolean
  toggleGuide: () => void
  dismissedTips: Set<string>
  dismissTip: (id: string) => void
}

export const useGuideStore = create<GuideState>((set) => ({
  guideActive: false,
  toggleGuide: () => set((s) => ({ guideActive: !s.guideActive })),
  dismissedTips: new Set<string>(),
  dismissTip: (id) => set((s) => {
    const next = new Set(s.dismissedTips)
    next.add(id)
    return { dismissedTips: next }
  }),
}))
