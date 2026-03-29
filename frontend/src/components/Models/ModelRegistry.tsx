import { useState, useEffect, useCallback } from 'react'
import { T, FS } from '@/lib/design-tokens'
import { api } from '@/api/client'
import {
  Package, Search, Tag, HardDrive, Calendar, Link, ChevronRight,
  ArrowLeft, Trash2, Download, X, Rocket, MessageSquare,
} from 'lucide-react'
import DeployModal from '@/components/Deploy/DeployModal'
import ModelTestChat from '@/components/Deploy/ModelTestChat'
import toast from 'react-hot-toast'

interface ModelRecord {
  id: string
  name: string
  version: string
  format: string
  size_bytes: number | null
  source_run_id: string | null
  source_node_id: string | null
  metrics: Record<string, unknown>
  tags: string
  training_config: Record<string, unknown>
  source_data: string | null
  model_path: string | null
  created_at: string
}

interface ModelCard {
  model: ModelRecord
  provenance: {
    run_id: string | null
    node_id: string | null
    pipeline_id: string | null
    pipeline_name: string | null
  }
  training_config: Record<string, unknown>
  metrics: Record<string, unknown>
}

const FORMAT_COLORS: Record<string, string> = {
  gguf: '#FF8C4A',
  safetensors: '#5B96FF',
  onnx: '#3EF07A',
  pytorch: '#A87EFF',
}

function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function FormatBadge({ format }: { format: string }) {
  const t = T
  const color = FORMAT_COLORS[format] || t.dim
  return (
    <span style={{
      fontSize: FS.xs,
      padding: '2px 8px',
      borderRadius: 4,
      background: `${color}22`,
      color,
      fontWeight: 600,
      textTransform: 'uppercase',
      letterSpacing: 0.5,
    }}>
      {format}
    </span>
  )
}

