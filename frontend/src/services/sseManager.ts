/**
 * SSE Manager — single canonical EventSource per run.
 *
 * All Zustand stores subscribe to this manager instead of creating
 * their own EventSource connections. Handles reconnection, replay,
 * staleness detection, and tab visibility recovery.
 */

type SSEEventHandler = (event: string, data: any) => void

interface SSEConnection {
  runId: string
  eventSource: EventSource
  subscribers: Set<SSEEventHandler>
  lastEventId: string | null
  reconnectAttempts: number
  reconnectTimer: number | null
  isStale: boolean
  lastEventAt: number
  closing: boolean // guard against double terminal-event close
}

const MAX_RECONNECT_ATTEMPTS = 10
const RECONNECT_BASE_DELAY = 1000 // ms
const RECONNECT_MAX_DELAY = 30_000 // cap at 30s
const STALE_THRESHOLD = 30_000 // 30s without events = stale
const TERMINAL_CLOSE_DELAY = 2000 // delay before closing after terminal event

const TERMINAL_EVENTS = new Set(['run_completed', 'run_failed', 'run_cancelled'])

const NAMED_EVENT_TYPES = [
  'node_started', 'node_progress', 'node_completed', 'node_failed',
  'node_output', 'node_log', 'node_retry', 'node_cached',
  'metric', 'system_metric',
  'run_completed', 'run_failed', 'run_cancelled',
  'sweep_run_completed', 'sweep_run_failed', 'sweep_completed',
]

class SSEManager {
  private connections: Map<string, SSEConnection> = new Map()
  private staleCheckInterval: number | null = null
  private visibilityHandler: (() => void) | null = null

  constructor() {
    this.staleCheckInterval = window.setInterval(() => this.checkStale(), 10_000)

    // Reconnect stale/closed connections when tab regains focus
    this.visibilityHandler = () => {
      if (document.visibilityState !== 'visible') return

      for (const [, conn] of this.connections) {
        if (conn.closing) continue
        const es = conn.eventSource
        if (!es || es.readyState === EventSource.CLOSED) {
          conn.reconnectAttempts = 0 // reset backoff — browser-initiated close
          this.connect(conn)
        }
      }
    }
    document.addEventListener('visibilitychange', this.visibilityHandler)
  }

  /**
   * Subscribe to SSE events for a run.
   * Creates the EventSource on first subscriber, reuses for subsequent ones.
   * Returns an unsubscribe function.
   */
  subscribe(runId: string, handler: SSEEventHandler): () => void {
    let conn = this.connections.get(runId)

    // Create new connection if none exists or if the existing one is shutting down
    if (!conn || conn.closing) {
      if (conn?.closing) {
        // Let the pending close timer finish, but start fresh
        this.connections.delete(runId)
      }
      conn = this.createConnection(runId)
      this.connections.set(runId, conn)
    }

    conn.subscribers.add(handler)

    return () => {
      conn!.subscribers.delete(handler)
      // Only close if connection is still tracked (not already closed by terminal event)
      if (conn!.subscribers.size === 0 && this.connections.has(runId)) {
        this.closeConnection(runId)
      }
    }
  }

  /**
   * Check if a run's SSE connection is stale (no events received recently).
   */
  isStale(runId: string): boolean {
    return this.connections.get(runId)?.isStale ?? false
  }

  /**
   * Get connection status for a run.
   */
  getStatus(runId: string): 'connected' | 'reconnecting' | 'stale' | 'disconnected' {
    const conn = this.connections.get(runId)
    if (!conn) return 'disconnected'
    if (conn.isStale) return 'stale'
    if (conn.reconnectAttempts > 0) return 'reconnecting'
    if (conn.eventSource.readyState === EventSource.OPEN) return 'connected'
    return 'reconnecting'
  }

  private createConnection(runId: string): SSEConnection {
    const conn: SSEConnection = {
      runId,
      eventSource: null as any, // set in connect()
      subscribers: new Set(),
      lastEventId: null,
      reconnectAttempts: 0,
      reconnectTimer: null,
      isStale: false,
      lastEventAt: Date.now(),
      closing: false,
    }

    this.connect(conn)
    return conn
  }

