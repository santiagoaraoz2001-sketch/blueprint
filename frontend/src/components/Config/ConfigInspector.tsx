import { useState, useEffect, useMemo } from 'react'
import { T, F, FS, FCODE, DEPTH, GLOW } from '@/lib/design-tokens'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useRunStore } from '@/stores/runStore'
import { api } from '@/api/client'
import { X, Copy, Check, CheckCircle, XCircle, Info, ChevronDown, ChevronRight } from 'lucide-react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PlanNode {
  node_id: string
  label: string
  block_type: string
  block_version: string
  resolved_config: Record<string, any>
  config_sources: Record<string, string>
  cache_fingerprint: string
  cache_eligible: boolean
  in_loop: boolean
  loop_id: string | null
}

interface PlanResponse {
  is_valid: boolean
  errors: string[]
  plan_hash: string | null
  nodes: Record<string, PlanNode>
  execution_order: string[]
  warnings: string[]
}

interface Props {
  nodeId: string
  onClose: () => void
}

// ---------------------------------------------------------------------------
// Source badge colors
// ---------------------------------------------------------------------------

function sourceBadgeStyle(source: string): { bg: string; fg: string; label: string } {
  if (source === 'workspace') return { bg: `${T.cyan}22`, fg: T.cyan, label: 'workspace' }
  if (source.startsWith('inherited:')) return { bg: `${T.green}22`, fg: T.green, label: source }
  if (source === 'block_default') return { bg: `${T.sec}18`, fg: T.sec, label: 'default' }
  if (source === 'user') return { bg: `${T.amber}22`, fg: T.amber, label: 'user' }
  if (source === 'workspace_auto_fill') return { bg: `${T.cyan}18`, fg: T.cyan, label: 'workspace (auto)' }
  return { bg: `${T.dim}18`, fg: T.dim, label: source }
}

function getOriginNodeName(source: string, nodeMap: Record<string, any>): string | null {
  if (!source.startsWith('inherited:')) return null
  const originId = source.replace('inherited:', '')
  const node = nodeMap[originId]
  return node?.data?.label || originId
}

// ---------------------------------------------------------------------------
// ConfigInspector Component
// ---------------------------------------------------------------------------

