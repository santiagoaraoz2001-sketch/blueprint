import { useState, useEffect, useCallback, useMemo } from 'react'
import { T, F, FS, CATEGORY_COLORS } from '@/lib/design-tokens'
import { PIPELINE_TEMPLATES, type PipelineTemplate, type TemplateDifficulty } from '@/lib/pipeline-templates'
import { usePipelineStore } from '@/stores/pipelineStore'
import TemplateVariableForm from './TemplateVariableForm'
import { X, LayoutTemplate, Clock, Variable, Search } from 'lucide-react'

interface TemplateGalleryProps {
  onClose: () => void
}

const DIFFICULTY_COLORS: Record<TemplateDifficulty, string> = {
  beginner: '#34D399',
  intermediate: '#FBBF24',
  advanced: '#F43F5E',
}

export default function TemplateGallery({ onClose }: TemplateGalleryProps) {
  const { instantiateTemplate, newPipeline } = usePipelineStore()
  const [selectedTemplate, setSelectedTemplate] = useState<PipelineTemplate | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [customTemplates, setCustomTemplates] = useState<PipelineTemplate[]>([])

  useEffect(() => {
    const stored = localStorage.getItem('blueprint-custom-templates')
    if (stored) {
      try {
        setCustomTemplates(JSON.parse(stored))
      } catch (e) {
        console.error('Failed to parse custom templates', e)
      }
    }
  }, [])

  // Escape key dismisses modal or goes back from variable form
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (selectedTemplate) {
          setSelectedTemplate(null)
        } else {
          onClose()
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [selectedTemplate, onClose])

  const allTemplates = useMemo(
    () => [...[...customTemplates].reverse(), ...PIPELINE_TEMPLATES],
    [customTemplates],
  )

  const filteredTemplates = useMemo(() => {
    if (!searchQuery.trim()) return allTemplates
    const q = searchQuery.toLowerCase()
    return allTemplates.filter(
      (tpl) =>
        tpl.name.toLowerCase().includes(q) ||
        tpl.description.toLowerCase().includes(q) ||
        tpl.category.toLowerCase().includes(q) ||
        (tpl.difficulty && tpl.difficulty.toLowerCase().includes(q)),
    )
  }, [allTemplates, searchQuery])

  const handleSelect = useCallback((template: PipelineTemplate) => {
    if (template.variables?.length) {
      setSelectedTemplate(template)
    } else {
      // No variables — instantiate directly (legacy behavior)
      newPipeline()
      setTimeout(() => {
        usePipelineStore.setState({
          name: template.name,
          nodes: template.nodes,
          edges: template.edges,
          isDirty: true,
        })
      }, 0)
      onClose()
    }
  }, [newPipeline, onClose])

  const handleInstantiate = useCallback((values: Record<string, any>) => {
    if (!selectedTemplate) return
    instantiateTemplate(selectedTemplate, values)
    onClose()
  }, [selectedTemplate, instantiateTemplate, onClose])

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: T.shadowHeavy,
      }}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Pipeline Templates"
    >
      <div
        style={{
          width: 680,
          maxHeight: '80vh',
          background: T.surface1,
          border: `1px solid ${T.borderHi}`,
          boxShadow: `0 16px 48px ${T.shadowHeavy}`,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {selectedTemplate ? (
          <TemplateVariableForm
            template={selectedTemplate}
            onSubmit={handleInstantiate}
            onBack={() => setSelectedTemplate(null)}
          />
        ) : (
          <>
            {/* Header */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '12px 16px', borderBottom: `1px solid ${T.border}`,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <LayoutTemplate size={12} color={T.cyan} />
                <span style={{
                  fontFamily: F, fontSize: FS.lg, fontWeight: 700, color: T.text,
                  letterSpacing: '0.06em',
                }}>
                  PIPELINE TEMPLATES
                </span>
              </div>
              <button
                onClick={onClose}
                style={{
                  background: 'none', border: 'none', color: T.dim,
                  cursor: 'pointer', padding: 4, display: 'flex',
                }}
                aria-label="Close template gallery"
              >
                <X size={14} />
              </button>
            </div>

            {/* Search bar */}
            <div style={{
              padding: '8px 16px',
              borderBottom: `1px solid ${T.border}`,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}>
              <Search size={12} color={T.dim} />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search templates..."
                autoFocus
                style={{
                  flex: 1,
                  background: 'none',
                  border: 'none',
                  outline: 'none',
                  color: T.text,
                  fontFamily: F,
                  fontSize: FS.sm,
                }}
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  style={{
                    background: 'none', border: 'none', color: T.dim,
                    cursor: 'pointer', padding: 2, display: 'flex',
                  }}
                  aria-label="Clear search"
                >
                  <X size={10} />
                </button>
              )}
            </div>

            {/* Template list */}
            <div style={{ flex: 1, overflowY: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {filteredTemplates.length === 0 ? (
                <div style={{
                  padding: '24px 16px',
                  textAlign: 'center',
                  fontFamily: F, fontSize: FS.xs, color: T.dim,
                }}>
                  No templates match &ldquo;{searchQuery}&rdquo;
                </div>
              ) : (
                filteredTemplates.map((tpl) => (
                  <TemplateCard
                    key={tpl.id}
                    template={tpl}
                    onClick={() => handleSelect(tpl)}
                  />
                ))
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function TemplateCard({ template, onClick }: { template: PipelineTemplate; onClick: () => void }) {
  const badgeColor = CATEGORY_COLORS[template.category] || T.dim
  const diffColor = template.difficulty ? DIFFICULTY_COLORS[template.difficulty] : null
  const hasVars = (template.variables?.length || 0) > 0

  return (
    <div
      onClick={onClick}
      style={{
        padding: '12px 14px',
        background: T.surface2,
        border: `1px solid ${T.border}`,
        cursor: 'pointer',
        transition: 'all 0.12s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = T.borderHi
        e.currentTarget.style.background = T.surface3
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = T.border
        e.currentTarget.style.background = T.surface2
      }}
    >
      {/* Top row: name + badges */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
        <span style={{
          fontFamily: F, fontSize: FS.md, fontWeight: 700, color: T.text,
          letterSpacing: '0.04em',
        }}>
          {template.name}
        </span>
        {/* Category badge */}
        <span style={{
          display: 'inline-flex', alignItems: 'center', gap: 3,
          fontFamily: F, fontSize: FS.xxs, fontWeight: 700, letterSpacing: '0.1em',
          color: badgeColor, background: `${badgeColor}15`, border: `1px solid ${badgeColor}30`,
          padding: '1px 6px', textTransform: 'uppercase',
        }}>
          {template.category}
        </span>
        {/* Difficulty badge */}
        {diffColor && template.difficulty && (
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 3,
            fontFamily: F, fontSize: FS.xxs, fontWeight: 700, letterSpacing: '0.1em',
            color: diffColor, background: `${diffColor}15`, border: `1px solid ${diffColor}30`,
            padding: '1px 6px', textTransform: 'uppercase',
          }}>
            {template.difficulty}
          </span>
        )}
      </div>

      {/* Description */}
      <div style={{
        fontFamily: F, fontSize: FS.xs, color: T.sec, lineHeight: 1.5, marginBottom: 6,
      }}>
        {template.description}
      </div>

      {/* Meta row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.08em' }}>
          {template.blockCount} BLOCKS
        </span>
        {template.estimatedTime && (
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 3,
            fontFamily: F, fontSize: FS.xxs, color: T.dim,
          }}>
            <Clock size={8} />
            ~{template.estimatedTime}
          </span>
        )}
        {hasVars && (
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 3,
            fontFamily: F, fontSize: FS.xxs, color: T.cyan,
          }}>
            <Variable size={8} />
            {template.variables!.length} variable{template.variables!.length > 1 ? 's' : ''}
          </span>
        )}
      </div>
    </div>
  )
}
