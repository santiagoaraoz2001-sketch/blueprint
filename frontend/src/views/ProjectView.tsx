import { useEffect, useState, useMemo, useCallback } from 'react'
import { T, F, FS, BRAND_TEAL } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { useProjectStore } from '@/stores/projectStore'
import { usePipelineStore } from '@/stores/pipelineStore'
import { api } from '@/api/client'
import toast from 'react-hot-toast'
import {
  GitCompare, Plus, Copy, ChevronDown, ArrowUpDown,
  Star, Tag, StickyNote, CheckCircle2, XCircle, Clock, Loader2,
} from 'lucide-react'

interface PipelineCard {
  id: string
  name: string
  description?: string
  source_pipeline_id?: string | null
  variant_notes?: string | null
  config_diff?: any
  notes?: string | null
  created_at?: string
  updated_at?: string
  run_count: number
  latest_run_status?: string | null
  runs?: any[]
}

const STATUS_DOT: Record<string, { color: string; label: string }> = {
  complete: { color: T.green, label: 'Complete' },
  failed: { color: T.red, label: 'Failed' },
  running: { color: T.amber, label: 'Running' },
  pending: { color: T.dim, label: 'Pending' },
  cancelled: { color: T.dim, label: 'Cancelled' },
}

const TAG_COLORS = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD']

function hashString(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash) + str.charCodeAt(i)
    hash |= 0
  }
  return Math.abs(hash)
}

