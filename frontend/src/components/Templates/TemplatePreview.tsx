import { useState, useEffect, useCallback, useMemo } from 'react'
import { motion } from 'framer-motion'
import {
  ReactFlow,
  Background,
  type Node,
  type Edge,
} from '@xyflow/react'
import { T, F, FS } from '@/lib/design-tokens'
import { api } from '@/api/client'
import { usePipelineStore, type BlockNodeData } from '@/stores/pipelineStore'
import { useUIStore } from '@/stores/uiStore'
import {
  X, Play, ArrowLeft, CheckCircle2, XCircle, Loader2,
  Clock, AlertCircle,
} from 'lucide-react'
import toast from 'react-hot-toast'

interface TemplatePreviewProps {
  templateId: string
  onBack: () => void
  onClose: () => void
}

interface FullTemplate {
  id: string
  name: string
  description: string
  difficulty: string
  estimated_runtime: string
  required_services: string[]
  required_capabilities: string[]
  nodes: Node<BlockNodeData>[]
  edges: Edge[]
  tags: string[]
}

const DIFFICULTY_COLORS: Record<string, string> = {
  beginner: '#34D399',
  intermediate: '#FBBF24',
  advanced: '#F43F5E',
}

const WHAT_YOULL_LEARN: Record<string, string[]> = {
  'simple-chat': [
    'How to select and configure a model',
    'Sending prompts through chat completion',
    'Exporting LLM responses',
  ],
  'text-classification': [
    'Loading datasets from HuggingFace',
    'Splitting data for training and evaluation',
    'Fine-tuning a classification model',
    'Evaluating model performance',
  ],
  'lora-finetune': [
    'Setting up LoRA adapters for efficient fine-tuning',
    'Connecting datasets to training blocks',
    'Saving and evaluating fine-tuned models',
  ],
  'model-merge-compare': [
    'Merging two models with SLERP interpolation',
    'Running benchmarks on multiple models',
    'Comparing evaluation results side by side',
  ],
  'dataset-prep': [
    'Loading and transforming datasets',
    'Splitting data into train/val/test sets',
    'Exporting prepared data in various formats',
  ],
  'inference-pipeline': [
    'Creating reusable prompt templates',
    'Running LLM inference with custom models',
    'Saving inference outputs',
  ],
  'evaluation-suite': [
    'Running comprehensive model benchmarks',
    'Using LM Eval Harness tasks',
    'Formatting evaluation results',
  ],
  'dpo-training': [
    'Direct Preference Optimization training',
    'Using preference datasets for alignment',
    'Evaluating aligned models on safety benchmarks',
  ],
}

// Minimal read-only node component for the preview
function PreviewNode({ data }: { data: BlockNodeData }) {
  return (
    <div style={{
      padding: '8px 12px',
      background: T.surface3,
      border: `1px solid ${data.accent || T.border}`,
      borderLeft: `3px solid ${data.accent || T.cyan}`,
      fontSize: 11,
      fontFamily: F,
      color: T.text,
      fontWeight: 600,
      minWidth: 120,
      pointerEvents: 'none',
    }}>
      {data.label}
      <div style={{ fontSize: 9, color: T.dim, marginTop: 2, fontWeight: 400 }}>
        {data.type}
      </div>
    </div>
  )
}

const nodeTypes = { blockNode: PreviewNode }

