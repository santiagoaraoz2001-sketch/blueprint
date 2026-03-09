import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useModelHubStore, type LocalModel } from '@/stores/modelHubStore'
import { useAgentStore } from '@/stores/agentStore'
import { ChevronDown, Search, HardDrive, Cloud, PenLine, RefreshCw } from 'lucide-react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ModelSelectorProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
}

interface ModelOption {
  id: string
  label: string
  section: 'local' | 'llm' | 'custom'
  format?: string
  sizeBytes?: number
  quant?: string | null
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatBytes(bytes: number): string {
  if (bytes < 1_000_000_000) {
    const mb = bytes / 1_000_000
    return `${mb.toFixed(1)} MB`
  }
  const gb = bytes / 1_000_000_000
  return `${gb.toFixed(1)} GB`
}

const FORMAT_COLORS: Record<string, string> = {
  gguf: '#4af6c3',
  safetensors: '#6C9EFF',
  pytorch: '#FB923C',
  onnx: '#B87EFF',
  mlx: '#F472B6',
}

function getFormatColor(format: string): string {
  return FORMAT_COLORS[format.toLowerCase()] ?? '#94A3B8'
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function FormatBadge({ format }: { format: string }) {
  const color = getFormatColor(format)
  return (
    <span
      style={{
        padding: '0px 4px',
        fontFamily: F,
        fontSize: FS.xxs,
        fontWeight: 700,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        color,
        background: `${color}15`,
        border: `1px solid ${color}30`,
        lineHeight: '14px',
        whiteSpace: 'nowrap',
      }}
    >
      {format.toUpperCase()}
    </span>
  )
}

function SectionHeader({ label, icon }: { label: string; icon: React.ReactNode }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 5,
        padding: '6px 8px 4px',
        fontFamily: F,
        fontSize: FS.xxs,
        fontWeight: 900,
        letterSpacing: '0.14em',
        textTransform: 'uppercase',
        color: T.dim,
        userSelect: 'none',
      }}
    >
      {icon}
      {label}
    </div>
  )
}

function OptionRow({
  option,
  isHighlighted,
  onClick,
  onMouseEnter,
}: {
  option: ModelOption
  isHighlighted: boolean
  onClick: () => void
  onMouseEnter: () => void
}) {
  return (
    <div
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '5px 8px',
        cursor: 'pointer',
        background: isHighlighted ? T.surface4 : 'transparent',
        transition: 'background 0.08s',
      }}
    >
      <span
        style={{
          flex: 1,
          fontFamily: F,
          fontSize: FS.sm,
          color: T.text,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {option.label}
      </span>

      {option.quant && (
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.amber,
            letterSpacing: '0.06em',
            whiteSpace: 'nowrap',
          }}
        >
          {option.quant}
        </span>
      )}

      {option.format && <FormatBadge format={option.format} />}

      {option.sizeBytes != null && option.sizeBytes > 0 && (
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.dim,
            whiteSpace: 'nowrap',
          }}
        >
          {formatBytes(option.sizeBytes)}
        </span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// ModelSelector
// ---------------------------------------------------------------------------

