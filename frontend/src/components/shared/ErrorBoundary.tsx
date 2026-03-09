import { Component, type ReactNode } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { AlertTriangle, RotateCcw } from 'lucide-react'

interface Props {
  children: ReactNode
  fallbackLabel?: string
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
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
        </div>
      )
    }

    return this.props.children
  }
}