  private connect(conn: SSEConnection): void {
    // Close previous EventSource if re-connecting
    if (conn.eventSource) {
      conn.eventSource.close()
    }

    const url = new URL(`/api/events/runs/${conn.runId}`, window.location.origin)
    if (conn.lastEventId) {
      url.searchParams.set('lastEventId', conn.lastEventId)
    }

    const es = new EventSource(url.toString())

    es.onopen = () => {
      conn.reconnectAttempts = 0
      conn.isStale = false
      conn.lastEventAt = Date.now()
      this.dispatch(conn, '__sse_connected', { runId: conn.runId })
    }

    es.onmessage = (event) => {
      this.handleRawEvent(conn, event)
    }

    // Register named event listeners for typed SSE events
    for (const eventType of NAMED_EVENT_TYPES) {
      es.addEventListener(eventType, (event: MessageEvent) => {
        this.handleNamedEvent(conn, eventType, event)
      })
    }

    es.onerror = () => {
      es.close()
      if (!conn.closing) {
        this.reconnect(conn)
      }
    }

    conn.eventSource = es
  }

  /** Process an unnamed SSE message (onmessage) */
  private handleRawEvent(conn: SSEConnection, event: MessageEvent): void {
    conn.isStale = false
    conn.lastEventAt = Date.now()

    if (event.lastEventId) {
      conn.lastEventId = event.lastEventId
    }

    try {
      const parsed = JSON.parse(event.data)
      const eventType = parsed.event || 'message'
      this.dispatch(conn, eventType, parsed)
      this.maybeScheduleClose(conn, eventType)
    } catch {
      // Non-JSON message (keepalive comment), ignore
    }
  }

  /** Process a named SSE event (event: type) */
  private handleNamedEvent(conn: SSEConnection, eventType: string, event: MessageEvent): void {
    conn.isStale = false
    conn.lastEventAt = Date.now()

    if (event.lastEventId) {
      conn.lastEventId = event.lastEventId
    }

    try {
      const data = JSON.parse(event.data)
      this.dispatch(conn, eventType, data)
      this.maybeScheduleClose(conn, eventType)
    } catch {
      // ignore parse errors
    }
  }

  /** Schedule auto-close after terminal events, guarded against duplicates */
  private maybeScheduleClose(conn: SSEConnection, eventType: string): void {
    if (!TERMINAL_EVENTS.has(eventType)) return
    if (conn.closing) return // already scheduled
    conn.closing = true

    setTimeout(() => {
      this.closeConnection(conn.runId)
    }, TERMINAL_CLOSE_DELAY)
  }

  private reconnect(conn: SSEConnection): void {
    if (conn.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      conn.isStale = true
      this.dispatch(conn, '__sse_failed', {
        runId: conn.runId,
        reason: 'max_reconnect_attempts',
      })
      return
    }

    conn.reconnectAttempts++
    const delay = Math.min(
      RECONNECT_BASE_DELAY * Math.pow(2, conn.reconnectAttempts - 1),
      RECONNECT_MAX_DELAY,
    )

    this.dispatch(conn, '__sse_reconnecting', {
      runId: conn.runId,
      attempt: conn.reconnectAttempts,
      maxAttempts: MAX_RECONNECT_ATTEMPTS,
    })

    conn.reconnectTimer = window.setTimeout(() => {
      conn.reconnectTimer = null
      this.connect(conn)
    }, delay)
  }

  private dispatch(conn: SSEConnection, event: string, data: any): void {
    for (const handler of conn.subscribers) {
      try {
        handler(event, data)
      } catch (e) {
        console.error(`[SSEManager] handler error for ${event}:`, e)
      }
    }
  }

  private checkStale(): void {
    const now = Date.now()
    for (const [, conn] of this.connections) {
      if (conn.closing) continue
      if (
        !conn.isStale &&
        now - conn.lastEventAt > STALE_THRESHOLD &&
        conn.eventSource.readyState !== EventSource.OPEN
      ) {
        conn.isStale = true
        this.dispatch(conn, '__sse_stale', { runId: conn.runId })
      }
    }
  }

  private closeConnection(runId: string): void {
    const conn = this.connections.get(runId)
    if (!conn) return

    if (conn.reconnectTimer) {
      clearTimeout(conn.reconnectTimer)
    }
    conn.eventSource.close()
    this.connections.delete(runId)
  }

  destroy(): void {
    if (this.staleCheckInterval) {
      clearInterval(this.staleCheckInterval)
      this.staleCheckInterval = null
    }
    if (this.visibilityHandler) {
      document.removeEventListener('visibilitychange', this.visibilityHandler)
      this.visibilityHandler = null
    }
    for (const [runId] of this.connections) {
      this.closeConnection(runId)
    }
  }
}

// Singleton instance
export const sseManager = new SSEManager()
