import { useState, useEffect, useRef, useMemo, createElement, type ReactNode } from 'react'
import { T, F, FS, FCODE } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import type { View } from '@/stores/uiStore'
import { api } from '@/api/client'
import { X, Loader, AlertCircle } from 'lucide-react'

/** Map the active view to a help topic slug */
function topicForView(view: View): string {
  switch (view) {
    case 'editor':
      return 'pipeline-editor'
    case 'results':
    case 'data':
    case 'visualization':
      return 'viewing-results'
    case 'settings':
      return 'configuration'
    case 'monitor':
      return 'running-pipelines'
    case 'datasets':
      return 'blocks'
    default:
      return 'getting-started'
  }
}

/** Human-readable title for a topic slug */
function titleForTopic(topic: string): string {
  return topic
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

// ---------------------------------------------------------------------------
// Safe markdown-to-ReactNode renderer (no dangerouslySetInnerHTML)
// Handles: h1, h2, h3, bold, inline code, code blocks, bullet lists, paragraphs
// ---------------------------------------------------------------------------

/** Parse inline formatting (**bold**, `code`) into React nodes */
function parseInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = []
  // Split by bold and code patterns, preserving matches
  const regex = /(\*\*(.+?)\*\*|`([^`]+)`)/g
  let lastIndex = 0
  let match: RegExpExecArray | null
  let partIdx = 0

  while ((match = regex.exec(text)) !== null) {
    // Text before the match
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index))
    }

    if (match[2]) {
      // Bold: **text**
      nodes.push(
        createElement('strong', { key: `${keyPrefix}-b${partIdx++}` }, match[2])
      )
    } else if (match[3]) {
      // Inline code: `text`
      nodes.push(
        createElement(
          'code',
          {
            key: `${keyPrefix}-c${partIdx++}`,
            style: {
              background: T.surface3,
              padding: '1px 5px',
              borderRadius: 3,
              fontFamily: FCODE,
              fontSize: FS.xs,
            },
          },
          match[3],
        ),
      )
    }
    lastIndex = match.index + match[0].length
  }

  // Remaining text
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex))
  }

  return nodes.length > 0 ? nodes : [text]
}

function renderMarkdownElements(md: string): ReactNode[] {
  const lines = md.split('\n')
  const elements: ReactNode[] = []
  let inCodeBlock = false
  let codeBuffer: string[] = []
  let listItems: ReactNode[] = []
  let elementIdx = 0

  function flushList() {
    if (listItems.length > 0) {
      elements.push(
        createElement(
          'ul',
          { key: `ul-${elementIdx++}`, style: { margin: '6px 0', paddingLeft: 20 } },
          ...listItems,
        ),
      )
      listItems = []
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]

    // Code blocks (```)
    if (line.trimStart().startsWith('```')) {
      if (inCodeBlock) {
        elements.push(
          createElement(
            'pre',
            {
              key: `pre-${elementIdx++}`,
              style: {
                background: T.surface3,
                padding: '12px 14px',
                borderRadius: 6,
                overflowX: 'auto' as const,
                fontFamily: FCODE,
                fontSize: FS.xs,
                lineHeight: 1.6,
                margin: '8px 0',
              },
            },
            codeBuffer.join('\n'),
          ),
        )
        codeBuffer = []
        inCodeBlock = false
      } else {
        flushList()
        inCodeBlock = true
      }
      continue
    }

    if (inCodeBlock) {
      codeBuffer.push(line)
      continue
    }

    // Blank line — close list
    if (line.trim() === '') {
      flushList()
      continue
    }

    // Headings
    if (line.startsWith('### ')) {
      flushList()
      elements.push(
        createElement(
          'h3',
          {
            key: `h3-${elementIdx++}`,
            style: { fontSize: FS.md, fontWeight: 700, color: T.text, margin: '16px 0 6px' },
          },
          ...parseInline(line.slice(4), `h3i-${elementIdx}`),
        ),
      )
      continue
    }
    if (line.startsWith('## ')) {
      flushList()
      elements.push(
        createElement(
          'h2',
          {
            key: `h2-${elementIdx++}`,
            style: { fontSize: FS.lg, fontWeight: 700, color: T.text, margin: '20px 0 8px' },
          },
          ...parseInline(line.slice(3), `h2i-${elementIdx}`),
        ),
      )
      continue
    }
    if (line.startsWith('# ')) {
      flushList()
      elements.push(
        createElement(
          'h1',
          {
            key: `h1-${elementIdx++}`,
            style: { fontSize: FS.xl, fontWeight: 700, color: T.text, margin: '20px 0 10px' },
          },
          ...parseInline(line.slice(2), `h1i-${elementIdx}`),
        ),
      )
      continue
    }

    // Bullet list items
    const bulletMatch = line.match(/^\s*[-*]\s+(.*)/)
    if (bulletMatch) {
      listItems.push(
        createElement(
          'li',
          { key: `li-${elementIdx++}`, style: { margin: '3px 0', lineHeight: 1.6 } },
          ...parseInline(bulletMatch[1], `lii-${elementIdx}`),
        ),
      )
      continue
    }

    // Regular paragraph
    flushList()
    elements.push(
      createElement(
        'p',
        { key: `p-${elementIdx++}`, style: { margin: '6px 0', lineHeight: 1.6 } },
        ...parseInline(line, `pi-${elementIdx}`),
      ),
    )
  }

  flushList()

  // Unclosed code block
  if (inCodeBlock && codeBuffer.length) {
    elements.push(
      createElement(
        'pre',
        {
          key: `pre-${elementIdx++}`,
          style: {
            background: T.surface3,
            padding: '12px 14px',
            borderRadius: 6,
            overflowX: 'auto' as const,
            fontFamily: FCODE,
            fontSize: FS.xs,
            lineHeight: 1.6,
            margin: '8px 0',
          },
        },
        codeBuffer.join('\n'),
      ),
    )
  }

  return elements
}

