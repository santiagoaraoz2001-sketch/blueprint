import { useEffect, useState, useRef } from 'react'
import { useRunStore } from '@/stores/runStore'

/**
 * Invisible aria-live region that announces pipeline state changes
 * to screen readers: run start, block completion, errors.
 */
export default function LiveAnnouncer() {
  const [message, setMessage] = useState('')
  const prevStatus = useRef<string | null>(null)
  const prevRunningCount = useRef(0)

  const status = useRunStore((s) => s.status)
  const nodeStatuses = useRunStore((s) => s.nodeStatuses)
  const error = useRunStore((s) => s.error)

  useEffect(() => {
    // Pipeline started
    if (status === 'running' && prevStatus.current !== 'running') {
      setMessage('Pipeline execution started')
    }

    // Pipeline completed
    if (status === 'complete' && prevStatus.current === 'running') {
      setMessage('Pipeline execution completed successfully')
    }

    // Pipeline failed
    if (status === 'failed' && prevStatus.current !== 'failed') {
      const errorMsg = error || 'Unknown error'
      setMessage(`Pipeline execution failed: ${errorMsg}`)
    }

    // Track block completions
    if (status === 'running') {
      const completedNodes = Object.entries(nodeStatuses).filter(
        ([, ns]) => ns.status === 'complete'
      )
      const runningNodes = Object.entries(nodeStatuses).filter(
        ([, ns]) => ns.status === 'running'
      )
      if (completedNodes.length > prevRunningCount.current) {
        const latest = completedNodes[completedNodes.length - 1]
        if (latest) {
          setMessage(`Block ${latest[0]} completed successfully`)
        }
      }
      if (runningNodes.length > 0) {
        const current = runningNodes[runningNodes.length - 1]
        if (current) {
          setMessage(`Now running block: ${current[0]}`)
        }
      }
      prevRunningCount.current = completedNodes.length
    }

    prevStatus.current = status
  }, [status, nodeStatuses, error])

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      className="sr-only"
    >
      {message}
    </div>
  )
}
