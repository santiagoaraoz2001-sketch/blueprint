import { T, F, FS } from '@/lib/design-tokens'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useRunStore } from '@/stores/runStore'
import { RotateCcw, X, AlertTriangle, Lock, Info } from 'lucide-react'
import ConfigDiffPreview from './ConfigDiffPreview'
import toast from 'react-hot-toast'

export default function RerunOverlay() {
  const rerunMode = usePipelineStore((s) => s.rerunMode)
  const nodes = usePipelineStore((s) => s.nodes)
  const pipelineId = usePipelineStore((s) => s.id)
  const exitRerunMode = usePipelineStore((s) => s.exitRerunMode)

  if (!rerunMode?.active) return null

  const startNode = nodes.find((n) => n.id === rerunMode.startNodeId)
  const startNodeLabel = startNode?.data?.label || rerunMode.startNodeId

  const handleCancel = () => {
    // Restore original configs when canceling
    exitRerunMode(true)
  }

  const handleRerun = async () => {
    if (!pipelineId) {
      toast.error('Save pipeline first')
      return
    }

    const { sourceRunId, startNodeId, originalConfigs, cachedNodes } = rerunMode

    // Compute config overrides by diffing current node config against original
    const configOverrides: Record<string, Record<string, any>> = {}
    for (const [nodeId, originalConfig] of Object.entries(originalConfigs)) {
      const currentNode = nodes.find((n) => n.id === nodeId)
      if (!currentNode) continue
      const currentConfig = currentNode.data.config || {}
      const diff: Record<string, any> = {}
      const allKeys = new Set([...Object.keys(currentConfig), ...Object.keys(originalConfig)])
      let hasDiff = false
      for (const key of allKeys) {
        if (JSON.stringify(currentConfig[key]) !== JSON.stringify(originalConfig[key])) {
          diff[key] = currentConfig[key]
          hasDiff = true
        }
      }
      if (hasDiff) {
        // Send the full current config when there are overrides
        configOverrides[nodeId] = currentConfig
      }
    }

    // Exit rerun mode without restoring configs (keep the edits)
    exitRerunMode(false)

    // Start the partial run
    await useRunStore.getState().startPartialRun(
      pipelineId,
      sourceRunId,
      startNodeId,
      configOverrides,
      cachedNodes
    )

    toast.success(`Re-running from ${startNodeLabel}`)
  }

  // Check if source run's start node had a failure
  const nodeStatuses = useRunStore.getState().nodeStatuses
  const startNodePreviousStatus = nodeStatuses[rerunMode.startNodeId]
  const sourceNodeFailed = startNodePreviousStatus?.status === 'failed'

  // Check if any downstream nodes have no cached output in the source run
  const hasIncompleteSource = rerunMode.cachedNodes.some((nid) => {
    const ns = nodeStatuses[nid]
    return ns && ns.status !== 'complete' && ns.status !== 'cached'
  })

  // Count nodes that will re-run
  const rerunCount = 1 + rerunMode.downstreamNodes.length

  return (
    <>
      {/* Top info banner */}
      <div
        style={{
          position: 'absolute',
          top: 12,
          left: '50%',
          transform: 'translateX(-50%)',
          background: `linear-gradient(135deg, ${T.surface2}, ${T.surface3})`,
          border: `1px solid ${T.cyan}30`,
          borderRadius: 8,
          padding: '8px 16px',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          zIndex: 100,
          boxShadow: `0 4px 20px ${T.shadowHeavy}`,
          fontFamily: F,
          maxWidth: '80%',
        }}
      >
        <RotateCcw size={12} color={T.cyan} style={{ flexShrink: 0 }} />
        <span style={{ fontSize: FS.sm, color: T.text, fontWeight: 600 }}>
          Re-run mode
        </span>
        <div style={{ width: 1, height: 14, background: T.border, flexShrink: 0 }} />
        <span style={{ fontSize: FS.xs, color: T.sec }}>
          Starting from <span style={{ color: T.cyan, fontWeight: 600 }}>{startNodeLabel}</span>
        </span>
        <div style={{ width: 1, height: 14, background: T.border, flexShrink: 0 }} />
        <span style={{ fontSize: FS.xxs, color: T.dim }}>
          <Lock size={8} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 2 }} />
          {rerunMode.cachedNodes.length} cached
        </span>
        <span style={{ fontSize: FS.xxs, color: T.blue }}>
          {rerunCount} will run
        </span>
        <Info
          size={10}
          color={T.dim}
          style={{ cursor: 'help', flexShrink: 0 }}
          title="Edit the start node's config, then click Re-run. Upstream nodes use cached outputs. Press Escape to cancel."
        />
      </div>

      {/* Config diff preview — positioned to the right */}
      <div
        style={{
          position: 'absolute',
          top: 56,
          right: 12,
          zIndex: 100,
        }}
      >
        <ConfigDiffPreview
          startNodeId={rerunMode.startNodeId}
          originalConfigs={rerunMode.originalConfigs}
          cachedNodes={rerunMode.cachedNodes}
          downstreamNodes={rerunMode.downstreamNodes}
        />
      </div>

      {/* Warnings */}
      {(sourceNodeFailed || hasIncompleteSource) && (
        <div
          style={{
            position: 'absolute',
            top: 56,
            left: 12,
            zIndex: 100,
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
            maxWidth: 320,
          }}
        >
          {sourceNodeFailed && (
            <WarningBadge>
              This node failed in the source run. Consider adjusting its config before re-running.
            </WarningBadge>
          )}
          {hasIncompleteSource && (
            <WarningBadge>
              Some cached nodes did not complete in the source run. Their outputs may be unavailable.
            </WarningBadge>
          )}
        </div>
      )}

      {/* Floating action bar — bottom center */}
      <div
        style={{
          position: 'absolute',
          bottom: 24,
          left: '50%',
          transform: 'translateX(-50%)',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          zIndex: 100,
        }}
      >
        <button
          onClick={handleCancel}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '8px 16px',
            background: T.surface3,
            border: `1px solid ${T.border}`,
            borderRadius: 6,
            color: T.sec,
            fontFamily: F,
            fontSize: FS.sm,
            cursor: 'pointer',
            fontWeight: 500,
            transition: 'background 0.15s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = T.surface4
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = T.surface3
          }}
        >
          <X size={12} />
          Cancel
        </button>

        <button
          onClick={handleRerun}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '8px 20px',
            background: `linear-gradient(135deg, ${T.cyan}, ${T.cyan}cc)`,
            border: 'none',
            borderRadius: 6,
            color: '#000',
            fontFamily: F,
            fontSize: FS.sm,
            fontWeight: 700,
            cursor: 'pointer',
            boxShadow: `0 2px 12px ${T.cyan}40`,
            letterSpacing: '0.02em',
            transition: 'box-shadow 0.15s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.boxShadow = `0 4px 20px ${T.cyan}60`
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.boxShadow = `0 2px 12px ${T.cyan}40`
          }}
        >
          <RotateCcw size={12} />
          Re-run from {startNodeLabel} →
        </button>
      </div>
    </>
  )
}

function WarningBadge({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        background: `${T.amber}12`,
        border: `1px solid ${T.amber}30`,
        borderRadius: 6,
        padding: '6px 10px',
        display: 'flex',
        alignItems: 'flex-start',
        gap: 6,
        fontFamily: F,
      }}
    >
      <AlertTriangle size={10} color={T.amber} style={{ marginTop: 1, flexShrink: 0 }} />
      <span style={{ fontSize: FS.xxs, color: T.amber, lineHeight: 1.5 }}>
        {children}
      </span>
    </div>
  )
}