export default function ModelSelector({
  value,
  onChange,
  placeholder = 'Select model...',
}: ModelSelectorProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [customValue, setCustomValue] = useState('')
  const [highlightIndex, setHighlightIndex] = useState(-1)
  const [isScanning, setIsScanning] = useState(false)

  const containerRef = useRef<HTMLDivElement>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const localModels = useModelHubStore((s) => s.localModels)
  const fetchLocalModels = useModelHubStore((s) => s.fetchLocalModels)
  const availableModels = useAgentStore((s) => s.availableModels)
  const fetchModels = useAgentStore((s) => s.fetchModels)

  const handleRescan = useCallback(async () => {
    if (isScanning) return
    setIsScanning(true)
    try {
      await fetch('/api/models/local/scan', { method: 'POST' })
      await Promise.all([fetchLocalModels(), fetchModels()])
    } catch { /* ignore scan errors */ }
    setIsScanning(false)
  }, [isScanning, fetchLocalModels, fetchModels])

  // ---- Build option list ----

  const options = useMemo<ModelOption[]>(() => {
    const lowerSearch = search.toLowerCase()
    const result: ModelOption[] = []

    // Local models
    localModels.forEach((m: LocalModel) => {
      const matchesSearch =
        !lowerSearch ||
        m.name.toLowerCase().includes(lowerSearch) ||
        m.format.toLowerCase().includes(lowerSearch) ||
        (m.detected_quant?.toLowerCase().includes(lowerSearch) ?? false)

      if (matchesSearch) {
        result.push({
          id: `local::${m.path}`,
          label: m.name,
          section: 'local',
          format: m.format,
          sizeBytes: m.size_bytes,
          quant: m.detected_quant,
        })
      }
    })

    // LLM models from agent provider
    availableModels.forEach((name: string) => {
      const matchesSearch = !lowerSearch || name.toLowerCase().includes(lowerSearch)
      if (matchesSearch) {
        result.push({
          id: `llm::${name}`,
          label: name,
          section: 'llm',
        })
      }
    })

    return result
  }, [localModels, availableModels, search])

  const localOptions = useMemo(() => options.filter((o) => o.section === 'local'), [options])
  const llmOptions = useMemo(() => options.filter((o) => o.section === 'llm'), [options])

  // Flat list for keyboard navigation
  const flatOptions = useMemo(() => {
    const flat: ModelOption[] = []
    flat.push(...localOptions)
    flat.push(...llmOptions)
    return flat
  }, [localOptions, llmOptions])

  // ---- Handlers ----

  const open = useCallback(() => {
    setIsOpen(true)
    setSearch('')
    setHighlightIndex(-1)

    // Always re-fetch models on open so newly downloaded models appear
    fetchLocalModels()
    fetchModels()

    requestAnimationFrame(() => {
      searchInputRef.current?.focus()
    })
  }, [fetchLocalModels, fetchModels])

  const close = useCallback(() => {
    setIsOpen(false)
    setSearch('')
    setHighlightIndex(-1)
  }, [])

  const selectOption = useCallback(
    (option: ModelOption) => {
      // For local models, emit the model name (consumers can resolve path if needed)
      const emitValue = option.section === 'local' ? option.label : option.label
      onChange(emitValue)
      close()
    },
    [onChange, close],
  )

  const submitCustom = useCallback(() => {
    const trimmed = customValue.trim()
    if (trimmed) {
      onChange(trimmed)
      setCustomValue('')
      close()
    }
  }, [customValue, onChange, close])

  // ---- Click outside ----

  useEffect(() => {
    if (!isOpen) return

    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        close()
      }
    }

    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [isOpen, close])

  // ---- Keyboard navigation ----

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!isOpen) return

      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setHighlightIndex((prev) => (prev < flatOptions.length - 1 ? prev + 1 : 0))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setHighlightIndex((prev) => (prev > 0 ? prev - 1 : flatOptions.length - 1))
      } else if (e.key === 'Enter') {
        e.preventDefault()
        if (highlightIndex >= 0 && highlightIndex < flatOptions.length) {
          selectOption(flatOptions[highlightIndex])
        }
      } else if (e.key === 'Escape') {
        e.preventDefault()
        close()
      }
    },
    [isOpen, flatOptions, highlightIndex, selectOption, close],
  )

  // ---- Scroll highlighted item into view ----

  useEffect(() => {
    if (highlightIndex < 0 || !dropdownRef.current) return
    const items = dropdownRef.current.querySelectorAll('[data-option-index]')
    const target = items[highlightIndex] as HTMLElement | undefined
    target?.scrollIntoView({ block: 'nearest' })
  }, [highlightIndex])

  // ---- Styles ----

  const triggerStyle: React.CSSProperties = {
    width: '100%',
    padding: '4px 8px',
    background: T.surface4,
    border: `1px solid ${T.border}`,
    color: value ? T.text : T.dim,
    fontFamily: F,
    fontSize: FS.sm,
    outline: 'none',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 4,
    textAlign: 'left',
  }

  const dropdownStyle: React.CSSProperties = {
    position: 'absolute',
    top: '100%',
    left: 0,
    right: 0,
    marginTop: 2,
    background: T.surface2,
    border: `1px solid ${T.borderHi}`,
    boxShadow: `0 8px 24px ${T.shadow}`,
    zIndex: 1000,
    maxHeight: 280,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  }

  const searchInputStyle: React.CSSProperties = {
    width: '100%',
    padding: '5px 8px 5px 24px',
    background: T.surface3,
    border: 'none',
    borderBottom: `1px solid ${T.border}`,
    color: T.text,
    fontFamily: F,
    fontSize: FS.sm,
    outline: 'none',
  }

  const customInputStyle: React.CSSProperties = {
    flex: 1,
    padding: '4px 6px',
    background: T.surface4,
    border: `1px solid ${T.border}`,
    color: T.text,
    fontFamily: F,
    fontSize: FS.sm,
    outline: 'none',
  }

  // ---- Track cumulative index for keyboard nav ----

  let optionIndex = 0

  return (
    <div
      ref={containerRef}
      style={{ position: 'relative', width: '100%' }}
      onKeyDown={handleKeyDown}
    >
      {/* Trigger button */}
      <button
        type="button"
        onClick={() => (isOpen ? close() : open())}
        style={triggerStyle}
      >
        <span
          style={{
            flex: 1,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {value || placeholder}
        </span>
        <ChevronDown
          size={10}
          style={{
            color: T.dim,
            transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 0.15s',
            flexShrink: 0,
          }}
        />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div style={dropdownStyle}>
          {/* Search input + refresh */}
          <div style={{ position: 'relative', flexShrink: 0, display: 'flex', alignItems: 'stretch' }}>
            <div style={{ position: 'relative', flex: 1 }}>
              <Search
                size={10}
                style={{
                  position: 'absolute',
                  left: 8,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: T.dim,
                  pointerEvents: 'none',
                }}
              />
              <input
                ref={searchInputRef}
                type="text"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value)
                  setHighlightIndex(-1)
                }}
                placeholder="Search models..."
                style={searchInputStyle}
              />
            </div>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); handleRescan() }}
              title="Rescan local models"
              style={{
                background: isScanning ? `${T.cyan}15` : T.surface3,
                border: 'none',
                borderBottom: `1px solid ${T.border}`,
                borderLeft: `1px solid ${T.border}`,
                padding: '0 8px',
                cursor: isScanning ? 'wait' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <RefreshCw
                size={11}
                color={isScanning ? T.cyan : T.dim}
                style={{
                  animation: isScanning ? 'spin 1s linear infinite' : 'none',
                  transition: 'color 0.15s',
                }}
              />
              <style>{`@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }`}</style>
            </button>
          </div>

          {/* Scrollable list */}
          <div
            ref={dropdownRef}
            style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}
          >
            {/* Local Models Section */}
            {localOptions.length > 0 && (
              <>
                <SectionHeader
                  label="LOCAL MODELS"
                  icon={<HardDrive size={8} color={T.dim} />}
                />
                {localOptions.map((opt) => {
                  const idx = optionIndex++
                  return (
                    <div key={opt.id} data-option-index={idx}>
                      <OptionRow
                        option={opt}
                        isHighlighted={highlightIndex === idx}
                        onClick={() => selectOption(opt)}
                        onMouseEnter={() => setHighlightIndex(idx)}
                      />
                    </div>
                  )
                })}
              </>
            )}

            {/* LLM Models Section */}
            {llmOptions.length > 0 && (
              <>
                <SectionHeader
                  label="LLM MODELS"
                  icon={<Cloud size={8} color={T.dim} />}
                />
                {llmOptions.map((opt) => {
                  const idx = optionIndex++
                  return (
                    <div key={opt.id} data-option-index={idx}>
                      <OptionRow
                        option={opt}
                        isHighlighted={highlightIndex === idx}
                        onClick={() => selectOption(opt)}
                        onMouseEnter={() => setHighlightIndex(idx)}
                      />
                    </div>
                  )
                })}
              </>
            )}

            {/* Empty state */}
            {localOptions.length === 0 && llmOptions.length === 0 && (
              <div
                style={{
                  padding: '12px 8px',
                  fontFamily: F,
                  fontSize: FS.xs,
                  color: T.dim,
                  textAlign: 'center',
                }}
              >
                {search ? 'No models match your search' : 'No models detected'}
              </div>
            )}
          </div>

          {/* Custom entry section */}
          <div
            style={{
              borderTop: `1px solid ${T.border}`,
              padding: '6px 8px',
              flexShrink: 0,
            }}
          >
            <SectionHeader
              label="CUSTOM"
              icon={<PenLine size={8} color={T.dim} />}
            />
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                marginTop: 4,
              }}
            >
              <input
                type="text"
                value={customValue}
                onChange={(e) => setCustomValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    e.stopPropagation()
                    submitCustom()
                  }
                }}
                placeholder="model name or path..."
                style={customInputStyle}
              />
              <button
                type="button"
                onClick={submitCustom}
                style={{
                  padding: '4px 8px',
                  background: customValue.trim() ? `${T.cyan}20` : T.surface4,
                  border: `1px solid ${customValue.trim() ? `${T.cyan}40` : T.border}`,
                  color: customValue.trim() ? T.cyan : T.dim,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  fontWeight: 700,
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  cursor: customValue.trim() ? 'pointer' : 'default',
                  whiteSpace: 'nowrap',
                }}
              >
                USE
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
