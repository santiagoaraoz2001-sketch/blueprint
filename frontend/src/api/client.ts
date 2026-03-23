// Configurable via VITE_API_URL environment variable
const BASE_URL = import.meta.env.VITE_API_URL || '/api'

/** Default request timeout in milliseconds */
const DEFAULT_TIMEOUT_MS = 30_000
/** Max retry attempts for 5xx errors */
const MAX_RETRIES = 3
/** Base delay for retry backoff (ms) */
const RETRY_BASE_DELAY_MS = 1_000

// ---------------------------------------------------------------------------
// Circuit breaker — prevents retry storms when the backend is unavailable.
// After a network failure (connection refused / fetch error), all subsequent
// requests fail immediately until a lightweight health probe succeeds.
// ---------------------------------------------------------------------------
let _backendDown = false
let _healthProbeRunning = false

function _startHealthProbe() {
  if (_healthProbeRunning) return
  _healthProbeRunning = true

  const probe = () => {
    fetch(`${BASE_URL}/health`, { signal: AbortSignal.timeout(5_000) })
      .then((r) => {
        if (r.ok) {
          _backendDown = false
          _healthProbeRunning = false
          return
        }
        setTimeout(probe, 3_000)
      })
      .catch(() => {
        setTimeout(probe, 3_000)
      })
  }
  // First probe after a short delay
  setTimeout(probe, 2_000)
}

function _markBackendDown() {
  if (!_backendDown) {
    _backendDown = true
    _startHealthProbe()
  }
}

/** Human-readable error messages for common HTTP status codes */
const HTTP_ERROR_MESSAGES: Record<number, string> = {
  400: 'Bad request \u2014 the server could not understand the request',
  401: 'Unauthorized \u2014 authentication is required',
  403: 'Forbidden \u2014 you do not have permission to access this resource',
  404: 'Resource not found',
  405: 'Method not allowed',
  408: 'Request timed out \u2014 the server took too long to respond',
  409: 'Conflict \u2014 the resource was modified by another request',
  413: 'Payload too large \u2014 try reducing the size of your data',
  422: 'Validation error \u2014 check your input parameters',
  429: 'Too many requests \u2014 please wait before trying again',
  500: 'Server error \u2014 check if the backend is running',
  502: 'Bad gateway \u2014 the backend server may be restarting',
  503: 'Service unavailable \u2014 the backend server may be starting up',
  504: 'Gateway timeout \u2014 the backend took too long to respond',
}

/** Build a human-readable error message from an HTTP status code and optional server error body */
function formatHttpError(status: number, serverError: string): string {
  const friendly = HTTP_ERROR_MESSAGES[status]
  if (friendly) {
    // Append server detail if it provides additional context beyond the status code
    const trimmed = serverError.trim()
    if (trimmed && trimmed !== 'Unknown error' && trimmed.toLowerCase() !== 'internal server error') {
      return `${friendly}: ${trimmed}`
    }
    return friendly
  }
  // Fallback for unmapped status codes
  return `Server responded with ${status}: ${serverError}`
}

/** Marker class so we can distinguish our own formatted errors from raw fetch errors */
export class ApiError extends Error {
  constructor(message: string, public statusCode?: number) {
    super(message)
    this.name = 'ApiError'
  }
}

/** Build a human-readable message for network-level errors (no HTTP response) */
function formatNetworkError(error: unknown): ApiError {
  if (error instanceof TypeError) {
    // TypeError: Failed to fetch — typically means the server is unreachable
    return new ApiError('Cannot reach server \u2014 is the backend running?')
  }
  if (error instanceof Error) {
    return new ApiError(error.message)
  }
  return new ApiError('An unexpected network error occurred')
}

interface RequestOptions extends RequestInit {
  retries?: number
  timeoutMs?: number
}

async function request<T>(path: string, options?: RequestOptions): Promise<T> {
  const { retries = MAX_RETRIES, timeoutMs = DEFAULT_TIMEOUT_MS, signal: externalSignal, ...fetchOptions } = options || {}

  // Circuit breaker: fail fast when backend is known to be down
  if (_backendDown) {
    throw new ApiError('Backend is unavailable \u2014 waiting for it to come back online', 503)
  }

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)

  // If the caller provided an external signal (e.g. for cancel), abort our
  // controller when that signal fires so the fetch is cancelled.
  let onExternalAbort: (() => void) | undefined
  if (externalSignal) {
    if (externalSignal.aborted) {
      clearTimeout(timeout)
      throw new ApiError('Request was cancelled', 0)
    }
    onExternalAbort = () => controller.abort()
    externalSignal.addEventListener('abort', onExternalAbort, { once: true })
  }

  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...fetchOptions.headers,
      },
      ...fetchOptions,
      signal: controller.signal,
    })

    if (!res.ok) {
      const error = await res.text().catch(() => 'Unknown error')
      // 502/503 from the proxy means the backend process is unreachable —
      // trip the circuit breaker and fail fast instead of retrying.
      if (res.status === 502 || res.status === 503) {
        _markBackendDown()
        throw new ApiError(formatHttpError(res.status, error), res.status)
      }
      // Retry on other 5xx server errors (real application errors)
      if (res.status >= 500 && retries > 0) {
        const delay = RETRY_BASE_DELAY_MS * (MAX_RETRIES - retries + 1)
        await new Promise((r) => setTimeout(r, delay))
        return request<T>(path, { ...fetchOptions, retries: retries - 1, timeoutMs, signal: externalSignal })
      }
      // All retries exhausted on 5xx — backend is likely down (proxy wraps
      // connection-refused as 500). Trip the circuit breaker.
      if (res.status >= 500) {
        _markBackendDown()
      }
      throw new ApiError(formatHttpError(res.status, error), res.status)
    }

    if (res.status === 204) return undefined as T
    return res.json()
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') {
      // Distinguish external cancellation from timeout
      if (externalSignal?.aborted) {
        throw new ApiError('Request was cancelled', 0)
      }
      throw new ApiError(
        `Request timed out after ${Math.round(timeoutMs / 1000)}s \u2014 the server may be overloaded (${path})`,
        408
      )
    }
    // Re-throw our own formatted errors as-is
    if (e instanceof ApiError) {
      throw e
    }
    // Network-level failure (connection refused, DNS, etc.) — trip circuit breaker
    _markBackendDown()
    throw formatNetworkError(e)
  } finally {
    clearTimeout(timeout)
    if (onExternalAbort && externalSignal) {
      externalSignal.removeEventListener('abort', onExternalAbort)
    }
  }
}

/** Extra options callers can pass for individual requests */
export interface ApiRequestOptions {
  timeoutMs?: number
  signal?: AbortSignal
}

/** Returns true when the circuit breaker has tripped (backend unreachable). */
export function isBackendDown(): boolean {
  return _backendDown
}

export const api = {
  get: <T>(path: string, opts?: ApiRequestOptions) =>
    request<T>(path, { ...opts }),

  post: <T>(path: string, body?: unknown, opts?: ApiRequestOptions) =>
    request<T>(path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
      ...opts,
    }),

  put: <T>(path: string, body?: unknown, opts?: ApiRequestOptions) =>
    request<T>(path, {
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
      ...opts,
    }),

  patch: <T>(path: string, body?: unknown, opts?: ApiRequestOptions) =>
    request<T>(path, {
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
      ...opts,
    }),

  delete: <T>(path: string, opts?: ApiRequestOptions) =>
    request<T>(path, { method: 'DELETE', ...opts }),
}