export default function ConfigInspector({ nodeId, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<'config' | 'cache'>('config')
  const [plan, setPlan] = useState<PlanResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showEffective, setShowEffective] = useState(false)
  const [copiedFp, setCopiedFp] = useState(false)

  const pipelineId = usePipelineStore((s) => s.tabs[s.activeTabIndex]?.id)
  const nodes = usePipelineStore((s) => s.nodes)
  const edges = usePipelineStore((s) => s.edges)
  const activeRunId = useRunStore((s) => s.activeRunId)

  const nodeMap = useMemo(() => {
    const m: Record<string, any> = {}
    for (const n of nodes) m[n.id] = n
    return m
  }, [nodes])

  const currentNode = nodeMap[nodeId]
  const nodeLabel = currentNode?.data?.label || nodeId

  // Fetch the plan
  useEffect(() => {
    if (!pipelineId) {
      setError('No active pipeline')
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    api
      .get<PlanResponse>(`/pipelines/${pipelineId}/plan`)
      .then((data) => {
        setPlan(data)
        setLoading(false)
      })
      .catch((err) => {
        setError(err?.message || 'Failed to load plan')
        setLoading(false)
      })
  }, [pipelineId])

  const planNode = plan?.nodes?.[nodeId] || null

  // Compute upstream dependency chain for cache tab
  const upstreamChain = useMemo(() => {
    if (!plan) return []
    const incoming: Record<string, Set<string>> = {}
    for (const e of edges) {
      const tgt = (e as any).target || (e as any).id?.split('-')[1]
      const src = (e as any).source || (e as any).id?.split('-')[0]
      if (tgt && src) {
        if (!incoming[tgt]) incoming[tgt] = new Set()
        incoming[tgt].add(src)
      }
    }
    const parents = incoming[nodeId] || new Set<string>()
    return Array.from(parents)
      .filter((id) => plan.nodes[id])
      .map((id) => ({
        id,
        label: plan.nodes[id].label,
        fingerprint: plan.nodes[id].cache_fingerprint,
      }))
  }, [plan, nodeId, edges])

  // Copy fingerprint to clipboard
  const copyFingerprint = (fp: string) => {
    navigator.clipboard.writeText(fp).then(() => {
      setCopiedFp(true)
      setTimeout(() => setCopiedFp(false), 1500)
    })
  }

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        right: 0,
        width: 420,
        height: '100vh',
        background: T.surface,
        borderLeft: `1px solid ${T.border}`,
        boxShadow: DEPTH.float,
        zIndex: 1000,
        display: 'flex',
        flexDirection: 'column',
        fontFamily: F,
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '12px 16px',
          borderBottom: `1px solid ${T.border}`,
          gap: 8,
        }}
      >
        <Info size={14} color={T.cyan} />
        <span style={{ flex: 1, fontSize: FS.sm, fontWeight: 600, color: T.text }}>
          Inspect: {nodeLabel}
        </span>
        <button
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            color: T.dim,
            cursor: 'pointer',
            padding: 4,
          }}
        >
          <X size={14} />
        </button>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', borderBottom: `1px solid ${T.border}` }}>
        {(['config', 'cache'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              flex: 1,
              padding: '8px 12px',
              background: activeTab === tab ? `${T.cyan}10` : 'none',
              border: 'none',
              borderBottom: activeTab === tab ? `2px solid ${T.cyan}` : '2px solid transparent',
              color: activeTab === tab ? T.text : T.dim,
              fontFamily: F,
              fontSize: FS.xs,
              fontWeight: activeTab === tab ? 600 : 400,
              cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {tab === 'config' ? 'Config Lineage' : 'Cache'}
          </button>
        ))}
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
        {loading && (
          <div style={{ color: T.dim, fontSize: FS.xs, textAlign: 'center', padding: 32 }}>
            Loading plan...
          </div>
        )}
        {error && (
          <div style={{ color: T.red, fontSize: FS.xs, padding: 16 }}>{error}</div>
        )}
        {!loading && !error && !planNode && (
          <div style={{ color: T.dim, fontSize: FS.xs, padding: 16 }}>
            Node not found in plan. This may be a visual-only node.
          </div>
        )}

        {!loading && !error && planNode && activeTab === 'config' && (
          <ConfigTab
            planNode={planNode}
            nodeMap={nodeMap}
            showEffective={showEffective}
            onToggleEffective={() => setShowEffective(!showEffective)}
          />
        )}

        {!loading && !error && planNode && activeTab === 'cache' && (
          <CacheTab
            planNode={planNode}
            upstreamChain={upstreamChain}
            copiedFp={copiedFp}
            onCopyFingerprint={copyFingerprint}
            runId={activeRunId}
          />
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Config Tab (Task 98)
// ---------------------------------------------------------------------------

function ConfigTab({
  planNode,
  nodeMap,
  showEffective,
  onToggleEffective,
}: {
  planNode: PlanNode
  nodeMap: Record<string, any>
  showEffective: boolean
  onToggleEffective: () => void
}) {
  const configKeys = Object.keys(planNode.resolved_config).sort()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Block metadata */}
      <div
        style={{
          display: 'flex',
          gap: 8,
          fontSize: FS.xxs,
          color: T.dim,
        }}
      >
        <span>
          {planNode.block_type} v{planNode.block_version}
        </span>
        {planNode.in_loop && (
          <span
            style={{
              background: `${T.amber}22`,
              color: T.amber,
              padding: '1px 6px',
              borderRadius: 3,
              fontSize: FS.xxs,
            }}
          >
            in loop
          </span>
        )}
      </div>

      {/* Config fields */}
      {configKeys.length === 0 && (
        <div style={{ color: T.dim, fontSize: FS.xs }}>No config fields</div>
      )}
      {configKeys.map((key) => {
        const value = planNode.resolved_config[key]
        const source = planNode.config_sources[key] || 'unknown'
        const badge = sourceBadgeStyle(source)
        const originName = getOriginNodeName(source, nodeMap)

        return (
          <div
            key={key}
            style={{
              padding: '8px 10px',
              background: T.surface2,
              borderRadius: 4,
              border: `1px solid ${T.border}`,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <span style={{ fontSize: FS.xs, color: T.sec, fontWeight: 500 }}>{key}</span>
              <span
                style={{
                  fontSize: 9,
                  padding: '1px 6px',
                  borderRadius: 3,
                  background: badge.bg,
                  color: badge.fg,
                  fontWeight: 500,
                  whiteSpace: 'nowrap',
                }}
              >
                {badge.label}
              </span>
            </div>
            <div
              style={{
                fontFamily: FCODE,
                fontSize: FS.xxs,
                color: T.text,
                wordBreak: 'break-all',
                lineHeight: 1.4,
              }}
            >
              {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
            </div>
            {originName && (
              <div style={{ fontSize: 9, color: T.dim, marginTop: 3 }}>
                from: {originName}
              </div>
            )}
          </div>
        )
      })}

      {/* Show Effective Config button */}
      <button
        onClick={onToggleEffective}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '8px 12px',
          background: showEffective ? `${T.cyan}12` : T.surface3,
          border: `1px solid ${showEffective ? T.cyan + '40' : T.border}`,
          borderRadius: 4,
          color: T.sec,
          fontFamily: F,
          fontSize: FS.xs,
          cursor: 'pointer',
        }}
      >
        {showEffective ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        Show Effective Config
      </button>

      {showEffective && (
        <pre
          style={{
            fontFamily: FCODE,
            fontSize: FS.xxs,
            color: T.text,
            background: T.surface0,
            border: `1px solid ${T.border}`,
            borderRadius: 4,
            padding: 12,
            overflow: 'auto',
            maxHeight: 400,
            whiteSpace: 'pre-wrap',
            lineHeight: 1.5,
          }}
        >
          {JSON.stringify(planNode.resolved_config, null, 2)}
        </pre>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Cache Tab (Task 99)
// ---------------------------------------------------------------------------

function CacheTab({
  planNode,
  upstreamChain,
  copiedFp,
  onCopyFingerprint,
  runId,
}: {
  planNode: PlanNode
  upstreamChain: { id: string; label: string; fingerprint: string }[]
  copiedFp: boolean
  onCopyFingerprint: (fp: string) => void
  runId: string | null
}) {
  const [artifacts, setArtifacts] = useState<any[] | null>(null)
  const [loadingArtifacts, setLoadingArtifacts] = useState(false)

  // Fetch artifacts for previous run if exists
  useEffect(() => {
    if (!runId) return
    setLoadingArtifacts(true)
    api
      .get<any[]>(`/runs/${runId}/artifacts`)
      .then((data) => {
        // Filter to this node's artifacts
        const nodeArtifacts = (data || []).filter(
          (a: any) => a.node_id === planNode.node_id
        )
        setArtifacts(nodeArtifacts)
        setLoadingArtifacts(false)
      })
      .catch(() => {
        setArtifacts(null)
        setLoadingArtifacts(false)
      })
  }, [runId, planNode.node_id])

  const fpShort = planNode.cache_fingerprint
    ? planNode.cache_fingerprint.slice(0, 12)
    : '—'

  const cacheIneligibleReason = !planNode.cache_eligible
    ? planNode.in_loop
      ? 'Node is inside a loop'
      : 'Cache not available for this node type'
    : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Cache Eligible */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '10px 12px',
          background: T.surface2,
          borderRadius: 4,
          border: `1px solid ${T.border}`,
        }}
      >
        {planNode.cache_eligible ? (
          <CheckCircle size={16} color={T.green} />
        ) : (
          <XCircle size={16} color={T.red} />
        )}
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: FS.xs, color: T.text, fontWeight: 500 }}>
            Cache Eligible
          </div>
          {cacheIneligibleReason && (
            <div style={{ fontSize: FS.xxs, color: T.dim, marginTop: 2 }}>
              {cacheIneligibleReason}
            </div>
          )}
        </div>
      </div>

      {/* Cache Fingerprint */}
      <div
        style={{
          padding: '10px 12px',
          background: T.surface2,
          borderRadius: 4,
          border: `1px solid ${T.border}`,
        }}
      >
        <div style={{ fontSize: FS.xxs, color: T.dim, marginBottom: 4 }}>
          Cache Fingerprint
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <code
            style={{
              fontFamily: FCODE,
              fontSize: FS.xs,
              color: T.text,
              background: T.surface0,
              padding: '2px 6px',
              borderRadius: 3,
            }}
          >
            {fpShort}
          </code>
          <button
            onClick={() => onCopyFingerprint(planNode.cache_fingerprint)}
            style={{
              background: 'none',
              border: 'none',
              color: copiedFp ? T.green : T.dim,
              cursor: 'pointer',
              padding: 2,
            }}
            title="Copy full fingerprint"
          >
            {copiedFp ? <Check size={12} /> : <Copy size={12} />}
          </button>
        </div>
      </div>

      {/* Dependency Chain */}
      <div
        style={{
          padding: '10px 12px',
          background: T.surface2,
          borderRadius: 4,
          border: `1px solid ${T.border}`,
        }}
      >
        <div style={{ fontSize: FS.xxs, color: T.dim, marginBottom: 6 }}>
          Dependency Chain
        </div>
        {upstreamChain.length === 0 ? (
          <div style={{ fontSize: FS.xs, color: T.dim }}>No upstream dependencies</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {upstreamChain.map((dep) => (
              <div
                key={dep.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  fontSize: FS.xxs,
                  padding: '3px 0',
                }}
              >
                <span style={{ color: T.sec, fontWeight: 500, flex: 1 }}>{dep.label}</span>
                <code
                  style={{
                    fontFamily: FCODE,
                    fontSize: 9,
                    color: T.dim,
                    background: T.surface0,
                    padding: '1px 4px',
                    borderRadius: 2,
                  }}
                >
                  {dep.fingerprint.slice(0, 8)}
                </code>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Previous Run Info */}
      {runId && (
        <div
          style={{
            padding: '10px 12px',
            background: T.surface2,
            borderRadius: 4,
            border: `1px solid ${T.border}`,
          }}
        >
          <div style={{ fontSize: FS.xxs, color: T.dim, marginBottom: 6 }}>
            Last Cached Run
          </div>
          {loadingArtifacts ? (
            <div style={{ fontSize: FS.xs, color: T.dim }}>Loading...</div>
          ) : artifacts && artifacts.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div style={{ fontSize: FS.xxs, color: T.sec }}>
                Run: <code style={{ fontFamily: FCODE, fontSize: 9 }}>{runId.slice(0, 8)}</code>
              </div>
              {artifacts.map((a: any, i: number) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    fontSize: FS.xxs,
                    color: T.dim,
                  }}
                >
                  <span style={{ flex: 1 }}>{a.name || a.artifact_type}</span>
                  {a.size_bytes != null && (
                    <span>{formatBytes(a.size_bytes)}</span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: FS.xs, color: T.dim }}>No cached artifacts for this node</div>
          )}
        </div>
      )}

      {/* What Would Invalidate Cache */}
      <div
        style={{
          padding: '10px 12px',
          background: T.surface2,
          borderRadius: 4,
          border: `1px solid ${T.border}`,
        }}
      >
        <div style={{ fontSize: FS.xxs, color: T.dim, marginBottom: 6 }}>
          What would invalidate this cache:
        </div>
        <ul
          style={{
            margin: 0,
            paddingLeft: 16,
            fontSize: FS.xxs,
            color: T.sec,
            lineHeight: 1.8,
            listStyleType: 'disc',
          }}
        >
          <li>Any config value change on this node</li>
          <li>Upstream node config or output change</li>
          <li>Block version update ({planNode.block_type} v{planNode.block_version})</li>
          {upstreamChain.length > 0 && (
            <li>
              Change in upstream nodes: {upstreamChain.map((d) => d.label).join(', ')}
            </li>
          )}
        </ul>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
}
