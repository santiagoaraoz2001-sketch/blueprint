import { useState, useMemo, useRef, useEffect } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { Search, X } from 'lucide-react'

export interface SearchableSection {
  id: string
  title: string
  text: string
}

interface HelpSearchProps {
  sections: SearchableSection[]
  onNavigate: (id: string) => void
}

export default function HelpSearch({ sections, onNavigate }: HelpSearchProps) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>()

  const [debouncedQuery, setDebouncedQuery] = useState('')

  useEffect(() => {
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => setDebouncedQuery(query), 200)
    return () => clearTimeout(debounceRef.current)
  }, [query])

  // Close dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Close dropdown on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) {
        setOpen(false)
        inputRef.current?.blur()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open])

  const results = useMemo(() => {
    const q = debouncedQuery.toLowerCase().trim()
    if (!q || q.length < 2) return []
    return sections
      .map((s) => {
        const titleIdx = s.title.toLowerCase().indexOf(q)
        const textIdx = s.text.toLowerCase().indexOf(q)
        if (titleIdx < 0 && textIdx < 0) return null
        const matchIdx = textIdx >= 0 ? textIdx : 0
        const start = Math.max(0, matchIdx - 40)
        const end = Math.min(s.text.length, matchIdx + q.length + 80)
        const excerpt =
          (start > 0 ? '...' : '') +
          s.text.slice(start, end) +
          (end < s.text.length ? '...' : '')
        return { ...s, excerpt, titleMatch: titleIdx >= 0 }
      })
      .filter(Boolean)
      .slice(0, 12) as (SearchableSection & { excerpt: string; titleMatch: boolean })[]
  }, [debouncedQuery, sections])

  return (
    <div ref={containerRef} style={{ position: 'relative' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 12px',
          background: T.surface2,
          border: `1px solid ${open ? T.accent : T.border}`,
          transition: 'border-color 0.15s',
        }}
      >
        <Search size={15} color={T.dim} />
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          placeholder="Search documentation..."
          style={{
            flex: 1,
            background: 'transparent',
            border: 'none',
            outline: 'none',
            fontFamily: F,
            fontSize: FS.sm,
            color: T.fg,
          }}
        />
        {query && (
          <X
            size={14}
            color={T.dim}
            style={{ cursor: 'pointer' }}
            onClick={() => {
              setQuery('')
              setOpen(false)
            }}
          />
        )}
      </div>

      {open && results.length > 0 && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            zIndex: 100,
            background: T.surface1,
            border: `1px solid ${T.border}`,
            borderTop: 'none',
            maxHeight: 400,
            overflowY: 'auto',
            boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
          }}
        >
          {results.map((r) => (
            <div
              key={r.id}
              onClick={() => {
                onNavigate(r.id)
                setOpen(false)
                setQuery('')
              }}
              style={{
                padding: '10px 14px',
                cursor: 'pointer',
                borderBottom: `1px solid ${T.border}`,
                transition: 'background 0.1s',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = T.surface2)}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <div
                style={{
                  fontFamily: F,
                  fontSize: FS.sm,
                  fontWeight: 600,
                  color: T.fg,
                  marginBottom: 3,
                }}
              >
                {r.title}
              </div>
              <div
                style={{
                  fontFamily: F,
                  fontSize: FS.xs,
                  color: T.dim,
                  lineHeight: 1.4,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {r.excerpt}
              </div>
            </div>
          ))}
        </div>
      )}

      {open && debouncedQuery.length >= 2 && results.length === 0 && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            zIndex: 100,
            background: T.surface1,
            border: `1px solid ${T.border}`,
            borderTop: 'none',
            padding: '16px 14px',
            fontFamily: F,
            fontSize: FS.sm,
            color: T.dim,
            textAlign: 'center',
          }}
        >
          No results found for &ldquo;{debouncedQuery}&rdquo;
        </div>
      )}
    </div>
  )
}
