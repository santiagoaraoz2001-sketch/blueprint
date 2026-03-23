import { useEffect, useRef } from 'react'
import { T, F, FD, FS } from '@/lib/design-tokens'

export interface SectionAnchorProps {
  id: string
  title: string
  level?: 1 | 2 | 3
  children?: React.ReactNode
}

/**
 * Deep-linkable section header with anchor.
 * Renders an h2/h3/h4 with an id for URL hash navigation.
 */
export default function SectionAnchor({ id, title, level = 2, children }: SectionAnchorProps) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (window.location.hash === `#${id}` && ref.current) {
      ref.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [id])

  const fontSize = level === 1 ? FS.xl : level === 2 ? FS.lg : FS.md
  const marginTop = level === 1 ? 48 : level === 2 ? 36 : 24
  const marginBottom = level === 1 ? 20 : level === 2 ? 14 : 10

  return (
    <div ref={ref} id={id} style={{ scrollMarginTop: 24 }}>
      <div
        style={{
          fontFamily: level === 1 ? FD : F,
          fontSize,
          fontWeight: level === 1 ? 800 : 700,
          color: T.text,
          marginTop,
          marginBottom,
          lineHeight: 1.3,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        {children}
        {title}
      </div>
    </div>
  )
}
