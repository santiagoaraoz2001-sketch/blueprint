import { T, F, FS } from '@/lib/design-tokens'
import { PIPELINE_TEMPLATES, type PipelineTemplate } from '@/lib/pipeline-templates'
import { useEffect, useState } from 'react'
import { usePipelineStore } from '@/stores/pipelineStore'
import { X, LayoutTemplate, Cpu, Database, BrainCircuit, GitMerge, FlaskConical, MessageSquare } from 'lucide-react'
import toast from 'react-hot-toast'

interface TemplateSelectorProps {
  onClose: () => void
}

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  source: <Database size={10} />,
  transform: <FlaskConical size={10} />,
  training: <Cpu size={10} />,
  inference: <MessageSquare size={10} />,
  evaluate: <FlaskConical size={10} />,
  merge: <GitMerge size={10} />,
  agents: <BrainCircuit size={10} />,
  flow: <Database size={10} />,
}

const CATEGORY_BADGE_COLORS: Record<string, string> = {
  source: '#F97316',
  transform: '#FACC15',
  training: '#3B82F6',
  inference: '#8B5CF6',
  evaluate: '#10B981',
  merge: '#EC4899',
  agents: '#F43F5E',
  flow: '#64748B',
}

export default function TemplateSelector({ onClose }: TemplateSelectorProps) {
  const newPipeline = usePipelineStore((s) => s.newPipeline)
  const [customTemplates, setCustomTemplates] = useState<any[]>([])

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

  const allTemplates = [...customTemplates.reverse(), ...PIPELINE_TEMPLATES]

  const handleSelect = (template: PipelineTemplate) => {
    newPipeline()

    // Use setTimeout to allow newPipeline state to flush before setting nodes/edges
    setTimeout(() => {
      usePipelineStore.setState({
        name: template.name,
        nodes: template.nodes,
        edges: template.edges,
        isDirty: true,
      })
      toast.success(`Loaded template: ${template.name}`)
    }, 0)

    onClose()
  }

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
    >
      <div
        style={{
          width: 640,
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
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '12px 16px',
            borderBottom: `1px solid ${T.border}`,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <LayoutTemplate size={12} color={T.cyan} />
            <span
              style={{
                fontFamily: F,
                fontSize: FS.lg,
                fontWeight: 700,
                color: T.text,
                letterSpacing: '0.06em',
              }}
            >
              PIPELINE TEMPLATES
            </span>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: T.dim,
              cursor: 'pointer',
              padding: 4,
              display: 'flex',
            }}
          >
            <X size={14} />
          </button>
        </div>

        {/* Description */}
        <div style={{ padding: '8px 16px', borderBottom: `1px solid ${T.border}` }}>
          <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>
            Start from a pre-built pipeline. Select a template to create a new pipeline with pre-configured blocks.
          </span>
        </div>

        {/* Template list */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {allTemplates.map((tpl) => {
            const badgeColor = CATEGORY_BADGE_COLORS[tpl.category] || T.dim
            return (
              <div
                key={tpl.id}
                onClick={() => handleSelect(tpl)}
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
                {/* Top row: name + badge */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <span
                    style={{
                      fontFamily: F,
                      fontSize: FS.md,
                      fontWeight: 700,
                      color: T.text,
                      letterSpacing: '0.04em',
                    }}
                  >
                    {tpl.name}
                  </span>
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 3,
                      fontFamily: F,
                      fontSize: FS.xxs,
                      fontWeight: 700,
                      letterSpacing: '0.1em',
                      color: badgeColor,
                      background: `${badgeColor}15`,
                      border: `1px solid ${badgeColor}30`,
                      padding: '1px 6px',
                      textTransform: 'uppercase',
                    }}
                  >
                    {CATEGORY_ICONS[tpl.category]}
                    {tpl.category}
                  </span>
                </div>

                {/* Description */}
                <div
                  style={{
                    fontFamily: F,
                    fontSize: FS.xs,
                    color: T.sec,
                    lineHeight: 1.5,
                    marginBottom: 6,
                  }}
                >
                  {tpl.description}
                </div>

                {/* Block count */}
                <span
                  style={{
                    fontFamily: F,
                    fontSize: FS.xxs,
                    color: T.dim,
                    letterSpacing: '0.08em',
                  }}
                >
                  {tpl.blockCount} BLOCKS
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
