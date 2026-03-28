import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { T, F, FS, CATEGORY_COLORS, DEPTH } from '@/lib/design-tokens'
import { getAllBlocks } from '@/lib/block-registry'
import type { BlockDefinition } from '@/lib/block-registry-types'
import { BLOCK_ALIASES, CATEGORY_ALIASES } from '@/lib/search-aliases'
import { getIcon } from '@/lib/icon-utils'
import { Search } from 'lucide-react'

const RECENTLY_USED_KEY = 'blueprint-recently-used-blocks'
const MAX_RECENT = 5
const MAX_VISIBLE = 8

function getRecentlyUsed(): string[] {
  try {
    const raw = localStorage.getItem(RECENTLY_USED_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function addRecentlyUsed(blockType: string): void {
  try {
    const recent = getRecentlyUsed().filter((t) => t !== blockType)
    recent.unshift(blockType)
    localStorage.setItem(RECENTLY_USED_KEY, JSON.stringify(recent.slice(0, MAX_RECENT)))
  } catch { /* quota exceeded, etc. */ }
}

function scoreBlock(block: BlockDefinition, query: string): number {
  const q = query.toLowerCase()
  const nameLower = block.name.toLowerCase()

  if (nameLower === q) return 100
  if (nameLower.startsWith(q)) return 80
  if (nameLower.includes(q)) return 50
  if (block.description.toLowerCase().includes(q)) return 20

  // Search port data_types (e.g. 'dataset' finds all blocks with dataset ports)
  if (block.inputs.some((i) => i.dataType.toLowerCase().includes(q))) return 15
  if (block.outputs.some((o) => o.dataType.toLowerCase().includes(q))) return 15

  // Block aliases and tags
  if (block.aliases?.some((a: string) => a.toLowerCase().includes(q))) return 45
  if (block.tags?.some((t: string) => t.toLowerCase().includes(q))) return 35

  // Search aliases (only for queries > 2 chars)
  if (q.length > 2) {
    const aliases = BLOCK_ALIASES[block.type] || []
    if (aliases.some((a) => a === q)) return 60
    if (aliases.some((a) => a.includes(q))) return 40
    const catAliases = CATEGORY_ALIASES[block.category] || []
    if (catAliases.some((a) => a.includes(q))) return 10
  }

  return 0
}

interface BlockSearchProps {
  onAddBlock: (blockType: string, position: { x: number; y: number }) => void
  onShowBlockDoc?: (blockType: string) => void
  getViewportCenter: () => { x: number; y: number }
}

export default function BlockSearch({ onAddBlock, onShowBlockDoc, getViewportCenter }: BlockSearchProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  // ── Global Cmd+K / Ctrl+K listener ──
  // Uses capture phase to intercept before the browser's address-bar shortcut
  // (Chrome/Firefox Cmd+K focuses the URL bar). The capture phase ensures we
  // preventDefault() before the browser can act on it.
  //
  // Safety: When the modal is open, the search <input> has focus. PipelineCanvas's
  // keyboard handler already bails out for input/textarea targets, so canvas
  // shortcuts (f=fit, Delete, etc.) do not fire while the modal has focus.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey
      if (meta && e.key === 'k') {
        e.preventDefault()
        e.stopPropagation()
        setOpen((prev) => !prev)
      }
    }
    window.addEventListener('keydown', handleKeyDown, { capture: true })
    return () => window.removeEventListener('keydown', handleKeyDown, { capture: true })
  }, [])

  // Reset state when opening
  useEffect(() => {
    if (open) {
      setQuery('')
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  const allBlocks = useMemo(() => getAllBlocks(), [open])

  // Filter and rank results
  const results = useMemo(() => {
    if (!query.trim()) return []
    return allBlocks
      .map((block) => ({ block, score: scoreBlock(block, query.trim()) }))
      .filter(({ score }) => score > 0)
      .sort((a, b) => b.score - a.score)
      .map(({ block }) => block)
  }, [query, allBlocks])

  // Recently used blocks
  const recentBlocks = useMemo(() => {
    if (query.trim()) return []
    const recentTypes = getRecentlyUsed()
    return recentTypes
      .map((type) => allBlocks.find((b) => b.type === type))
      .filter(Boolean) as BlockDefinition[]
  }, [query, allBlocks])

  const displayResults = query.trim() ? results : recentBlocks
  const hasResults = displayResults.length > 0

  // Keep selected index in bounds
  useEffect(() => {
    setSelectedIndex(0)
  }, [query])

  // Scroll selected item into view
  useEffect(() => {
    if (!listRef.current) return
    const items = listRef.current.querySelectorAll('[data-search-item]')
    const selected = items[selectedIndex] as HTMLElement
    if (selected?.scrollIntoView) {
      selected.scrollIntoView({ block: 'nearest' })
    }
  }, [selectedIndex])

  const handleSelect = useCallback(
    (block: BlockDefinition, openDoc?: boolean) => {
      if (openDoc && onShowBlockDoc) {
        onShowBlockDoc(block.type)
      } else {
        addRecentlyUsed(block.type)
        const center = getViewportCenter()
        onAddBlock(block.type, center)
      }
      setOpen(false)
    },
    [onAddBlock, onShowBlockDoc, getViewportCenter]
  )

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const maxIndex = Math.min(displayResults.length, MAX_VISIBLE * 2) - 1

      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedIndex((i) => Math.min(i + 1, maxIndex))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedIndex((i) => Math.max(i - 1, 0))
      } else if (e.key === 'Enter') {
        e.preventDefault()
        const block = displayResults[selectedIndex]
        if (block) handleSelect(block, e.shiftKey)
      } else if (e.key === 'Escape') {
        e.preventDefault()
        setOpen(false)
      }
    },
    [displayResults, selectedIndex, handleSelect]
  )

  if (!open) return null

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.15 }}
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 9999,
          background: 'rgba(0,0,0,0.55)',
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'center',
          paddingTop: '15vh',
        }}
        onClick={() => setOpen(false)}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: -8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: -8 }}
          transition={{ type: 'spring', damping: 28, stiffness: 350 }}
          onClick={(e) => e.stopPropagation()}
          style={{
            width: 520,
            maxHeight: '60vh',
            background: `linear-gradient(145deg, ${T.surface2} 0%, ${T.surface1} 100%)`,
            border: `1px solid ${T.borderHi}`,
            borderRadius: 12,
            boxShadow: DEPTH.modal,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {/* Search input */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '14px 16px',
              borderBottom: `1px solid ${T.border}`,
            }}
          >
            <Search size={16} color={T.dim} />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search blocks by name, type, or capability..."
              style={{
                flex: 1,
                background: 'none',
                border: 'none',
                color: T.text,
                fontFamily: F,
                fontSize: FS.md,
                outline: 'none',
                caretColor: T.cyan,
              }}
            />
            <kbd
              style={{
                fontFamily: F,
                fontSize: FS.xxs,
                color: T.dim,
                background: T.surface4,
                padding: '2px 6px',
                borderRadius: 4,
                border: `1px solid ${T.border}`,
              }}
            >
              ESC
            </kbd>
          </div>

          {/* Results list */}
          <div
            ref={listRef}
            style={{
              overflowY: 'auto',
              padding: 6,
              scrollbarWidth: 'thin',
            }}
          >
            {/* Recently Used section header */}
            {!query.trim() && recentBlocks.length > 0 && (
              <div
                style={{
                  fontFamily: F,
                  fontSize: FS.xxs,
                  color: T.dim,
                  fontWeight: 900,
                  letterSpacing: '0.1em',
                  padding: '6px 10px 4px',
                  textTransform: 'uppercase',
                }}
              >
                Recently Used
              </div>
            )}

            {/* Empty state */}
            {!hasResults && (
              <div
                style={{
                  padding: '24px 16px',
                  textAlign: 'center',
                  fontFamily: F,
                  fontSize: FS.sm,
                  color: T.dim,
                }}
              >
                {query.trim()
                  ? `No blocks matching "${query}"`
                  : 'Type to search blocks...'}
              </div>
            )}

            {/* Results */}
            {displayResults.map((block, index) => (
              <SearchResultItem
                key={block.type}
                block={block}
                isSelected={index === selectedIndex}
                onClick={(e) => handleSelect(block, e.shiftKey)}
                onMouseEnter={() => setSelectedIndex(index)}
              />
            ))}
          </div>

          {/* Footer hint */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '8px 16px',
              borderTop: `1px solid ${T.border}`,
              background: T.surface0,
            }}
          >
            <FooterHint keys={['↑', '↓']} label="navigate" />
            <FooterHint keys={['↵']} label="add block" />
            <FooterHint keys={['⇧', '↵']} label="view docs" />
            <FooterHint keys={['esc']} label="close" />
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}

