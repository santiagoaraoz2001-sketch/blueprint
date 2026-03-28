import { Component, type ReactNode } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { AlertTriangle, RotateCcw, Copy, ChevronDown, ChevronUp } from 'lucide-react'

interface Props {
  children: ReactNode
  fallbackLabel?: string
}

interface State {
  hasError: boolean
  error: Error | null
  showDetails: boolean
  copied: boolean
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null, showDetails: false, copied: false }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, showDetails: false, copied: false })
  }

  handleCopyError = async () => {
    const { error } = this.state
    if (!error) return
    const text = `${error.name}: ${error.message}\n\n${error.stack || 'No stack trace available'}`
    try {
      await navigator.clipboard.writeText(text)
      this.setState({ copied: true })
      setTimeout(() => this.setState({ copied: false }), 2000)
    } catch {
      // Fallback for environments without clipboard API
    }
  }

  toggleDetails = () => {
    this.setState((s) => ({ showDetails: !s.showDetails }))
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          role="alert"
          aria-live="assertive"
          style={{
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 16,
            padding: 40,
            background: T.bg,
          }}
        >
          <AlertTriangle size={28} color={T.amber} />
          <div
            style={{
              fontFamily: F,
              fontSize: FS.sm,
              fontWeight: 900,
              color: T.amber,
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
            }}
          >
            {this.props.fallbackLabel || 'Something went wrong'}
          </div>
          <div
            style={{
              fontFamily: F,
              fontSize: FS.xs,
              color: T.dim,
              maxWidth: 400,
              textAlign: 'center',
              lineHeight: 1.6,
            }}
          >
            {this.state.error?.message || 'An unexpected error occurred.'}
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={this.handleReset}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '8px 16px',
                background: T.surface2,
                border: `1px solid ${T.border}`,
                borderRadius: 4,
                color: T.sec,
                fontFamily: F,
                fontSize: FS.xs,
                fontWeight: 700,
                cursor: 'pointer',
                letterSpacing: '0.08em',
              }}
            >
              <RotateCcw size={12} />
              RETRY
            </button>
            <button
              onClick={this.handleCopyError}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '8px 16px',
                background: T.surface2,
                border: `1px solid ${T.border}`,
                borderRadius: 4,
                color: this.state.copied ? T.green : T.sec,
                fontFamily: F,
                fontSize: FS.xs,
                fontWeight: 700,
                cursor: 'pointer',
                letterSpacing: '0.08em',
              }}
            >
              <Copy size={12} />
              {this.state.copied ? 'COPIED' : 'COPY ERROR'}
            </button>
          </div>

          {this.state.error?.stack && (
            <>
              <button
                onClick={this.toggleDetails}
                aria-expanded={this.state.showDetails}
                aria-label="Toggle error details"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  background: 'none',
                  border: 'none',
                  color: T.dim,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  cursor: 'pointer',
                  letterSpacing: '0.06em',
                }}
              >
                {this.state.showDetails ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
                {this.state.showDetails ? 'HIDE DETAILS' : 'SHOW DETAILS'}
              </button>
              {this.state.showDetails && (
                <pre
                  style={{
                    fontFamily: F,
                    fontSize: FS.xxs,
                    color: T.dim,
                    background: T.surface1,
                    border: `1px solid ${T.border}`,
                    padding: 12,
                    maxWidth: 600,
                    maxHeight: 200,
                    overflow: 'auto',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-all',
                    lineHeight: 1.5,
                  }}
                >
                  {this.state.error.stack}
                </pre>
              )}
            </>
          )}
        </div>
      )
    }

    return this.props.children
  }
}
