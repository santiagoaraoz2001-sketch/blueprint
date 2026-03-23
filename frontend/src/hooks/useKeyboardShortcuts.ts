import { useEffect } from 'react'
import { useUIStore } from '@/stores/uiStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useRunStore } from '@/stores/runStore'
import { useGuideStore } from '@/stores/guideStore'
import toast from 'react-hot-toast'

export function useKeyboardShortcuts() {
  const setView = useUIStore((s) => s.setView)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey
      const isInput = e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement

      // G — Toggle guide (not in inputs)
      if (!meta && e.key === 'g' && !isInput) {
        e.preventDefault()
        useGuideStore.getState().toggleGuide()
        return
      }

      // Cmd+S — Save pipeline
      if (meta && !e.shiftKey && e.key === 's') {
        e.preventDefault()
        const { savePipeline, isDirty } = usePipelineStore.getState()
        if (isDirty) {
          savePipeline()
            .then(() => toast.success('Pipeline saved'))
            .catch(() => toast.error('Save failed'))
        }
        return
      }

      // Cmd+Shift+M — Navigate to Monitor (active or latest run)
      if (meta && e.shiftKey && (e.key === 'm' || e.key === 'M')) {
        e.preventDefault()
        const { activeRunId } = useRunStore.getState()
        useUIStore.getState().navigateToMonitor(activeRunId)
        return
      }

      // Cmd+Shift+R — Re-run most recent pipeline (same config)
      if (meta && e.shiftKey && (e.key === 'r' || e.key === 'R')) {
        e.preventDefault()
        const { pipelineId } = useRunStore.getState()
        const currentPipelineId = pipelineId || usePipelineStore.getState().id
        if (currentPipelineId) {
          useRunStore.getState().startRun(currentPipelineId)
          toast.success('Re-running pipeline')
        } else {
          toast.error('No pipeline to re-run')
        }
        return
      }

      // Cmd+Shift+C — Clone currently viewed pipeline
      if (meta && e.shiftKey && (e.key === 'c' || e.key === 'C')) {
        e.preventDefault()
        const pipelineId = usePipelineStore.getState().id
        if (pipelineId) {
          usePipelineStore.getState().duplicatePipeline(pipelineId)
        } else {
          toast.error('No pipeline to clone')
        }
        return
      }

      // Shift+R — Re-run from selected node (no meta key, not in inputs)
      if (!meta && e.shiftKey && (e.key === 'r' || e.key === 'R') && !isInput) {
        const view = useUIStore.getState().activeView
        if (view === 'editor') {
          e.preventDefault()
          const { selectedNodeId, enterRerunMode } = usePipelineStore.getState()
          const { activeRunId, status } = useRunStore.getState()
          const isComplete = status === 'complete' || status === 'failed'
          if (selectedNodeId && activeRunId && isComplete) {
            enterRerunMode(selectedNodeId, activeRunId)
          }
          return
        }
      }

      // Cmd+Z — Undo (global, works in editor view)
      if (meta && !e.shiftKey && e.key === 'z' && !isInput) {
        const view = useUIStore.getState().activeView
        if (view === 'editor') {
          e.preventDefault()
          usePipelineStore.getState().undo()
          return
        }
      }

      // Cmd+Shift+Z — Redo (global, works in editor view)
      if (meta && e.shiftKey && (e.key === 'z' || e.key === 'Z') && !isInput) {
        const view = useUIStore.getState().activeView
        if (view === 'editor') {
          e.preventDefault()
          usePipelineStore.getState().redo()
          return
        }
      }

      // Cmd+1-7 — Switch views
      if (meta && !e.shiftKey && e.key >= '1' && e.key <= '7') {
        e.preventDefault()
        const allViews = ['dashboard', 'editor', 'results', 'datasets', 'marketplace', 'paper', 'settings'] as const
        const features = useSettingsStore.getState().features
        const views = allViews.filter(v => v !== 'marketplace' || features?.marketplace)
        const idx = parseInt(e.key) - 1
        if (idx < views.length) setView(views[idx])
        return
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [setView])
}