function SearchResultItem({
  block,
  isSelected,
  onClick,
  onMouseEnter,
}: {
  block: BlockDefinition
  isSelected: boolean
  onClick: (e: React.MouseEvent) => void
  onMouseEnter: () => void
}) {
  const IconComp = getIcon(block.icon)
  const catColor = CATEGORY_COLORS[block.category] || T.dim
  const inputCount = block.inputs.length
  const outputCount = block.outputs.length

  return (
    <button
      data-search-item
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        width: '100%',
        padding: '10px 12px',
        background: isSelected ? `${T.cyan}12` : 'transparent',
        border: isSelected ? `1px solid ${T.cyan}25` : '1px solid transparent',
        borderRadius: 8,
        cursor: 'pointer',
        textAlign: 'left',
        transition: 'background 0.1s, border-color 0.1s',
      }}
    >
      {/* Icon */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 32,
          height: 32,
          borderRadius: 6,
          background: `linear-gradient(135deg, ${T.surface3}, ${T.surface1})`,
          border: `1px solid ${T.borderHi}`,
          flexShrink: 0,
        }}
      >
        <IconComp size={14} color={block.accent || T.cyan} />
      </div>

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span
            style={{
              fontFamily: F,
              fontSize: FS.sm,
              color: T.text,
              fontWeight: 700,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {block.name}
          </span>
          {/* Category badge */}
          <span
            style={{
              fontFamily: F,
              fontSize: 9,
              color: catColor,
              background: `${catColor}15`,
              border: `1px solid ${catColor}30`,
              padding: '1px 6px',
              borderRadius: 4,
              fontWeight: 700,
              letterSpacing: '0.05em',
              textTransform: 'uppercase',
              flexShrink: 0,
            }}
          >
            {block.category}
          </span>
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginTop: 2,
          }}
        >
          <span
            style={{
              fontFamily: F,
              fontSize: FS.xxs,
              color: T.dim,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              flex: 1,
            }}
          >
            {block.description.split('\n')[0].slice(0, 80)}
            {block.description.length > 80 ? '...' : ''}
          </span>
          {/* Port summary */}
          <span
            style={{
              fontFamily: F,
              fontSize: 9,
              color: T.dim,
              flexShrink: 0,
              opacity: 0.7,
            }}
          >
            {inputCount} in, {outputCount} out
          </span>
        </div>
      </div>
    </button>
  )
}

function FooterHint({ keys, label }: { keys: string[]; label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      {keys.map((key) => (
        <kbd
          key={key}
          style={{
            fontFamily: F,
            fontSize: 9,
            color: T.dim,
            background: T.surface3,
            padding: '1px 4px',
            borderRadius: 3,
            border: `1px solid ${T.border}`,
            lineHeight: '14px',
          }}
        >
          {key}
        </kbd>
      ))}
      <span style={{ fontFamily: F, fontSize: 9, color: T.dim }}>{label}</span>
    </div>
  )
}
