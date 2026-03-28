import { useState, useEffect, useMemo } from 'react'
import { motion } from 'framer-motion'
import { T, F, FS } from '@/lib/design-tokens'
import { api } from '@/api/client'
import {
  LayoutTemplate, Clock, Search, X, AlertCircle,
  Cpu, Server, Zap,
} from 'lucide-react'

export interface TemplateSummary {
  id: string
  name: string
  description: string
  difficulty: 'beginner' | 'intermediate' | 'advanced'
  estimated_runtime: string
  required_services: string[]
  required_capabilities: string[]
  block_count: number
  tags: string[]
}

interface TemplateGalleryProps {
  onSelectTemplate: (templateId: string) => void
  onBlankCanvas?: () => void
  embedded?: boolean // true = landing page mode (no close button)
  onClose?: () => void
}

const DIFFICULTY_COLORS: Record<string, string> = {
  beginner: '#34D399',
  intermediate: '#FBBF24',
  advanced: '#F43F5E',
}

const SERVICE_ICONS: Record<string, React.ReactNode> = {
  ollama: <Server size={10} />,
  torch: <Cpu size={10} />,
}

export default function TemplateGallery({ onSelectTemplate, onBlankCanvas, embedded, onClose }: TemplateGalleryProps) {
  const [templates, setTemplates] = useState<TemplateSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    api.get<TemplateSummary[]>('/templates')
      .then((data) => {
        setTemplates(data)
        setError(null)
      })
      .catch((err) => setError(err.message || 'Failed to load templates'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!embedded) {
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape') onClose?.()
      }
      window.addEventListener('keydown', handleKeyDown)
      return () => window.removeEventListener('keydown', handleKeyDown)
    }
  }, [embedded, onClose])

  const filtered = useMemo(() => {
    if (!searchQuery.trim()) return templates
    const q = searchQuery.toLowerCase()
    return templates.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        t.difficulty.includes(q) ||
        t.tags.some((tag) => tag.includes(q)),
    )
  }, [templates, searchQuery])

  const content = (
    <div style={{
      width: embedded ? '100%' : undefined,
      maxWidth: embedded ? 1000 : undefined,
      margin: embedded ? '0 auto' : undefined,
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: embedded ? '32px 0 20px' : '16px 20px',
        borderBottom: embedded ? 'none' : `1px solid ${T.border}`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <LayoutTemplate size={16} color={T.cyan} />
          <span style={{
            fontFamily: F, fontSize: embedded ? 20 : FS.lg, fontWeight: 700,
            color: T.text, letterSpacing: '0.06em',
          }}>
            {embedded ? 'GET STARTED' : 'NEW FROM TEMPLATE'}
          </span>
        </div>
        {!embedded && onClose && (
          <button
            onClick={onClose}
            style={{
              background: 'none', border: 'none', color: T.dim,
              cursor: 'pointer', padding: 4, display: 'flex',
            }}
            aria-label="Close"
          >
            <X size={14} />
          </button>
        )}
      </div>

      {embedded && (
        <p style={{
          fontFamily: F, fontSize: FS.sm, color: T.sec,
          margin: '0 0 20px', lineHeight: 1.5,
        }}>
          Choose a template to start building, or create a blank pipeline.
        </p>
      )}

      {/* Search */}
      <div style={{
        padding: embedded ? '0 0 16px' : '10px 20px',
        display: 'flex', alignItems: 'center', gap: 8,
        borderBottom: embedded ? 'none' : `1px solid ${T.border}`,
      }}>
        <Search size={12} color={T.dim} />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search templates..."
          style={{
            flex: 1, background: 'none', border: 'none', outline: 'none',
            color: T.text, fontFamily: F, fontSize: FS.sm,
          }}
        />
        {searchQuery && (
          <button
            onClick={() => setSearchQuery('')}
            style={{
              background: 'none', border: 'none', color: T.dim,
              cursor: 'pointer', padding: 2, display: 'flex',
            }}
          >
            <X size={10} />
          </button>
        )}
      </div>

      {/* Grid */}
      {loading ? (
        <div style={{ padding: 40, textAlign: 'center' }}>
          <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>Loading templates...</span>
        </div>
      ) : error ? (
        <div style={{
          padding: 40, textAlign: 'center', display: 'flex',
          flexDirection: 'column', alignItems: 'center', gap: 8,
        }}>
          <AlertCircle size={16} color={T.red} />
          <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>{error}</span>
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: embedded
            ? 'repeat(auto-fill, minmax(280px, 1fr))'
            : 'repeat(auto-fill, minmax(260px, 1fr))',
          gap: 12,
          padding: embedded ? '0' : '16px 20px',
        }}>
          {/* Blank canvas card */}
          {onBlankCanvas && (
            <TemplateCard
              template={{
                id: 'blank',
                name: 'Blank Pipeline',
                description: 'Start from scratch with an empty canvas.',
                difficulty: 'beginner',
                estimated_runtime: '',
                required_services: [],
                required_capabilities: [],
                block_count: 0,
                tags: [],
              }}
              onClick={onBlankCanvas}
              isBlank
            />
          )}
          {filtered.map((tpl) => (
            <TemplateCard
              key={tpl.id}
              template={tpl}
              onClick={() => onSelectTemplate(tpl.id)}
            />
          ))}
          {filtered.length === 0 && !loading && (
            <div style={{
              gridColumn: '1 / -1', padding: 24, textAlign: 'center',
              fontFamily: F, fontSize: FS.xs, color: T.dim,
            }}>
              No templates match &ldquo;{searchQuery}&rdquo;
            </div>
          )}
        </div>
      )}
    </div>
  )

  if (embedded) {
    return content
  }

  // Modal mode
  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: T.shadowHeavy,
      }}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.2 }}
        style={{
          width: 720, maxHeight: '85vh',
          background: T.surface1, border: `1px solid ${T.borderHi}`,
          boxShadow: `0 16px 48px ${T.shadowHeavy}`,
          display: 'flex', flexDirection: 'column', overflow: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {content}
      </motion.div>
    </div>
  )
}

