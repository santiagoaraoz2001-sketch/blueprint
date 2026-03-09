import { useEffect, useRef, useCallback } from 'react'

interface SSEOptions {
  onEvent: (event: string, data: any) => void
  onError?: (error: Event) => void
  enabled?: boolean
  maxRetries?: number
}

const BASE_DELAY_MS = 1000
const MAX_DELAY_MS = 30000

export function useSSE(url: string | null, options: SSEOptions) {
  const { onEvent, onError, enabled = true, maxRetries = 10 } = options
  const sourceRef = useRef<EventSource | null>(null)
  const retryCountRef = useRef(0)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onEventRef = useRef(onEvent)
  const onErrorRef = useRef(onError)

  onEventRef.current = onEvent
  onErrorRef.current = onError

  const clearRetryTimer = useCallback(() => {
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current)
      retryTimerRef.current = null
    }
  }, [])

  const disconnect = useCallback(() => {
    clearRetryTimer()
    if (sourceRef.current) {
      sourceRef.current.close()
      sourceRef.current = null
    }
  }, [clearRetryTimer])

  const connect = useCallback(
    (targetUrl: string) => {
      // Close any existing connection before opening a new one
      if (sourceRef.current) {
        sourceRef.current.close()
        sourceRef.current = null
      }

      const es = new EventSource(targetUrl)
      sourceRef.current = es

      es.onmessage = (e) => {
        // Successful message received — reset retry count
        retryCountRef.current = 0

        try {
          const data = JSON.parse(e.data)
          onEventRef.current(data.event || 'message', data)
        } catch {
          onEventRef.current('message', e.data)
        }
      }

      es.onerror = (e) => {
        onErrorRef.current?.(e)

        // Close the broken connection — don't rely on built-in reconnect
        es.close()
        sourceRef.current = null

        if (retryCountRef.current >= maxRetries) {
          console.warn(
            `[useSSE] Max retries (${maxRetries}) reached for ${targetUrl}. Giving up.`
          )
          return
        }

        const delay = Math.min(
          BASE_DELAY_MS * Math.pow(2, retryCountRef.current),
          MAX_DELAY_MS
        )

        console.warn(
          `[useSSE] Connection error. Retrying in ${delay}ms (attempt ${retryCountRef.current + 1}/${maxRetries})`
        )

        retryCountRef.current += 1

        retryTimerRef.current = setTimeout(() => {
          retryTimerRef.current = null
          connect(targetUrl)
        }, delay)
      }
    },
    [maxRetries]
  )

  useEffect(() => {
    if (!url || !enabled) {
      disconnect()
      retryCountRef.current = 0
      return
    }

    retryCountRef.current = 0
    connect(url)

    return () => {
      disconnect()
    }
  }, [url, enabled, connect, disconnect])

  return { disconnect }
}
