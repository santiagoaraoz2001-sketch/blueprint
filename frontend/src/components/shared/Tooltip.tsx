import { useState, useRef, useCallback, useEffect } from 'react'
import ReactDOM from 'react-dom'
import { T, F, FS } from '@/lib/design-tokens'

interface TooltipProps {
  content: React.ReactNode
  shortcut?: string
  delay?: number
  position?: 'top' | 'bottom' | 'left' | 'right'
  children: React.ReactNode
}

const ARROW_GAP = 8

/**
 * Production-quality portal-based tooltip.
 *
 * Wraps children in an inline-flex span with hover/focus handlers rather than
 * using cloneElement. This avoids React warnings caused by merging refs or
 * event handlers onto components that don't expect them.
 */
export default function Tooltip({
  content,
  shortcut,
  delay = 300,
  position = 'top',
  children,
}: TooltipProps) {
  const [visible, setVisible] = useState(false)
  const [coords, setCoords] = useState<{ top: number; left: number }>({ top: 0, left: 0 })
  const triggerRef = useRef<HTMLSpanElement | null>(null)
  const tooltipRef = useRef<HTMLDivElement | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const computePosition = useCallback(() => {
    const trigger = triggerRef.current
    const tooltip = tooltipRef.current
    if (!trigger || !tooltip) return

    const rect = trigger.getBoundingClientRect()
    const tt = tooltip.getBoundingClientRect()
    const vw = window.innerWidth
    const vh = window.innerHeight

    let top = 0
    let left = 0

    switch (position) {
      case 'top':
        top = rect.top - tt.height - ARROW_GAP
        left = rect.left + rect.width / 2 - tt.width / 2
        break
      case 'bottom':
        top = rect.bottom + ARROW_GAP
        left = rect.left + rect.width / 2 - tt.width / 2
        break
      case 'left':
        top = rect.top + rect.height / 2 - tt.height / 2
        left = rect.left - tt.width - ARROW_GAP
        break
      case 'right':
        top = rect.top + rect.height / 2 - tt.height / 2
        left = rect.right + ARROW_GAP
        break
    }

    // Clamp to viewport
    if (left < 4) left = 4
    if (left + tt.width > vw - 4) left = vw - tt.width - 4
    if (top < 4) top = 4
    if (top + tt.height > vh - 4) top = vh - tt.height - 4

    setCoords({ top, left })
  }, [position])

  const show = useCallback(() => {
    timerRef.current = setTimeout(() => {
      setVisible(true)
    }, delay)
  }, [delay])

  const hide = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    setVisible(false)
  }, [])

  // Recompute position once the tooltip mounts and is measurable
  useEffect(() => {
    if (visible) {
      requestAnimationFrame(computePosition)
    }
  }, [visible, computePosition])

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  // Inject keyframes once
  useEffect(() => {
    const id = 'bp-tooltip-keyframes'
    if (document.getElementById(id)) return
    const style = document.createElement('style')
    style.id = id
    style.textContent = `@keyframes bp-tooltip-fadein { from { opacity: 0; } to { opacity: 1; } }`
    document.head.appendChild(style)
  }, [])

  const tooltipStyle: React.CSSProperties = {
    position: 'fixed',
    top: coords.top,
    left: coords.left,
    zIndex: 10000,
    background: T.surface5,
    color: T.text,
    border: `1px solid ${T.borderHi}`,
    fontFamily: F,
    fontSize: FS.xs,
    padding: '6px 10px',
    borderRadius: 6,
    pointerEvents: 'none',
    whiteSpace: 'nowrap',
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    animation: 'bp-tooltip-fadein 100ms ease-out',
  }

  return (
    <>
      <span
        ref={triggerRef}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        style={{ display: 'inline-flex', alignItems: 'center' }}
      >
        {children}
      </span>
      {visible &&
        ReactDOM.createPortal(
          <div ref={tooltipRef} style={tooltipStyle} role="tooltip">
            <span>{content}</span>
            {shortcut && (
              <span style={{ color: T.dim, fontSize: FS.xs }}>{shortcut}</span>
            )}
          </div>,
          document.body,
        )}
    </>
  )
}
