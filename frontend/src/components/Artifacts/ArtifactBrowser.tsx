import { useState, useMemo } from 'react'
import { T, F, FCODE, FS } from '@/lib/design-tokens'
import { useOutputArtifacts } from '@/hooks/useOutputs'
import type { ArtifactItem } from '@/hooks/useOutputs'
import { FileText, Database, Brain, BarChart3, Box, Image, Activity, ChevronRight, ChevronDown, Loader2 } from 'lucide-react'
import ArtifactPreview from './ArtifactPreview'

const TYPE_ICON: Record<string, typeof FileText> = {
  text:       FileText,
  log:        FileText,
  dataset:    Database,
  data:       Database,
  model:      Brain,
  metrics:    BarChart3,
  adapter:    Box,
  figure:     Image,
  checkpoint: Activity,
}

const TYPE_COLOR: Record<string, string> = {
  text:       T.cyan,
  log:        T.dim,
  dataset:    T.purple,
  data:       T.purple,
  model:      T.orange,
  metrics:    T.green,
  adapter:    T.blue,
  figure:     T.pink,
  checkpoint: T.amber,
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(i > 1 ? 1 : 0)} ${sizes[i]}`
}

interface ArtifactBrowserProps {
  runId: string
}

interface ArtifactGroup {
  nodeId: string
  blockType: string
  artifacts: ArtifactItem[]
}

export default function ArtifactBrowser({ runId }: ArtifactBrowserProps) {
  const { data: artifacts, isLoading } = useOutputArtifacts({ runId, limit: 500 })
  const [expandedNode, setExpandedNode] = useState<string | null>(null)
  const [expandedArtifact, setExpandedArtifact] = useState<string | null>(null)

  // Group artifacts by node_id
  const groups = useMemo<ArtifactGroup[]>(() => {
    if (!artifacts?.length) return []
    const map = new Map<string, ArtifactGroup>()
    for (const a of artifacts) {
      let group = map.get(a.node_id)
      if (!group) {
        group = { nodeId: a.node_id, blockType: a.block_type, artifacts: [] }
        map.set(a.node_id, group)
      }
      group.artifacts.push(a)
    }
    return Array.from(map.values())
  }, [artifacts])

  if (isLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 16, color: T.dim }}>
        <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
        <span style={{ fontFamily: F, fontSize: FS.xs }}>Loading artifacts...</span>
      </div>
    )
  }

  if (!groups.length) {
    return (
      <div style={{ padding: 16, fontFamily: F, fontSize: FS.xs, color: T.dim }}>
        No artifacts for this run.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      {groups.map((group) => {
        const isExpanded = expandedNode === group.nodeId
        return (
          <div key={group.nodeId}>
            {/* Node group header */}
            <div
              onClick={() => setExpandedNode(isExpanded ? null : group.nodeId)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '8px 12px',
                cursor: 'pointer',
                background: isExpanded ? T.surface1 : 'transparent',
                borderBottom: `1px solid ${T.border}`,
                transition: 'background 0.1s',
              }}
              onMouseEnter={(e) => {
                if (!isExpanded) e.currentTarget.style.background = `${T.surface1}`
              }}
              onMouseLeave={(e) => {
                if (!isExpanded) e.currentTarget.style.background = 'transparent'
              }}
            >
              {isExpanded
                ? <ChevronDown size={11} color={T.dim} />
                : <ChevronRight size={11} color={T.dim} />
              }

              <span style={{
                fontFamily: F,
                fontSize: FS.sm,
                fontWeight: 600,
                color: T.text,
                flex: 1,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {group.blockType}
              </span>

              <span style={{
                fontFamily: F,
                fontSize: FS.xxs,
                color: T.dim,
                padding: '1px 6px',
                background: T.surface3,
              }}>
                {group.artifacts.length} artifact{group.artifacts.length !== 1 ? 's' : ''}
              </span>
            </div>

            {/* Artifacts list */}
            {isExpanded && (
              <div style={{ background: T.surface0, borderBottom: `1px solid ${T.border}` }}>
                {group.artifacts.map((artifact) => {
                  const Icon = TYPE_ICON[artifact.artifact_type] || FileText
                  const color = TYPE_COLOR[artifact.artifact_type] || T.dim
                  const isArtExpanded = expandedArtifact === artifact.id

                  return (
                    <div key={artifact.id}>
                      <div
                        onClick={() => setExpandedArtifact(isArtExpanded ? null : artifact.id)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 10,
                          padding: '6px 12px 6px 28px',
                          cursor: 'pointer',
                          transition: 'background 0.1s',
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = `${T.surface2}` }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
                      >
                        <Icon size={12} color={color} strokeWidth={1.5} style={{ flexShrink: 0 }} />

                        <span style={{
                          fontFamily: F,
                          fontSize: FS.xs,
                          color: T.text,
                          flex: 1,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}>
                          {artifact.name}
                        </span>

                        {/* Data type badge */}
                        <span style={{
                          fontFamily: F,
                          fontSize: FS.xxs,
                          color,
                          padding: '1px 6px',
                          background: `${color}14`,
                          border: `1px solid ${color}22`,
                          flexShrink: 0,
                          letterSpacing: '0.04em',
                          textTransform: 'uppercase',
                        }}>
                          {artifact.artifact_type}
                        </span>

                        {/* Size */}
                        <span style={{
                          fontFamily: F,
                          fontSize: FS.xxs,
                          color: T.dim,
                          flexShrink: 0,
                        }}>
                          {formatBytes(artifact.size_bytes)}
                        </span>

                        {/* Truncated hash */}
                        {artifact.hash && (
                          <span
                            title={artifact.hash}
                            style={{
                              fontFamily: FCODE,
                              fontSize: FS.xxs,
                              color: T.muted,
                              flexShrink: 0,
                              opacity: 0.7,
                            }}
                          >
                            {artifact.hash.slice(0, 8)}
                          </span>
                        )}
                      </div>

                      {/* Expanded preview */}
                      {isArtExpanded && (
                        <div style={{ padding: '4px 12px 8px 40px' }}>
                          <ArtifactPreview artifact={artifact} />
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
