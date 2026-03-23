import { useEffect, useRef } from 'react'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useSettingsStore } from '@/stores/settingsStore'
import toast from 'react-hot-toast'

const RETRY_DELAY_MS = 3000

export function useAutoSave() {
  const autoSaveInterval = useSettingsStore((s) => s.autoSaveInterval)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const unsub = usePipelineStore.subscribe((state, prev) => {
      if (state.isDirty && !prev.isDirty) {
        // Pipeline became dirty and has an ID — schedule save
        if (timerRef.current) clearTimeout(timerRef.current)

        timerRef.current = setTimeout(async () => {
          const { isDirty, savePipeline } = usePipelineStore.getState()
          if (!isDirty) return

          try {
            await savePipeline()
          } catch (error) {
            console.warn('[useAutoSave] Save failed, retrying in 3s:', error)

            // Retry once after 3 seconds
            retryTimerRef.current = setTimeout(async () => {
              const retryState = usePipelineStore.getState()
              if (!retryState.isDirty) return

              try {
                await retryState.savePipeline()
              } catch (retryError) {
                console.warn(
                  '[useAutoSave] Retry save also failed:',
                  retryError
                )
                toast.error('Auto-save failed. Save manually with \u2318S / Ctrl+S.')
              }
            }, RETRY_DELAY_MS)
          }
        }, autoSaveInterval)
      }
    })

    return () => {
      unsub()
      if (timerRef.current) clearTimeout(timerRef.current)
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current)
    }
  }, [autoSaveInterval])
}