function ModelCardView({ modelId, onBack }: { modelId: string; onBack: () => void }) {
  const [card, setCard] = useState<ModelCard | null>(null)
  const [loading, setLoading] = useState(true)
  const [showDeploy, setShowDeploy] = useState(false)
  const [showTestChat, setShowTestChat] = useState(false)
  const t = T

  useEffect(() => {
    setLoading(true)
    api.get<ModelCard>(`/models/registry/${modelId}/card`)
      .then(setCard)
      .catch(() => toast.error('Failed to load model card'))
      .finally(() => setLoading(false))
  }, [modelId])

  if (loading) {
    return <div style={{ padding: 24, textAlign: 'center', color: t.dim, fontSize: FS.sm }}>Loading model card...</div>
  }

  if (!card) {
    return <div style={{ padding: 24, textAlign: 'center', color: t.dim, fontSize: FS.sm }}>Model not found</div>
  }

  const { model, provenance, training_config, metrics } = card

  return (
    <div style={{ padding: 16 }}>
      {/* Back button */}
      <button
        onClick={onBack}
        style={{
          fontSize: FS.xs, display: 'flex', alignItems: 'center', gap: 4,
          color: t.cyan, background: 'none', border: 'none', cursor: 'pointer',
          padding: '4px 0', marginBottom: 12, fontWeight: 500,
        }}
      >
        <ArrowLeft size={14} /> Back to registry
      </button>

      {/* Model header */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <Package size={20} style={{ color: t.cyan }} />
          <h2 style={{ fontSize: FS.md, fontWeight: 700, color: t.text, margin: 0 }}>{model.name}</h2>
          <FormatBadge format={model.format} />
        </div>
        <div style={{ fontSize: FS.xs, color: t.dim, display: 'flex', gap: 12 }}>
          <span>v{model.version}</span>
          <span>{formatBytes(model.size_bytes)}</span>
          <span>{new Date(model.created_at).toLocaleDateString()}</span>
        </div>
      </div>

      {/* Tags */}
      {model.tags && (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 16 }}>
          {model.tags.split(',').filter(Boolean).map((tag) => (
            <span key={tag} style={{
              fontSize: FS.xs, padding: '2px 8px', borderRadius: 4,
              background: t.surface3, color: t.sec,
            }}>
              <Tag size={10} style={{ marginRight: 3 }} />{tag.trim()}
            </span>
          ))}
        </div>
      )}

      {/* Provenance */}
      <Section title="Provenance">
        <InfoRow label="Run ID" value={provenance.run_id || '—'} />
        <InfoRow label="Node ID" value={provenance.node_id || '—'} />
        <InfoRow label="Pipeline" value={provenance.pipeline_name || provenance.pipeline_id || '—'} />
        {model.source_data && <InfoRow label="Training Data" value={model.source_data} />}
        {model.model_path && <InfoRow label="Model Path" value={model.model_path} />}
      </Section>

      {/* Metrics */}
      {Object.keys(metrics).length > 0 && (
        <Section title="Metrics">
          {Object.entries(metrics).map(([key, value]) => (
            <InfoRow key={key} label={key} value={String(value)} />
          ))}
        </Section>
      )}

      {/* Training Config */}
      {Object.keys(training_config).length > 0 && (
        <Section title="Training Configuration">
          <div style={{
            fontSize: FS.xs, fontFamily: 'JetBrains Mono, monospace',
            background: t.surface2, borderRadius: 6, padding: 12,
            maxHeight: 200, overflowY: 'auto', color: t.sec,
            whiteSpace: 'pre-wrap', wordBreak: 'break-all',
          }}>
            {JSON.stringify(training_config, null, 2)}
          </div>
        </Section>
      )}

      {/* Actions */}
      <div style={{ marginTop: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button
          onClick={() => setShowDeploy(true)}
          style={{
            fontSize: FS.xs, padding: '8px 16px', borderRadius: 6,
            background: t.cyan, color: t.bg, border: 'none',
            cursor: 'pointer', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4,
          }}
        >
          <Rocket size={14} /> Deploy
        </button>
        <button
          onClick={() => setShowTestChat(true)}
          style={{
            fontSize: FS.xs, padding: '8px 16px', borderRadius: 6,
            background: 'none', color: t.cyan, border: `1px solid ${t.cyan}44`,
            cursor: 'pointer', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4,
          }}
        >
          <MessageSquare size={14} /> Test Model
        </button>
        {model.model_path && (
          <button style={{
            fontSize: FS.xs, padding: '8px 16px', borderRadius: 6,
            background: 'none', color: t.sec, border: `1px solid ${t.border}`,
            cursor: 'pointer', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4,
          }}>
            <Download size={14} /> Download
          </button>
        )}
      </div>

      {/* Deploy Modal */}
      {showDeploy && (
        <DeployModal
          modelId={model.id}
          modelName={model.name}
          modelFormat={model.format}
          modelPath={model.model_path}
          onClose={() => setShowDeploy(false)}
        />
      )}

      {/* Test Chat Modal */}
      {showTestChat && (
        <ModelTestChat
          modelName={model.name.toLowerCase().replace(/\s+/g, '-')}
          onClose={() => setShowTestChat(false)}
        />
      )}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const t = T
  return (
    <div style={{ marginBottom: 16 }}>
      <h3 style={{ fontSize: FS.xs, color: t.dim, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>
        {title}
      </h3>
      <div style={{ background: t.surface, borderRadius: 8, border: `1px solid ${t.border}`, padding: 10 }}>
        {children}
      </div>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  const t = T
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: `1px solid ${t.border}22` }}>
      <span style={{ fontSize: FS.xs, color: t.dim }}>{label}</span>
      <span style={{ fontSize: FS.xs, color: t.text, fontFamily: 'JetBrains Mono, monospace', maxWidth: '60%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{value}</span>
    </div>
  )
}

export default function ModelRegistry() {
  const [models, setModels] = useState<ModelRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [formatFilter, setFormatFilter] = useState<string | null>(null)
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null)
  const t = T

  const fetchModels = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (search) params.set('search', search)
      if (formatFilter) params.set('format', formatFilter)
      const qs = params.toString() ? `?${params.toString()}` : ''
      const list = await api.get<ModelRecord[]>(`/models/registry${qs}`)
      setModels(list || [])
    } catch {
      // Silent fail
    } finally {
      setLoading(false)
    }
  }, [search, formatFilter])

  useEffect(() => {
    fetchModels()
  }, [fetchModels])

  const handleDelete = useCallback(async (id: string) => {
    try {
      await api.delete(`/models/registry/${id}`)
      setModels((prev) => prev.filter((m) => m.id !== id))
      toast.success('Model deleted')
    } catch {
      toast.error('Failed to delete model')
    }
  }, [])

  // Show model card detail view
  if (selectedModelId) {
    return <ModelCardView modelId={selectedModelId} onBack={() => setSelectedModelId(null)} />
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px',
        borderBottom: `1px solid ${t.border}`,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <Package size={16} style={{ color: t.purple }} />
        <span style={{ fontSize: FS.sm, fontWeight: 600, color: t.text }}>Model Registry</span>
        <span style={{
          fontSize: FS.xs, color: t.dim, marginLeft: 'auto',
          background: t.surface3, borderRadius: 8, padding: '2px 8px',
        }}>
          {models.length}
        </span>
      </div>

      {/* Search & Filters */}
      <div style={{ padding: '8px 12px', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: t.surface2, borderRadius: 6, padding: '4px 10px', flex: 1, minWidth: 120,
        }}>
          <Search size={13} style={{ color: t.dim }} />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search models..."
            style={{
              fontSize: FS.xs, background: 'none', border: 'none', outline: 'none',
              color: t.text, width: '100%',
            }}
          />
          {search && (
            <X size={12} style={{ color: t.dim, cursor: 'pointer' }} onClick={() => setSearch('')} />
          )}
        </div>
        {['gguf', 'safetensors', 'onnx', 'pytorch'].map((fmt) => (
          <button
            key={fmt}
            onClick={() => setFormatFilter(formatFilter === fmt ? null : fmt)}
            style={{
              fontSize: FS.xs, padding: '4px 8px', borderRadius: 4,
              border: `1px solid ${formatFilter === fmt ? (FORMAT_COLORS[fmt] || t.border) : t.border}`,
              background: formatFilter === fmt ? `${FORMAT_COLORS[fmt] || t.cyan}22` : 'transparent',
              color: formatFilter === fmt ? (FORMAT_COLORS[fmt] || t.cyan) : t.dim,
              cursor: 'pointer', fontWeight: 500,
            }}
          >
            {fmt}
          </button>
        ))}
      </div>

      {/* Model list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px 8px' }}>
        {loading && (
          <div style={{ padding: 24, textAlign: 'center', color: t.dim, fontSize: FS.sm }}>
            Loading models...
          </div>
        )}
        {!loading && models.length === 0 && (
          <div style={{ padding: 24, textAlign: 'center', color: t.dim }}>
            <Package size={32} style={{ marginBottom: 8, opacity: 0.4 }} />
            <p style={{ fontSize: FS.sm, margin: 0 }}>No models registered yet.</p>
            <p style={{ fontSize: FS.xs, marginTop: 4 }}>Models are auto-registered when training or merge blocks complete.</p>
          </div>
        )}
        {models.map((model) => (
          <div
            key={model.id}
            onClick={() => setSelectedModelId(model.id)}
            style={{
              padding: '10px 12px',
              marginBottom: 4,
              borderRadius: 8,
              border: `1px solid ${t.border}`,
              background: t.surface,
              cursor: 'pointer',
              transition: 'border-color 0.15s ease',
              display: 'flex', alignItems: 'center', gap: 10,
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.borderColor = t.borderHi }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.borderColor = t.border }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <span style={{ fontSize: FS.sm, fontWeight: 600, color: t.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {model.name}
                </span>
                <FormatBadge format={model.format} />
              </div>
              <div style={{ fontSize: FS.xs, color: t.dim, display: 'flex', gap: 12 }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                  <HardDrive size={10} /> {formatBytes(model.size_bytes)}
                </span>
                {model.source_run_id && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                    <Link size={10} /> Run
                  </span>
                )}
                <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                  <Calendar size={10} /> {new Date(model.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); handleDelete(model.id) }}
              style={{
                background: 'none', border: 'none', cursor: 'pointer', color: t.dim, padding: 4,
              }}
              title="Delete model"
            >
              <Trash2 size={14} />
            </button>
            <ChevronRight size={14} style={{ color: t.dim }} />
          </div>
        ))}
      </div>
    </div>
  )
}
