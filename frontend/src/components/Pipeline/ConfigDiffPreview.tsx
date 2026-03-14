import { T, F, FS } from '@/lib/design-tokens'
import { usePipelineStore } from '@/stores/pipelineStore'
import { estimatePipeline, formatTimeShort } from '@/lib/pipeline-estimator'
import { Clock, ArrowRight } from 'lucide-react'

interface ConfigDiffPreviewProps {
  startNodeId: string
  originalConfigs: Record<string, Record<string, any>>
  cachedNodes: string[]
  downstreamNodes: string[]
}

interface DiffEntry {
  key: string
  oldVal: any
  newVal: any
}

export default function ConfigDiffPreview({
  startNodeId,
  originalConfigs,
  cachedNodes,
  downstreamNodes,
}: ConfigDiffPreviewProps) {
  const nodes = usePipelineStore((s) => s.nodes)
  const startNode = nodes.find((n) => n.id === startNodeId)
  if (!startNode) return null

  // Compute config diffs by comparing current node config against the original snapshot
  const currentConfig = startNode.data.config || {}
  const original = originalConfigs[startNodeId] || {}
  const diffs: DiffEntry[] = []

  // Check all keys in both current and original configs
  const allKeys = new Set([...Object.keys(currentConfig), ...Object.keys(original)])
  for (const key of allKeys) {
    const oldVal = original[key]
    const newVal = currentConfig[key]
    if (JSON.stringify(oldVal) !== JSON.stringify(newVal)) {
      diffs.push({ key, oldVal, newVal })
    }
  }

  // Estimate time saved by skipping cached nodes
  const cachedNodeObjs = nodes.filter((n) => cachedNodes.includes(n.id))
  const cachedEstimate = cachedNodeObjs.length > 0 ? estimatePipeline(cachedNodeObjs) : null
  const timeSaved = cachedEstimate?.totalSeconds ?? 0

  // Downstream node names
  const downstreamNames = downstreamNodes
    .map((id) => nodes.find((n) => n.id === id)?.data?.label || id)
    .slice(0, 5)

  return (
    <div
      style={{
        background: T.surface1,
        border: `1px solid ${T.border}`,
        borderRadius: 6,
        padding: '10px 12px',
        maxWidth: 360,
        fontFamily: F,
      }}
    >
      {/* Config changes */}
      {diffs.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div
            style={{
              fontSize: FS.xs,
              color: T.dim,
              fontWeight: 700,
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              marginBottom: 6,
            }}
          >
            {startNode.data.label} config changes
          </div>
          {diffs.slice(0, 8).map((d) => (
            <div
              key={d.key}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                fontSize: FS.xs,
                color: T.sec,
                marginBottom: 3,
                lineHeight: 1.6,
              }}
            >
              <span
                style={{
                  color: T.dim,
                  minWidth: 70,
                  maxWidth: 90,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  flexShrink: 0,
                }}
              >
                {d.key}:
              </span>
              <span
                style={{
                  color: T.red,
                  textDecoration: 'line-through',
                  opacity: 0.7,
                  maxWidth: 100,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {formatValue(d.oldVal)}
              </span>
              <ArrowRight size={8} color={T.dim} style={{ flexShrink: 0 }} />
              <span
                style={{
                  color: T.green,
                  fontWeight: 600,
                  maxWidth: 100,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {formatValue(d.newVal)}
              </span>
            </div>
          ))}
          {diffs.length > 8 && (
            <div style={{ fontSize: FS.xxs, color: T.dim, marginTop: 2 }}>
              +{diffs.length - 8} more changes
            </div>
          )}
        </div>
      )}

      {diffs.length === 0 && (
        <div style={{ fontSize: FS.xs, color: T.dim, marginBottom: 8 }}>
          No config changes — re-running with same parameters
        </div>
      )}

      {/* Downstream nodes */}
      {downstreamNames.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <span style={{ fontSize: FS.xxs, color: T.dim, fontWeight: 600 }}>
            Downstream affected:{' '}
          </span>
          <span style={{ fontSize: FS.xxs, color: T.sec }}>
            {downstreamNames.join(', ')}
            {downstreamNodes.length > 5 && ` +${downstreamNodes.length - 5} more`}
          </span>
        </div>
      )}

      {/* Time saved */}
      {timeSaved > 0 && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            fontSize: FS.xxs,
            color: T.green,
            fontWeight: 600,
          }}
        >
          <Clock size={8} />
          <span>
            Estimated time saved: ~{formatTimeShort(timeSaved)} (skipping{' '}
            {cachedNodes.length} node{cachedNodes.length !== 1 ? 's' : ''})
          </span>
        </div>
      )}
    </div>
  )
}

function formatValue(val: any): string {
  if (val === undefined || val === null) return '\u2014'
  if (typeof val === 'string') {
    const truncated = val.length > 24 ? val.slice(0, 24) + '...' : val
    return `"${truncated}"`
  }
  if (typeof val === 'boolean') return val ? 'true' : 'false'
  if (typeof val === 'number') return String(val)
  if (Array.isArray(val)) return `[${val.length} items]`
  if (typeof val === 'object') return `{${Object.keys(val).length} keys}`
  return String(val)
}