// ---------------------------------------------------------------------------

interface HelpContentResponse {
  topic: string
  content: string
}

export default function HelpPanel() {
  const helpPanelOpen = useUIStore((s) => s.helpPanelOpen)
  const toggleHelpPanel = useUIStore((s) => s.toggleHelpPanel)
  const activeView = useUIStore((s) => s.activeView)

  const topic = useMemo(() => topicForView(activeView), [activeView])
  const title = useMemo(() => titleForTopic(topic), [topic])

  const [content, setContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Fetch help content when topic changes
  useEffect(() => {
    if (!helpPanelOpen) return

    let cancelled = false
    setLoading(true)
    setError(null)

    api
      .get<HelpContentResponse>(`/system/help/${topic}`)
      .then((data) => {
        if (cancelled) return
        setContent(data.content || '')
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Failed to load help content')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [topic, helpPanelOpen])

  // Scroll to top on topic change
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 0 })
  }, [topic])

  // Memoize rendered elements to avoid re-parsing on every render
  const renderedElements = useMemo(
    () => (content ? renderMarkdownElements(content) : []),
    [content],
  )

  if (!helpPanelOpen) return null

  const panelStyle: React.CSSProperties = {
    position: 'fixed',
    top: 0,
    right: 0,
    width: 380,
    height: '100vh',
    background: T.surface1,
    borderLeft: `1px solid ${T.border}`,
    boxShadow: `-8px 0 24px rgba(0,0,0,0.35)`,
    display: 'flex',
    flexDirection: 'column',
    zIndex: 9000,
    fontFamily: F,
    fontSize: FS.sm,
    color: T.sec,
    animation: 'bp-help-slide-in 200ms ease-out',
  }

  const headerStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '14px 16px',
    borderBottom: `1px solid ${T.border}`,
    flexShrink: 0,
  }

  return (
    <>
      {/* Inject slide-in animation once */}
      <style>{`@keyframes bp-help-slide-in { from { transform: translateX(100%); } to { transform: translateX(0); } }`}</style>

      <aside style={panelStyle} role="complementary" aria-label="Help panel">
        {/* Header */}
        <div style={headerStyle}>
          <span style={{ fontFamily: F, fontSize: FS.md, fontWeight: 700, color: T.text }}>
            {title}
          </span>
          <button
            onClick={toggleHelpPanel}
            aria-label="Close help panel"
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: 4,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <X size={16} color={T.dim} />
          </button>
        </div>

        {/* Content */}
        <div
          ref={scrollRef}
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '16px 20px',
          }}
        >
          {loading && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                paddingTop: 60,
              }}
            >
              <Loader size={20} color={T.dim} className="animate-spin" />
            </div>
          )}

          {error && !loading && (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 12,
                paddingTop: 60,
                textAlign: 'center',
              }}
            >
              <AlertCircle size={28} color={T.dim} />
              <span style={{ color: T.dim, fontSize: FS.sm, lineHeight: 1.5 }}>{error}</span>
            </div>
          )}

          {!loading && !error && renderedElements.length > 0 && (
            <div>{renderedElements}</div>
          )}

          {!loading && !error && renderedElements.length === 0 && (
            <div
              style={{
                paddingTop: 60,
                textAlign: 'center',
                color: T.dim,
                fontSize: FS.sm,
              }}
            >
              No help content available for this section.
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
