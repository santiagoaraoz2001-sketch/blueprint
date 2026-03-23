import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface MissionState {
  activeMissionId: string | null
  currentStepIndex: number
  completedMissions: string[]
  isMinimized: boolean
  hintVisible: boolean

  startMission: (id: string) => void
  advanceStep: () => void
  completeMission: () => void
  skipMission: () => void
  toggleMinimize: () => void
  showHint: () => void
  hideHint: () => void
  resetAll: () => void
}

export const useMissionStore = create<MissionState>()(
  persist(
    (set, get) => ({
      activeMissionId: null,
      currentStepIndex: 0,
      completedMissions: [],
      isMinimized: false,
      hintVisible: false,

      startMission: (id: string) => {
        set({ activeMissionId: id, currentStepIndex: 0, isMinimized: false, hintVisible: false })
      },

      advanceStep: () => {
        set((s) => ({ currentStepIndex: s.currentStepIndex + 1, hintVisible: false }))
      },

      completeMission: () => {
        const { activeMissionId, completedMissions } = get()
        if (activeMissionId && !completedMissions.includes(activeMissionId)) {
          set({
            activeMissionId: null,
            currentStepIndex: 0,
            completedMissions: [...completedMissions, activeMissionId],
            isMinimized: false,
            hintVisible: false,
          })
        } else {
          set({ activeMissionId: null, currentStepIndex: 0, isMinimized: false, hintVisible: false })
        }
      },

      skipMission: () => {
        const { activeMissionId, completedMissions } = get()
        if (activeMissionId && !completedMissions.includes(activeMissionId)) {
          set({
            activeMissionId: null,
            currentStepIndex: 0,
            completedMissions: [...completedMissions, activeMissionId],
            hintVisible: false,
          })
        } else {
          set({ activeMissionId: null, currentStepIndex: 0, hintVisible: false })
        }
      },

      toggleMinimize: () => set((s) => ({ isMinimized: !s.isMinimized })),
      showHint: () => set({ hintVisible: true }),
      hideHint: () => set({ hintVisible: false }),
      resetAll: () => set({ activeMissionId: null, currentStepIndex: 0, completedMissions: [], isMinimized: false, hintVisible: false }),
    }),
    {
      name: 'blueprint-mission-storage',
      partialize: (state) => ({ completedMissions: state.completedMissions }),
    }
  )
)
