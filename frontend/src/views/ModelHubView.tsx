import { useState, useEffect, useRef, useCallback } from 'react'
import { T, F, FS, FD } from '@/lib/design-tokens'
import { useModelHubStore, type HFModel, type LocalModel } from '@/stores/modelHubStore'
import EmptyState from '@/components/shared/EmptyState'
import { Package, Search, RefreshCw, Download, Heart, HardDrive, Globe, MessageSquare } from 'lucide-react'
import { motion } from 'framer-motion'
import ChatInterface from '@/components/shared/ChatInterface'

type Tab = 'huggingface' | 'local'

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------

function formatDownloads(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function formatBytes(bytes: number): string {
  if (bytes >= 1_000_000_000) return `${(bytes / 1_000_000_000).toFixed(1)} GB`
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(0)} MB`
  if (bytes >= 1_000) return `${(bytes / 1_000).toFixed(0)} KB`
  return `${bytes} B`
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function FormatBadge({ format }: { format: string }) {
  const colorMap: Record<string, string> = {
    gguf: T.green,
    safetensors: T.cyan,
    pytorch: T.orange,
    onnx: T.purple,
    coreml: T.pink,
    tflite: T.amber,
  }
  const color = colorMap[format] || T.dim
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '1px 5px',
        background: `${color}18`,
        border: `1px solid ${color}33`,
        color,
        fontFamily: F,
        fontSize: FS.xxs,
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
      }}
    >
      {format}
    </span>
  )
}

function PipelineBadge({ tag }: { tag: string }) {
  if (!tag) return null
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '1px 5px',
        background: `${T.blue}18`,
        border: `1px solid ${T.blue}33`,
        color: T.blue,
        fontFamily: F,
        fontSize: FS.xxs,
        letterSpacing: '0.06em',
      }}
    >
      {tag}
    </span>
  )
}

function HFModelCard({ model, index }: { model: HFModel; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04, duration: 0.3, ease: 'easeOut' }}
      style={{
        background: T.surface1,
        border: `1px solid ${T.border}`,
        padding: 12,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        transition: 'border-color 0.15s, box-shadow 0.15s',
        cursor: 'default',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = T.borderHi
        e.currentTarget.style.boxShadow = `0 0 12px ${T.cyan}10`
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = T.border
        e.currentTarget.style.boxShadow = 'none'
      }}
    >
      {/* Model ID */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span
          style={{
            fontFamily: FD,
            fontSize: FS.md,
            fontWeight: 600,
            color: T.text,
            letterSpacing: '0.02em',
            wordBreak: 'break-all',
          }}
        >
          {model.id}
        </span>
      </div>

      {/* Author */}
      <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>
        by {model.author}
      </span>

      {/* Badges row */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        <PipelineBadge tag={model.pipeline_tag} />
        {model.formats.map((fmt) => (
          <FormatBadge key={fmt} format={fmt} />
        ))}
      </div>

      {/* Stats row */}
      <div style={{ display: 'flex', gap: 12, marginTop: 'auto' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 3, fontFamily: F, fontSize: FS.xs, color: T.sec }}>
          <Download size={8} />
          {formatDownloads(model.downloads)}
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 3, fontFamily: F, fontSize: FS.xs, color: T.sec }}>
          <Heart size={8} />
          {formatDownloads(model.likes)}
        </span>
      </div>
    </motion.div>
  )
}

function LocalModelRow({ model, index, onVibeCheck }: { model: LocalModel; index: number; onVibeCheck: (name: string) => void }) {
  return (
    <motion.tr
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.03, duration: 0.25 }}
    >
      <td style={{ padding: '6px 10px', fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 500 }}>
        {model.name}
      </td>
      <td style={{ padding: '6px 10px' }}>
        <FormatBadge format={model.format} />
      </td>
      <td style={{ padding: '6px 10px', fontFamily: F, fontSize: FS.xs, color: T.sec, textAlign: 'right' }}>
        {formatBytes(model.size_bytes)}
      </td>
      <td style={{ padding: '6px 10px', fontFamily: F, fontSize: FS.xxs, color: T.dim, maxWidth: 250, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {model.path}
      </td>
      <td style={{ padding: '6px 10px', fontFamily: F, fontSize: FS.xs, color: model.detected_quant ? T.green : T.dim }}>
        {model.detected_quant || '-'}
      </td>
      <td style={{ padding: '6px 10px', textAlign: 'right' }}>
        <button
          onClick={() => onVibeCheck(model.name)}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            padding: '4px 8px', background: `${T.cyan}10`, border: `1px solid ${T.cyan}33`,
            color: T.cyan, fontFamily: F, fontSize: FS.xxs, cursor: 'pointer'
          }}
        >
          <MessageSquare size={10} />
          VIBE CHECK
        </button>
      </td>
    </motion.tr>
  )
}

// ---------------------------------------------------------------------------
// Main View
// ---------------------------------------------------------------------------

export default function ModelHubView() {
  const {
    searchResults,
    localModels,
    searchQuery,
    loading,
    error,
    searchModels,
    fetchLocalModels,
    triggerScan,
    setSearchQuery,
  } = useModelHubStore()

  const [activeTab, setActiveTab] = useState<Tab>('huggingface')
  const [chatModel, setChatModel] = useState<string | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Initial loads
  useEffect(() => {
    searchModels('')
    fetchLocalModels()
  }, [searchModels, fetchLocalModels])

  const handleSearchChange = useCallback(
    (value: string) => {
      setSearchQuery(value)
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        searchModels(value)
      }, 300)
    },
    [setSearchQuery, searchModels]
  )

  const tabs: { id: Tab; label: string; icon: typeof Globe }[] = [
    { id: 'huggingface', label: 'HUGGINGFACE', icon: Globe },
    { id: 'local', label: 'LOCAL MODELS', icon: HardDrive },
  ]

  const headerBtnStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    padding: '3px 10px',
    background: T.surface3,
    border: `1px solid ${T.border}`,
    color: T.sec,
    fontFamily: F,
    fontSize: FS.xs,
    letterSpacing: '0.06em',
    textTransform: 'uppercase',
    cursor: 'pointer',
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div
        style={{
          padding: '12px 16px 0',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}
      >
        <h2
          style={{
            fontFamily: FD,
            fontSize: FS.h2,
            fontWeight: 600,
            color: T.text,
            margin: 0,
            letterSpacing: '0.04em',
          }}
        >
          MODEL HUB
        </h2>

        <div style={{ flex: 1 }} />

        {/* Search input */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '3px 10px',
            background: T.surface3,
            border: `1px solid ${T.border}`,
            minWidth: 220,
          }}
        >
          <Search size={10} color={T.dim} />
          <input
            value={searchQuery}
            onChange={(e) => handleSearchChange(e.target.value)}
            placeholder="Search models..."
            style={{
              flex: 1,
              background: 'none',
              border: 'none',
              color: T.text,
              fontFamily: F,
              fontSize: FS.md,
              outline: 'none',
            }}
          />
        </div>

        {/* Scan button (only visible on local tab) */}
        {activeTab === 'local' && (
          <button
            onClick={() => triggerScan()}
            style={headerBtnStyle}
          >
            <RefreshCw size={9} />
            SCAN
          </button>
        )}
      </div>

      {/* Tabs */}
      <div
        style={{
          display: 'flex',
          gap: 0,
          padding: '10px 16px 0',
          borderBottom: `1px solid ${T.border}`,
        }}
      >
        {tabs.map((tab) => {
          const Icon = tab.icon
          const active = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: '6px 14px',
                background: active ? T.surface2 : 'transparent',
                border: 'none',
                borderBottom: active ? `2px solid ${T.cyan}` : '2px solid transparent',
                color: active ? T.cyan : T.dim,
                fontFamily: F,
                fontSize: FS.xs,
                letterSpacing: '0.08em',
                marginBottom: -1,
                cursor: 'pointer',
              }}
            >
              <Icon size={10} />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Error banner */}
      {error && (
        <div
          style={{
            margin: '8px 16px 0',
            padding: '6px 10px',
            background: `${T.red}14`,
            border: `1px solid ${T.red}33`,
            fontFamily: F,
            fontSize: FS.xs,
            color: T.red,
          }}
        >
          {error}
        </div>
      )}

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center' }}>
            <span style={{ fontFamily: F, fontSize: FS.md, color: T.dim }}>Loading...</span>
          </div>
        ) : activeTab === 'huggingface' ? (
          /* HuggingFace tab */
          searchResults.length === 0 ? (
            <EmptyState
              icon={Package}
              title="No models found"
              description={searchQuery ? `No results for "${searchQuery}"` : 'Search HuggingFace for models'}
            />
          ) : (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
                gap: 10,
              }}
            >
              {searchResults.map((model, i) => (
                <HFModelCard key={model.id} model={model} index={i} />
              ))}
            </div>
          )
        ) : (
          /* Local models tab */
          localModels.length === 0 ? (
            <EmptyState
              icon={HardDrive}
              title="No local models detected"
              description="Click SCAN to search common model directories"
              action={{ label: 'Scan Now', onClick: () => triggerScan() }}
            />
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table
                style={{
                  width: '100%',
                  borderCollapse: 'collapse',
                  fontFamily: F,
                }}
              >
                <thead>
                  <tr>
                    {['NAME', 'FORMAT', 'SIZE', 'PATH', 'QUANT', ''].map((col) => (
                      <th
                        key={col}
                        style={{
                          padding: '6px 10px',
                          textAlign: col === 'SIZE' ? 'right' : 'left',
                          fontFamily: F,
                          fontSize: FS.xxs,
                          fontWeight: 600,
                          color: T.dim,
                          letterSpacing: '0.1em',
                          borderBottom: `1px solid ${T.border}`,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {localModels.map((model, i) => (
                    <LocalModelRow key={model.path} model={model} index={i} onVibeCheck={setChatModel} />
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </div>

      {chatModel && (
        <ChatInterface modelId={chatModel} onClose={() => setChatModel(null)} />
      )}
    </div>
  )
}