export default function TemplatePreview({ templateId, onBack, onClose }: TemplatePreviewProps) {
  const [template, setTemplate] = useState<FullTemplate | null>(null)
  const [loading, setLoading] = useState(true)
  const [instantiating, setInstantiating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const loadPipeline = usePipelineStore((s) => s.loadPipeline)
  const setView = useUIStore((s) => s.setView)

  useEffect(() => {
    setLoading(true)
    api.get<FullTemplate>(`/templates/${templateId}`)
      .then((data) => {
        setTemplate(data)
        setError(null)
      })
      .catch((err) => setError(err.message || 'Failed to load template'))
      .finally(() => setLoading(false))
  }, [templateId])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const handleUseTemplate = useCallback(async () => {
    if (!template) return
    setInstantiating(true)
    try {
      const result = await api.post<{ pipeline_id: string; name: string }>(
        `/templates/${templateId}/instantiate`,
      )
      await loadPipeline(result.pipeline_id)
      setView('editor')
      toast.success(`Created pipeline: ${result.name}`)
      onClose()
    } catch (err: any) {
      toast.error(err.message || 'Failed to create pipeline')
    } finally {
      setInstantiating(false)
    }
  }, [template, templateId, loadPipeline, setView, onClose])

  const diffColor = template ? (DIFFICULTY_COLORS[template.difficulty] || T.dim) : T.dim
  const learnItems = template ? (WHAT_YOULL_LEARN[template.id] || []) : []

  // Fetch real prerequisite status from the backend
  interface PrereqItem { id: string; label: string; available: boolean; detail: string }
  interface PrereqResponse {
    services: Record<string, PrereqItem>
    capabilities: Record<string, PrereqItem>
  }
  const [prereqData, setPrereqData] = useState<PrereqResponse | null>(null)

  useEffect(() => {
    api.get<PrereqResponse>('/templates/prerequisites/check')
      .then(setPrereqData)
      .catch(() => {}) // fail silently — prereqs are informational
  }, [])

  const prereqs = useMemo(() => {
    if (!template || !prereqData) {
      // While loading, show items as unknown (dimmed)
      if (!template) return []
      return [
        ...template.required_services.map((svc) => ({
          label: svc, available: false, detail: 'Checking...',
        })),
        ...template.required_capabilities.map((cap) => ({
          label: cap, available: false, detail: 'Checking...',
        })),
      ]
    }
    const items: { label: string; available: boolean; detail: string }[] = []
    for (const svc of template.required_services) {
      const status = prereqData.services[svc]
      if (status) {
        items.push({ label: status.label, available: status.available, detail: status.detail })
      } else {
        items.push({ label: svc, available: false, detail: 'Not detected' })
      }
    }
    for (const cap of template.required_capabilities) {
      const status = prereqData.capabilities[cap]
      if (status) {
        items.push({ label: status.label, available: status.available, detail: status.detail })
      } else {
        items.push({ label: cap, available: false, detail: 'Not detected' })
      }
    }
    return items
  }, [template, prereqData])

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
          width: 900, height: '80vh', maxHeight: 700,
          background: T.surface1, border: `1px solid ${T.borderHi}`,
          boxShadow: `0 24px 64px ${T.shadowHeavy}`,
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '12px 16px', borderBottom: `1px solid ${T.border}`,
        }}>
          <button
            onClick={onBack}
            style={{
              background: 'none', border: 'none', color: T.dim,
              cursor: 'pointer', display: 'flex', padding: 4,
            }}
          >
            <ArrowLeft size={14} />
          </button>
          <span style={{
            fontFamily: F, fontSize: FS.lg, fontWeight: 700, color: T.text,
            letterSpacing: '0.04em', flex: 1,
          }}>
            {template?.name || 'Loading...'}
          </span>
          <button
            onClick={onClose}
            style={{
              background: 'none', border: 'none', color: T.dim,
              cursor: 'pointer', display: 'flex', padding: 4,
            }}
          >
            <X size={14} />
          </button>
        </div>

        {/* Body: two-panel layout */}
        {loading ? (
          <div style={{
            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Loader2 size={20} color={T.dim} style={{ animation: 'spin 1s linear infinite' }} />
          </div>
        ) : error ? (
          <div style={{
            flex: 1, display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', gap: 8,
          }}>
            <AlertCircle size={20} color={T.red} />
            <span style={{ fontFamily: F, fontSize: FS.sm, color: T.dim }}>{error}</span>
          </div>
        ) : template && (
          <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
            {/* Left panel: React Flow preview */}
            <div style={{
              flex: 1, borderRight: `1px solid ${T.border}`,
              background: T.bg, position: 'relative',
            }}>
              <ReactFlow
                nodes={template.nodes}
                edges={template.edges}
                nodeTypes={nodeTypes}
                fitView
                fitViewOptions={{ padding: 0.3 }}
                nodesDraggable={false}
                nodesConnectable={false}
                elementsSelectable={false}
                panOnDrag={false}
                zoomOnScroll={false}
                zoomOnDoubleClick={false}
                preventScrolling={false}
                proOptions={{ hideAttribution: true }}
              >
                <Background color={T.border} gap={20} size={1} />
              </ReactFlow>
              {/* Node count overlay */}
              <div style={{
                position: 'absolute', bottom: 10, left: 10,
                fontFamily: F, fontSize: FS.xxs, color: T.dim,
                background: `${T.surface1}cc`, padding: '3px 8px',
                letterSpacing: '0.08em',
              }}>
                {template.nodes.length} BLOCKS &middot; {template.edges.length} CONNECTIONS
              </div>
            </div>

            {/* Right panel: details */}
            <div style={{
              width: 320, padding: '16px 20px', overflowY: 'auto',
              display: 'flex', flexDirection: 'column', gap: 16,
            }}>
              {/* Name + difficulty */}
              <div>
                <h2 style={{
                  fontFamily: F, fontSize: 18, fontWeight: 700,
                  color: T.text, margin: '0 0 6px',
                }}>
                  {template.name}
                </h2>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{
                    fontFamily: F, fontSize: FS.xxs, fontWeight: 700,
                    letterSpacing: '0.1em', color: diffColor,
                    background: `${diffColor}15`, border: `1px solid ${diffColor}30`,
                    padding: '1px 6px', textTransform: 'uppercase',
                  }}>
                    {template.difficulty}
                  </span>
                  {template.estimated_runtime && (
                    <span style={{
                      display: 'inline-flex', alignItems: 'center', gap: 3,
                      fontFamily: F, fontSize: FS.xxs, color: T.dim,
                    }}>
                      <Clock size={8} />
                      {template.estimated_runtime}
                    </span>
                  )}
                </div>
              </div>

              {/* Description */}
              <div style={{
                fontFamily: F, fontSize: FS.sm, color: T.sec, lineHeight: 1.6,
              }}>
                {template.description}
              </div>

              {/* What you'll learn */}
              {learnItems.length > 0 && (
                <div>
                  <h3 style={{
                    fontFamily: F, fontSize: FS.xs, fontWeight: 700,
                    color: T.text, letterSpacing: '0.08em', margin: '0 0 8px',
                  }}>
                    WHAT YOU&apos;LL LEARN
                  </h3>
                  <ul style={{
                    margin: 0, padding: '0 0 0 16px',
                    fontFamily: F, fontSize: FS.xs, color: T.sec, lineHeight: 1.8,
                  }}>
                    {learnItems.map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Prerequisites */}
              {prereqs.length > 0 && (
                <div>
                  <h3 style={{
                    fontFamily: F, fontSize: FS.xs, fontWeight: 700,
                    color: T.text, letterSpacing: '0.08em', margin: '0 0 8px',
                  }}>
                    PREREQUISITES
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {prereqs.map((p, i) => (
                      <div key={i} style={{
                        display: 'flex', alignItems: 'flex-start', gap: 6,
                        fontFamily: F, fontSize: FS.xs,
                      }}>
                        {p.available ? (
                          <CheckCircle2 size={12} color="#34D399" style={{ flexShrink: 0, marginTop: 1 }} />
                        ) : (
                          <XCircle size={12} color="#F43F5E" style={{ flexShrink: 0, marginTop: 1 }} />
                        )}
                        <div>
                          <div style={{ color: T.sec }}>{p.label}</div>
                          <div style={{ fontSize: FS.xxs, color: T.dim, marginTop: 1 }}>
                            {p.detail}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Spacer */}
              <div style={{ flex: 1 }} />

              {/* CTA */}
              <motion.button
                onClick={handleUseTemplate}
                disabled={instantiating}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                style={{
                  width: '100%', padding: '10px 20px',
                  background: `${T.cyan}18`, border: `1px solid ${T.cyan}50`,
                  color: T.cyan, fontFamily: F, fontSize: FS.sm,
                  fontWeight: 700, letterSpacing: '0.1em',
                  cursor: instantiating ? 'wait' : 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                  opacity: instantiating ? 0.6 : 1,
                  transition: 'background 0.15s',
                }}
                onMouseEnter={(e) => {
                  if (!instantiating) e.currentTarget.style.background = `${T.cyan}30`
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = `${T.cyan}18`
                }}
              >
                {instantiating ? (
                  <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
                ) : (
                  <Play size={12} />
                )}
                USE THIS TEMPLATE
              </motion.button>
            </div>
          </div>
        )}
      </motion.div>
    </div>
  )
}