function TemplateCard({ template, onClick, isBlank }: {
  template: TemplateSummary
  onClick: () => void
  isBlank?: boolean
}) {
  const diffColor = DIFFICULTY_COLORS[template.difficulty] || T.dim

  return (
    <motion.div
      onClick={onClick}
      whileHover={{ scale: 1.01 }}
      style={{
        padding: '16px 18px',
        background: T.surface2,
        border: `1px solid ${T.border}`,
        cursor: 'pointer',
        transition: 'border-color 0.15s, box-shadow 0.15s',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        minHeight: 130,
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = `${T.cyan}60`
        e.currentTarget.style.boxShadow = `0 0 12px ${T.cyan}15`
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = T.border
        e.currentTarget.style.boxShadow = 'none'
      }}
    >
      {/* Name + badges */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        {isBlank ? (
          <Zap size={12} color={T.cyan} />
        ) : (
          <LayoutTemplate size={12} color={T.dim} />
        )}
        <span style={{
          fontFamily: F, fontSize: 16, fontWeight: 700, color: T.text,
          letterSpacing: '0.03em',
        }}>
          {template.name}
        </span>
      </div>

      {/* Description */}
      <div style={{
        fontFamily: F, fontSize: 14, color: T.sec, lineHeight: 1.5,
        display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
        overflow: 'hidden', flex: 1,
      }}>
        {template.description}
      </div>

      {/* Meta row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        {/* Difficulty badge */}
        {!isBlank && (
          <span style={{
            fontFamily: F, fontSize: FS.xxs, fontWeight: 700, letterSpacing: '0.1em',
            color: diffColor, background: `${diffColor}15`,
            border: `1px solid ${diffColor}30`, padding: '1px 6px',
            textTransform: 'uppercase',
          }}>
            {template.difficulty}
          </span>
        )}
        {/* Runtime */}
        {template.estimated_runtime && (
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 3,
            fontFamily: F, fontSize: FS.xxs, color: T.dim,
          }}>
            <Clock size={8} />
            {template.estimated_runtime}
          </span>
        )}
        {/* Required services */}
        {template.required_services.map((svc) => (
          <span key={svc} style={{
            display: 'inline-flex', alignItems: 'center', gap: 3,
            fontFamily: F, fontSize: FS.xxs, color: T.dim,
          }}>
            {SERVICE_ICONS[svc] || <Server size={8} />}
            {svc}
          </span>
        ))}
        {/* Block count */}
        {!isBlank && template.block_count > 0 && (
          <span style={{
            fontFamily: F, fontSize: FS.xxs, color: T.dim,
            letterSpacing: '0.08em', marginLeft: 'auto',
          }}>
            {template.block_count} BLOCKS
          </span>
        )}
      </div>
    </motion.div>
  )
}
