import { useEffect } from 'react'
import { useUIStore } from '@/stores/uiStore'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useGuideStore } from '@/stores/guideStore'
import toast from 'react-hot-toast'

export function useKeyboardShortcuts() {
  const setView = useUIStore((s) => s.setView)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey

      // G — Toggle guide
      if (!meta && e.key === 'g' && !(e.target instanceof HTMLInputElement) && !(e.target instanceof HTMLTextAreaElement)) {
        e.preventDefault()
        useGuideStore.getState().toggleGuide()
        return
      }

      // Cmd+S — Save pipeline
      if (meta && e.key === 's') {
        e.preventDefault()
        const { savePipeline, isDirty } = usePipelineStore.getState()
        if (isDirty) {
          savePipeline()
            .then(() => toast.success('Pipeline saved'))
            .catch(() => toast.error('Save failed'))
        }
        return
      }

      // Cmd+1-7 — Switch views
      if (meta && e.key >= '1' && e.key <= '7') {
        e.preventDefault()
        const views = ['dashboard', 'editor', 'results', 'datasets', 'marketplace', 'paper', 'settings'] as const
        const idx = parseInt(e.key) - 1
        if (idx < views.length) setView(views[idx])
        return
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [setView])
}