export default function ProjectView() {
  const selectedProjectId = useUIStore((s) => s.selectedProjectId)
  const setView = useUIStore((s) => s.setView)
  const setSelectedPipeline = useUIStore((s) => s.setSelectedPipeline)
  const fetchProject = useProjectStore((s) => s.fetchProject)
  const updateProject = useProjectStore((s) => s.updateProject)
  const loadPipeline = usePipelineStore((s) => s.loadPipeline)

  const [project, setProject] = useState<any>(null)
  const [pipelines, setPipelines] = useState<PipelineCard[]>([])
  const [loading, setLoading] = useState(true)
  const [sortBy, setSortBy] = useState<'date' | 'name' | 'status'>('date')
  const [editingName, setEditingName] = useState(false)
  const [editingHypothesis, setEditingHypothesis] = useState(false)
  const [nameText, setNameText] = useState('')
  const [hypothesisText, setHypothesisText] = useState('')
  const [showCloneDialog, setShowCloneDialog] = useState(false)
  const [cloneSourceId, setCloneSourceId] = useState<string | null>(null)
  const [cloneName, setCloneName] = useState('')
  const [cloneNotes, setCloneNotes] = useState('')

  useEffect(() => {
    if (!selectedProjectId) return
    setLoading(true)
    api.get<any>(`/projects/${selectedProjectId}`)
      .then((data) => {
        setProject(data)
        setPipelines(data.pipelines || [])
        setNameText(data.name)
        setHypothesisText(data.hypothesis || '')
        setLoading(false)
      })
      .catch(() => {
        toast.error('Failed to load project')
        setLoading(false)
      })
  }, [selectedProjectId])

  const sortedPipelines = useMemo(() => {
    const sorted = [...pipelines]
    switch (sortBy) {
      case 'name':
        sorted.sort((a, b) => a.name.localeCompare(b.name))
        break
      case 'status': {
        const statusOrder: Record<string, number> = { running: 0, failed: 1, complete: 2, pending: 3 }
        sorted.sort((a, b) =>
          (statusOrder[a.latest_run_status || 'pending'] ?? 4) -
          (statusOrder[b.latest_run_status || 'pending'] ?? 4)
        )
        break
      }
      default: // date
        sorted.sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''))
    }
    return sorted
  }, [pipelines, sortBy])

  const handleSaveName = useCallback(async () => {
    if (!selectedProjectId || !nameText.trim()) return
    await updateProject(selectedProjectId, { name: nameText.trim() })
    setProject((p: any) => ({ ...p, name: nameText.trim() }))
    setEditingName(false)
    toast.success('Project name updated')
  }, [selectedProjectId, nameText, updateProject])

  const handleSaveHypothesis = useCallback(async () => {
    if (!selectedProjectId) return
    await updateProject(selectedProjectId, { hypothesis: hypothesisText })
    setProject((p: any) => ({ ...p, hypothesis: hypothesisText }))
    setEditingHypothesis(false)
    toast.success('Hypothesis updated')
  }, [selectedProjectId, hypothesisText, updateProject])

  const handleNewExperiment = useCallback(async () => {
    if (!selectedProjectId) return
    try {
      const pipeline = await api.post<any>('/pipelines', {
        name: `Experiment ${pipelines.length + 1}`,
        project_id: selectedProjectId,
      })
      setPipelines((prev) => [pipeline, ...prev])
      toast.success('New experiment created')
    } catch {
      toast.error('Failed to create experiment')
    }
  }, [selectedProjectId, pipelines.length])

  const handleCloneVariant = useCallback(async () => {
    if (!cloneSourceId) return
    try {
      const result = await api.post<any>(`/pipelines/${cloneSourceId}/clone-variant`, {
        name: cloneName || undefined,
        project_id: selectedProjectId,
        variant_notes: cloneNotes || undefined,
      })
      setPipelines((prev) => [result.pipeline, ...prev])
      setShowCloneDialog(false)
      setCloneName('')
      setCloneNotes('')
      toast.success(`Cloned as variant (${result.inherited_config_count} configs inherited)`)
    } catch {
      toast.error('Failed to clone variant')
    }
  }, [cloneSourceId, cloneName, cloneNotes, selectedProjectId])

  const handleOpenPipeline = useCallback((pipelineId: string) => {
    setSelectedPipeline(pipelineId)
    loadPipeline(pipelineId)
    setView('editor')
  }, [setSelectedPipeline, loadPipeline, setView])

  if (!selectedProjectId) {
    return (
      <div style={{ height: '100%', display: 'grid', placeItems: 'center', color: T.dim, fontFamily: F }}>
        No project selected. Go to Projects to select one.
      </div>
    )
  }

  if (loading) {
    return (
      <div style={{ height: '100%', display: 'grid', placeItems: 'center' }}>
        <Loader2 size={24} color={T.dim} style={{ animation: 'spin 1s linear infinite' }} />
      </div>
    )
  }

  const statusBadgeColor: Record<string, string> = {
    active: BRAND_TEAL,
    completed: T.green,
    archived: T.dim,
    planned: T.amber,
  }

  return (
    <div style={{ height: '100%', overflow: 'auto', padding: '32px 48px', scrollbarWidth: 'thin' }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        {/* Project name (editable) */}
        {editingName ? (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
            <input
              autoFocus
              value={nameText}
              onChange={(e) => setNameText(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleSaveName(); if (e.key === 'Escape') setEditingName(false) }}
              style={{
                fontFamily: F,
                fontSize: 28,
                fontWeight: 800,
                color: T.text,
                background: T.surface3,
                border: `1px solid ${BRAND_TEAL}40`,
                borderRadius: 6,
                padding: '4px 12px',
                outline: 'none',
                flex: 1,
              }}
            />
            <button onClick={handleSaveName} style={{ padding: '4px 12px', background: `${BRAND_TEAL}20`, border: `1px solid ${BRAND_TEAL}40`, borderRadius: 6, color: BRAND_TEAL, fontFamily: F, fontSize: FS.xs, fontWeight: 700, cursor: 'pointer' }}>
              Save
            </button>
          </div>
        ) : (
          <h1
            onClick={() => setEditingName(true)}
            style={{
              fontFamily: F,
              fontSize: 28,
              fontWeight: 800,
              color: T.text,
              letterSpacing: '-0.02em',
              margin: 0,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 12,
            }}
          >
            {project?.name}
            {project?.status && (
              <span style={{
                fontFamily: F,
                fontSize: FS.xxs,
                fontWeight: 700,
                color: statusBadgeColor[project.status] || T.dim,
                background: `${statusBadgeColor[project.status] || T.dim}15`,
                border: `1px solid ${statusBadgeColor[project.status] || T.dim}30`,
                borderRadius: 4,
                padding: '2px 8px',
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
              }}>
                {project.status}
              </span>
            )}
          </h1>
        )}

        {/* Hypothesis (editable, italic) */}
        {editingHypothesis ? (
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginTop: 8 }}>
            <textarea
              autoFocus
              value={hypothesisText}
              onChange={(e) => setHypothesisText(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && e.metaKey) handleSaveHypothesis(); if (e.key === 'Escape') setEditingHypothesis(false) }}
              placeholder="What is the research question?"
              style={{
                fontFamily: F,
                fontSize: FS.md,
                fontStyle: 'italic',
                color: T.sec,
                background: T.surface3,
                border: `1px solid ${T.border}`,
                borderRadius: 6,
                padding: '6px 12px',
                outline: 'none',
                flex: 1,
                minHeight: 60,
                resize: 'vertical',
              }}
            />
            <button onClick={handleSaveHypothesis} style={{ padding: '4px 12px', background: `${BRAND_TEAL}20`, border: `1px solid ${BRAND_TEAL}40`, borderRadius: 6, color: BRAND_TEAL, fontFamily: F, fontSize: FS.xs, fontWeight: 700, cursor: 'pointer' }}>
              Save
            </button>
          </div>
        ) : (
          <p
            onClick={() => setEditingHypothesis(true)}
            style={{
              fontFamily: F,
              fontSize: FS.md,
              color: project?.hypothesis ? T.sec : T.dim,
              fontStyle: 'italic',
              margin: '8px 0 0',
              cursor: 'pointer',
              lineHeight: 1.6,
            }}
          >
            {project?.hypothesis || 'Click to add research hypothesis...'}
          </p>
        )}
      </div>

      {/* Actions bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
        <button
          onClick={handleNewExperiment}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '8px 16px',
            background: `${BRAND_TEAL}15`,
            border: `1px solid ${BRAND_TEAL}30`,
            borderRadius: 8,
            color: BRAND_TEAL,
            fontFamily: F,
            fontSize: FS.sm,
            fontWeight: 700,
            cursor: 'pointer',
          }}
        >
          <Plus size={14} />
          New Experiment
        </button>

        <button
          onClick={() => {
            if (pipelines.length === 0) {
              toast.error('No pipelines to clone from')
              return
            }
            setCloneSourceId(pipelines[0].id)
            setShowCloneDialog(true)
          }}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '8px 16px',
            background: T.surface2,
            border: `1px solid ${T.border}`,
            borderRadius: 8,
            color: T.sec,
            fontFamily: F,
            fontSize: FS.sm,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          <Copy size={14} />
          Clone Existing
        </button>

        <div style={{ flex: 1 }} />

        {/* Sort control */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <ArrowUpDown size={12} color={T.dim} />
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            style={{
              background: T.surface3,
              border: `1px solid ${T.border}`,
              borderRadius: 4,
              color: T.sec,
              fontFamily: F,
              fontSize: FS.xs,
              padding: '4px 8px',
              outline: 'none',
            }}
          >
            <option value="date">Date</option>
            <option value="name">Name</option>
            <option value="status">Status</option>
          </select>
        </div>
      </div>

      {/* Pipeline cards */}
      <div style={{ display: 'grid', gap: 12 }}>
        {sortedPipelines.length === 0 && (
          <div style={{
            padding: 40,
            textAlign: 'center',
            color: T.dim,
            fontFamily: F,
            fontSize: FS.sm,
          }}>
            No experiments yet. Create a new one or clone from an existing pipeline.
          </div>
        )}

        {sortedPipelines.map((pipe) => {
          const statusInfo = STATUS_DOT[pipe.latest_run_status || ''] || STATUS_DOT.pending
          const diffCount = pipe.config_diff?.changed_keys
            ? Object.values(pipe.config_diff.changed_keys).reduce(
                (acc: number, keys: any) => acc + (typeof keys === 'object' ? Object.keys(keys).length : 0), 0
              )
            : 0

          return (
            <div
              key={pipe.id}
              onClick={() => handleOpenPipeline(pipe.id)}
              style={{
                padding: '16px 20px',
                background: `linear-gradient(135deg, ${T.surface2} 0%, ${T.surface1} 100%)`,
                border: `1px solid ${T.border}`,
                borderRadius: 10,
                cursor: 'pointer',
                transition: 'all 0.15s',
                display: 'flex',
                alignItems: 'center',
                gap: 16,
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = `${BRAND_TEAL}40`
                e.currentTarget.style.boxShadow = `0 4px 16px ${T.shadow}`
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = T.border
                e.currentTarget.style.boxShadow = 'none'
              }}
            >
              {/* Status dot */}
              <div style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: statusInfo.color,
                boxShadow: pipe.latest_run_status === 'running' ? `0 0 8px ${statusInfo.color}` : 'none',
                flexShrink: 0,
              }} />

              {/* Main info */}
              <div style={{ flex: 1, overflow: 'hidden' }}>
                <div style={{
                  fontFamily: F,
                  fontSize: FS.md,
                  color: T.text,
                  fontWeight: 700,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}>
                  {pipe.name}
                </div>
                {pipe.variant_notes && (
                  <div style={{
                    fontFamily: F,
                    fontSize: FS.xxs,
                    color: T.sec,
                    fontStyle: 'italic',
                    marginTop: 4,
                    lineHeight: 1.4,
                  }}>
                    {pipe.variant_notes}
                  </div>
                )}
              </div>

              {/* Run count */}
              <div style={{
                fontFamily: F,
                fontSize: FS.xs,
                color: T.dim,
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                whiteSpace: 'nowrap',
              }}>
                {pipe.run_count} run{pipe.run_count !== 1 ? 's' : ''}
              </div>

              {/* Config diff badge */}
              {diffCount > 0 && pipe.config_diff?.source_pipeline_name && (
                <div
                  onClick={(e) => e.stopPropagation()}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                    padding: '3px 8px',
                    background: `${BRAND_TEAL}12`,
                    border: `1px solid ${BRAND_TEAL}25`,
                    borderRadius: 4,
                    fontFamily: F,
                    fontSize: FS.xxs,
                    color: BRAND_TEAL,
                    fontWeight: 600,
                    whiteSpace: 'nowrap',
                  }}
                >
                  <GitCompare size={9} />
                  {diffCount} change{diffCount !== 1 ? 's' : ''} from {pipe.config_diff.source_pipeline_name}
                </div>
              )}

              {/* Clone button */}
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  setCloneSourceId(pipe.id)
                  setCloneName(`${pipe.name} (variant)`)
                  setShowCloneDialog(true)
                }}
                title="Clone as variant"
                style={{
                  background: 'none',
                  border: `1px solid ${T.border}`,
                  borderRadius: 4,
                  color: T.dim,
                  cursor: 'pointer',
                  padding: '4px 6px',
                  display: 'flex',
                  transition: 'color 0.15s',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.color = BRAND_TEAL }}
                onMouseLeave={(e) => { e.currentTarget.style.color = T.dim }}
              >
                <Copy size={12} />
              </button>
            </div>
          )
        })}
      </div>

      {/* Clone as variant dialog */}
      {showCloneDialog && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.6)',
            display: 'grid',
            placeItems: 'center',
            zIndex: 1000,
          }}
          onClick={() => setShowCloneDialog(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: 420,
              background: T.surface1,
              border: `1px solid ${T.border}`,
              borderRadius: 12,
              padding: 24,
              boxShadow: `0 16px 48px ${T.shadowHeavy}`,
            }}
          >
            <h3 style={{
              fontFamily: F,
              fontSize: FS.lg,
              color: T.text,
              fontWeight: 700,
              margin: '0 0 16px',
            }}>
              Clone as Variant
            </h3>

            <div style={{ marginBottom: 16 }}>
              <label style={{ fontFamily: F, fontSize: FS.xs, color: T.sec, fontWeight: 600, display: 'block', marginBottom: 6 }}>
                Variant Name
              </label>
              <input
                value={cloneName}
                onChange={(e) => setCloneName(e.target.value)}
                placeholder="e.g. BALLAST lr=1e-4"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  background: T.surface3,
                  border: `1px solid ${T.border}`,
                  borderRadius: 6,
                  color: T.text,
                  fontFamily: F,
                  fontSize: FS.sm,
                  outline: 'none',
                }}
              />
            </div>

            {pipelines.length > 1 && (
              <div style={{ marginBottom: 16 }}>
                <label style={{ fontFamily: F, fontSize: FS.xs, color: T.sec, fontWeight: 600, display: 'block', marginBottom: 6 }}>
                  Clone From
                </label>
                <select
                  value={cloneSourceId || ''}
                  onChange={(e) => setCloneSourceId(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    background: T.surface3,
                    border: `1px solid ${T.border}`,
                    borderRadius: 6,
                    color: T.text,
                    fontFamily: F,
                    fontSize: FS.sm,
                    outline: 'none',
                  }}
                >
                  {pipelines.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>
            )}

            <div style={{ marginBottom: 20 }}>
              <label style={{ fontFamily: F, fontSize: FS.xs, color: T.sec, fontWeight: 600, display: 'block', marginBottom: 6 }}>
                What's different in this experiment?
              </label>
              <textarea
                value={cloneNotes}
                onChange={(e) => setCloneNotes(e.target.value)}
                placeholder="e.g. Testing lower learning rate to reduce divergence"
                style={{
                  width: '100%',
                  minHeight: 80,
                  padding: '8px 12px',
                  background: T.surface3,
                  border: `1px solid ${T.border}`,
                  borderRadius: 6,
                  color: T.text,
                  fontFamily: F,
                  fontSize: FS.sm,
                  outline: 'none',
                  resize: 'vertical',
                }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button
                onClick={() => setShowCloneDialog(false)}
                style={{
                  padding: '8px 16px',
                  background: 'none',
                  border: `1px solid ${T.border}`,
                  borderRadius: 6,
                  color: T.dim,
                  fontFamily: F,
                  fontSize: FS.sm,
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleCloneVariant}
                style={{
                  padding: '8px 16px',
                  background: `${BRAND_TEAL}20`,
                  border: `1px solid ${BRAND_TEAL}40`,
                  borderRadius: 6,
                  color: BRAND_TEAL,
                  fontFamily: F,
                  fontSize: FS.sm,
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                Clone Variant
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
