import { useEffect, useRef } from 'react'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { api } from '@/api/client'
import toast from 'react-hot-toast'

const RETRY_DELAY_MS = 3000
const SNAPSHOT_INTERVAL_MS = 60_000 // 60 seconds for crash recovery snapshots

// ─── Session identity ────────────────────────────────────────────
// Each browser tab gets a unique session ID so that multi-tab autosaves
// don't overwrite each other. The backend stores files as
// {pipeline_id}_{session_id}_autosave.json and returns the newest on GET.

const SESSION_ID = (() => {
  // Reuse if already set (HMR / re-imports), otherwise generate
  const existing = (globalThis as any).__BLUEPRINT_SESSION_ID
  if (existing) return existing as string
  const id = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
  ;(globalThis as any).__BLUEPRINT_SESSION_ID = id
  return id
})()

// ─── BroadcastChannel for multi-tab coordination ─────────────────
// When one tab performs an explicit save, it broadcasts a message so
// other tabs can delete their autosave files for that pipeline.

let _saveChannel: BroadcastChannel | null = null
try {
  _saveChannel = new BroadcastChannel('blueprint:autosave')
} catch {
  // BroadcastChannel not supported (SSR, old browsers) — graceful degradation
}

export function useAutoSave() {
  const autoSaveInterval = useSettingsStore((s) => s.autoSaveInterval)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastDirtyRef = useRef(false)

  // Existing auto-save behavior (full save to DB)
  useEffect(() => {
    const unsub = usePipelineStore.subscribe((state, prev) => {
      if (state.isDirty && !prev.isDirty) {
        if (timerRef.current) clearTimeout(timerRef.current)

        timerRef.current = setTimeout(async () => {
          const { isDirty, savePipeline } = usePipelineStore.getState()
          if (!isDirty) return

          try {
            await savePipeline()
          } catch (error) {
            console.warn('[useAutoSave] Save failed, retrying in 3s:', error)

            retryTimerRef.current = setTimeout(async () => {
              const retryState = usePipelineStore.getState()
              if (!retryState.isDirty) return

              try {
                await retryState.savePipeline()
              } catch (retryError) {
                console.warn('[useAutoSave] Retry save also failed:', retryError)
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

  // Crash recovery snapshots — session-scoped, every 60s when dirty
  useEffect(() => {
    const timer = setInterval(() => {
      const { id, isDirty, name, nodes, edges } = usePipelineStore.getState()
      if (!id || !isDirty) return

      api.post(`/pipelines/${id}/autosave`, {
        name,
        session_id: SESSION_ID,
        definition: { nodes, edges },
      }).catch(() => {})
    }, SNAPSHOT_INTERVAL_MS)

    return () => clearInterval(timer)
  }, [])

  // On explicit save: delete ALL autosaves for this pipeline + broadcast to other tabs
  useEffect(() => {
    return usePipelineStore.subscribe((state) => {
      const wasDirty = lastDirtyRef.current
      const isNowClean = !state.isDirty
      lastDirtyRef.current = state.isDirty

      if (wasDirty && isNowClean && state.id) {
        api.delete(`/pipelines/${state.id}/autosave`).catch(() => {})
        // Notify other tabs to clean up their autosaves too
        _saveChannel?.postMessage({ type: 'saved', pipelineId: state.id })
      }
    })
  }, [])

  // Listen for save broadcasts from other tabs
  useEffect(() => {
    if (!_saveChannel) return
    const handler = (e: MessageEvent) => {
      if (e.data?.type === 'saved') {
        const pipelineId = e.data.pipelineId
        const currentId = usePipelineStore.getState().id
        if (pipelineId === currentId) {
          // Another tab saved this pipeline — our autosave is stale
          api.delete(`/pipelines/${pipelineId}/autosave`).catch(() => {})
        }
      }
    }
    _saveChannel.addEventListener('message', handler)
    return () => _saveChannel?.removeEventListener('message', handler)
  }, [])
}

// ─── Public API ──────────────────────────────────────────────────

/**
 * Check for autosave recovery for a specific pipeline.
 * The backend scans all session-scoped autosave files and returns the newest.
 */
export async function checkAutosave(pipelineId: string): Promise<{
  exists: boolean
  timestamp?: string
  definition?: any
  name?: string
} | null> {
  try {
    return await api.get<{
      exists: boolean
      timestamp?: string
      definition?: any
      name?: string
    }>(`/pipelines/${pipelineId}/autosave`)
  } catch {
    return null
  }
}

/**
 * Discard ALL autosave files for a pipeline (from any session).
 */
export async function discardAutosave(pipelineId: string): Promise<void> {
  try {
    await api.delete(`/pipelines/${pipelineId}/autosave`)
  } catch {}
}
