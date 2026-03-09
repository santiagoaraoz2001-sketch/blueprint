// Configurable via VITE_API_URL environment variable
const BASE_URL = import.meta.env.VITE_API_URL || '/api'

/** Default request timeout in milliseconds */
const DEFAULT_TIMEOUT_MS = 30_000
/** Max retry attempts for 5xx errors */
const MAX_RETRIES = 3
/** Base delay for retry backoff (ms) */
const RETRY_BASE_DELAY_MS = 1_000

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
  const { retries = MAX_RETRIES, timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options || {}

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)

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
      // Retry on 5xx server errors
      if (res.status >= 500 && retries > 0) {
        const delay = RETRY_BASE_DELAY_MS * (MAX_RETRIES - retries + 1)
        await new Promise((r) => setTimeout(r, delay))
        return request<T>(path, { ...fetchOptions, retries: retries - 1, timeoutMs })
      }
      throw new ApiError(formatHttpError(res.status, error), res.status)
    }

    if (res.status === 204) return undefined as T
    return res.json()
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') {
      throw new ApiError(
        `Request timed out after ${Math.round(timeoutMs / 1000)}s \u2014 the server may be overloaded (${path})`,
        408
      )
    }
    // Re-throw our own formatted errors as-is
    if (e instanceof ApiError) {
      throw e
    }
    // Wrap raw network errors with a human-readable message
    throw formatNetworkError(e)
  } finally {
    clearTimeout(timeout)
  }
}

export const api = {
  get: <T>(path: string) => request<T>(path),

  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }),

  put: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
    }),

  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    }),

  delete: <T>(path: string) =>
    request<T>(path, { method: 'DELETE' }),
}
