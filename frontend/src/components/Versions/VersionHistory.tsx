import { useState, useEffect, useCallback, useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { api } from '@/api/client'
import { usePipelineStore, type BlockNodeData } from '@/stores/pipelineStore'
import { History, RotateCcw, Eye, EyeOff, Clock, User, ChevronDown, ChevronUp, GitBranch } from 'lucide-react'
import { type Node, type Edge, ReactFlow, Background, BackgroundVariant } from '@xyflow/react'
import toast from 'react-hot-toast'

interface VersionSummary {
  id: string
  pipeline_id: string
  version_number: number
  author: string
  message: string | null
  created_at: string
}

interface VersionFull extends VersionSummary {
  snapshot: string
}

interface DiffResult {
  added: Set<string>
  removed: Set<string>
  modified: Set<string>
}

function computeNodeDiff(
  currentNodes: Node<BlockNodeData>[],
  snapshotNodes: Node<BlockNodeData>[],
): DiffResult {
  const currentIds = new Set(currentNodes.map((n) => n.id))
  const snapshotIds = new Set(snapshotNodes.map((n) => n.id))

  const added = new Set<string>()
  const removed = new Set<string>()
  const modified = new Set<string>()

  // Nodes in snapshot but not in current = they were removed since that version
  for (const id of snapshotIds) {
    if (!currentIds.has(id)) removed.add(id)
  }

  // Nodes in current but not in snapshot = they were added since that version
  for (const id of currentIds) {
    if (!snapshotIds.has(id)) added.add(id)
  }

  // Nodes in both: check if config or position changed
  const snapshotMap = new Map(snapshotNodes.map((n) => [n.id, n]))
  for (const node of currentNodes) {
    if (snapshotIds.has(node.id)) {
      const snap = snapshotMap.get(node.id)
      if (snap && JSON.stringify(node.data?.config) !== JSON.stringify(snap.data?.config)) {
        modified.add(node.id)
      }
    }
  }

  return { added, removed, modified }
}

export default function VersionHistory() {
  const pipelineId = usePipelineStore((s) => s.id)
  const currentNodes = usePipelineStore((s) => s.nodes)
  const [versions, setVersions] = useState<VersionSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [previewVersionId, setPreviewVersionId] = useState<number | null>(null)
  const [previewSnapshot, setPreviewSnapshot] = useState<{ nodes: Node[]; edges: Edge[] } | null>(null)
  const [previewDiff, setPreviewDiff] = useState<DiffResult | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const fetchVersions = useCallback(async () => {
    if (!pipelineId) return
    setLoading(true)
    try {
      const list = await api.get<VersionSummary[]>(`/pipelines/${pipelineId}/versions`)
      setVersions(list || [])
    } catch {
      // Silent fail
    } finally {
      setLoading(false)
    }
  }, [pipelineId])

  useEffect(() => {
    fetchVersions()
  }, [fetchVersions])

  const handlePreview = useCallback(async (versionNumber: number) => {
    if (!pipelineId) return
    if (previewVersionId === versionNumber) {
      setPreviewVersionId(null)
      setPreviewSnapshot(null)
      setPreviewDiff(null)
      return
    }
    try {
      const full = await api.get<VersionFull>(`/pipelines/${pipelineId}/versions/${versionNumber}`)
      const parsed = JSON.parse(full.snapshot)
      const nodes = parsed.nodes || []
      const edges = parsed.edges || []
      setPreviewSnapshot({ nodes, edges })
      setPreviewVersionId(versionNumber)
      setPreviewDiff(computeNodeDiff(currentNodes, nodes))
    } catch {
      toast.error('Failed to load version preview')
    }
  }, [pipelineId, previewVersionId, currentNodes])

  const handleRestore = useCallback(async (versionNumber: number) => {
    if (!pipelineId) return
    try {
      await api.post(`/pipelines/${pipelineId}/versions/${versionNumber}/restore`)
      // Reload the pipeline to reflect the restored state
      await usePipelineStore.getState().loadPipeline(pipelineId)
      fetchVersions()
      setPreviewVersionId(null)
      setPreviewSnapshot(null)
      setPreviewDiff(null)
      toast.success(`Restored to version ${versionNumber}`)
    } catch {
      toast.error('Failed to restore version')
    }
  }, [pipelineId, fetchVersions])

  const t = T()

  if (!pipelineId) {
    return (
      <div style={{ padding: 24, color: t.dim, textAlign: 'center' }}>
        <History size={32} style={{ marginBottom: 8, opacity: 0.5 }} />
        <p style={{ ...F.sm }}>Save a pipeline to see version history</p>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px',
        borderBottom: `1px solid ${t.border}`,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <GitBranch size={16} style={{ color: t.cyan }} />
        <span style={{ ...F.sm, fontWeight: 600, color: t.text }}>Version History</span>
        <span style={{
          ...F.xs, color: t.dim, marginLeft: 'auto',
          background: t.surface3, borderRadius: 8, padding: '2px 8px',
        }}>
          {versions.length}
        </span>
      </div>

      {/* Version list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
        {loading && (
          <div style={{ padding: 24, textAlign: 'center', color: t.dim, ...F.sm }}>
            Loading versions...
          </div>
        )}
        {!loading && versions.length === 0 && (
          <div style={{ padding: 24, textAlign: 'center', color: t.dim, ...F.sm }}>
            No versions yet. Save (Cmd+S) to create the first version.
          </div>
        )}
        {versions.map((v) => {
          const isPreview = previewVersionId === v.version_number
          const isExpanded = expandedId === v.version_number
          return (
            <div
              key={v.id}
              style={{
                margin: '0 8px 4px',
                borderRadius: 8,
                border: `1px solid ${isPreview ? t.cyan : t.border}`,
                background: isPreview ? `${t.cyan}11` : t.surface,
                overflow: 'hidden',
                transition: 'all 0.15s ease',
              }}
            >
              {/* Version header */}
              <div
                style={{
                  padding: '10px 12px',
                  display: 'flex', alignItems: 'center', gap: 8,
                  cursor: 'pointer',
                }}
                onClick={() => setExpandedId(isExpanded ? null : v.version_number)}
              >
                <div style={{
                  width: 28, height: 28, borderRadius: '50%',
                  background: t.surface3, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  ...F.xs, fontWeight: 700, color: t.cyan, flexShrink: 0,
                }}>
                  v{v.version_number}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ ...F.xs, color: t.text, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {v.message || 'Auto-save'}
                  </div>
                  <div style={{ ...F.xs, color: t.dim, display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
                    <Clock size={10} />
                    {new Date(v.created_at).toLocaleString()}
                    <User size={10} style={{ marginLeft: 4 }} />
                    {v.author}
                  </div>
                </div>
                {isExpanded ? <ChevronUp size={14} style={{ color: t.dim }} /> : <ChevronDown size={14} style={{ color: t.dim }} />}
              </div>

              {/* Expanded actions */}
              {isExpanded && (
                <div style={{ padding: '0 12px 10px', display: 'flex', gap: 6 }}>
                  <button
                    onClick={() => handlePreview(v.version_number)}
                    style={{
                      ...F.xs,
                      padding: '5px 10px', borderRadius: 6,
                      border: `1px solid ${t.border}`,
                      background: isPreview ? t.cyan : t.surface3,
                      color: isPreview ? t.bg : t.text,
                      cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4,
                      fontWeight: 500,
                    }}
                  >
                    {isPreview ? <EyeOff size={12} /> : <Eye size={12} />}
                    {isPreview ? 'Close Preview' : 'Preview'}
                  </button>
                  <button
                    onClick={() => handleRestore(v.version_number)}
                    style={{
                      ...F.xs,
                      padding: '5px 10px', borderRadius: 6,
                      border: `1px solid ${t.border}`,
                      background: t.surface3,
                      color: t.text,
                      cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4,
                      fontWeight: 500,
                    }}
                  >
                    <RotateCcw size={12} />
                    Restore
                  </button>
                </div>
              )}

              {/* Visual diff indicators */}
              {isPreview && previewDiff && (
                <div style={{ padding: '0 12px 10px', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {previewDiff.added.size > 0 && (
                    <span style={{ ...F.xs, color: t.green, display: 'flex', alignItems: 'center', gap: 3 }}>
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: t.green, display: 'inline-block' }} />
                      {previewDiff.added.size} added
                    </span>
                  )}
                  {previewDiff.removed.size > 0 && (
                    <span style={{ ...F.xs, color: t.red, display: 'flex', alignItems: 'center', gap: 3 }}>
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: t.red, display: 'inline-block' }} />
                      {previewDiff.removed.size} removed
                    </span>
                  )}
                  {previewDiff.modified.size > 0 && (
                    <span style={{ ...F.xs, color: t.amber, display: 'flex', alignItems: 'center', gap: 3 }}>
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: t.amber, display: 'inline-block' }} />
                      {previewDiff.modified.size} modified
                    </span>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Preview pane: read-only React Flow rendering */}
      {previewSnapshot && (
        <div style={{
          height: 260,
          borderTop: `1px solid ${t.border}`,
          background: t.bgAlt,
          position: 'relative',
        }}>
          <div style={{
            position: 'absolute', top: 8, left: 12, zIndex: 10,
            ...F.xs, color: t.dim, background: `${t.bg}cc`, padding: '2px 8px', borderRadius: 6,
          }}>
            Preview — v{previewVersionId} (read-only)
          </div>
          <ReactFlow
            nodes={previewSnapshot.nodes.map((n) => {
              const diff = previewDiff
              let borderColor = 'transparent'
              let borderStyle = 'solid'
              if (diff) {
                if (diff.removed.has(n.id)) { borderColor = T().red; borderStyle = 'dashed' }
                else if (diff.added.has(n.id)) { borderColor = T().green; borderStyle = 'solid' }
                else if (diff.modified.has(n.id)) { borderColor = T().amber; borderStyle = 'solid' }
              }
              return {
                ...n,
                style: {
                  ...(n.style || {}),
                  border: borderColor !== 'transparent' ? `2px ${borderStyle} ${borderColor}` : undefined,
                  borderRadius: 8,
                },
              }
            })}
            edges={previewSnapshot.edges}
            fitView
            panOnDrag
            zoomOnScroll={false}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color={`${t.dim}33`} />
          </ReactFlow>
        </div>
      )}
    </div>
  )
}
