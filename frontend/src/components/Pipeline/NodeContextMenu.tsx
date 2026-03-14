import { T, F, FS } from '@/lib/design-tokens'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useRunStore } from '@/stores/runStore'
import { useReactFlow } from '@xyflow/react'
import { Settings, Copy, Maximize, Trash2, RotateCcw, Eye, GitCompare } from 'lucide-react'

interface NodeContextMenuProps {
  visible: boolean
  x: number
  y: number
  nodeId: string
  onClose: () => void
}

export default function NodeContextMenu({ visible, x, y, nodeId, onClose }: NodeContextMenuProps) {
  const { fitView } = useReactFlow()
  const runStatus = useRunStore((s) => s.status)
  const activeRunId = useRunStore((s) => s.activeRunId)
  const nodeStatuses = useRunStore((s) => s.nodeStatuses)
  const nodeOutputs = useRunStore((s) => s.nodeOutputs)

  if (!visible) return null

  const isRunComplete = runStatus === 'complete' || runStatus === 'failed'
  const nodeRunStatus = nodeStatuses[nodeId]
  const nodeHasOutput = nodeRunStatus?.status === 'complete' || nodeRunStatus?.status === 'cached'
  const nodeIsFailed = nodeRunStatus?.status === 'failed'
  const nodeHasOutputData = !!nodeOutputs[nodeId] && Object.keys(nodeOutputs[nodeId]).length > 0

  // A node can be re-run from if:
  // 1. A run is complete (or failed)
  // 2. The node itself didn't fail (all upstream must have succeeded)
  // 3. There's an active run ID to use as source
  // Failed nodes CAN be re-run from (to retry with different config)
  // but nodes downstream of a failed node cannot if they have no cached outputs
  const canRerunFromHere = isRunComplete && activeRunId != null

  // Check if all upstream nodes have outputs (either complete or cached)
  const upstreamNodes = usePipelineStore.getState().getUpstreamNodes(nodeId)
  const allUpstreamHaveOutputs = upstreamNodes.every((uid) => {
    const s = nodeStatuses[uid]
    return s && (s.status === 'complete' || s.status === 'cached')
  })

  // Can only re-run if upstream is all good
  const canRerun = canRerunFromHere && allUpstreamHaveOutputs

  const handleRerunFromHere = () => {
    if (!activeRunId || !canRerun) return
    usePipelineStore.getState().enterRerunMode(nodeId, activeRunId)
    onClose()
  }

  const handleViewOutputs = () => {
    usePipelineStore.getState().selectNode(nodeId)
    onClose()
  }

  const handleEditConfig = () => {
    usePipelineStore.getState().selectNode(nodeId)
    onClose()
  }

  const handleDuplicate = () => {
    usePipelineStore.getState().duplicateNodes([nodeId])
    onClose()
  }

  const handleFocus = () => {
    fitView({ nodes: [{ id: nodeId }], duration: 400, padding: 0.5 })
    onClose()
  }

  const handleDelete = () => {
    usePipelineStore.getState().removeNode(nodeId)
    onClose()
  }

  // Compute disabled reason for tooltip
  let rerunDisabledReason = ''
  if (!isRunComplete) {
    rerunDisabledReason = 'Run must be complete first'
  } else if (!allUpstreamHaveOutputs) {
    rerunDisabledReason = 'Upstream nodes have no cached outputs'
  }

  return (
    <div
      style={{
        position: 'fixed',
        left: x,
        top: y,
        background: T.surface2,
        border: `1px solid ${T.borderHi}`,
        boxShadow: `0 4px 16px ${T.shadowHeavy}`,
        zIndex: 999,
        minWidth: 200,
        borderRadius: 4,
        overflow: 'hidden',
      }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Re-run section — only when a run exists */}
      {isRunComplete && activeRunId && (
        <>
          <ContextMenuBtn
            icon={<RotateCcw size={10} />}
            label="Re-run from here"
            shortcut="\u21E7R"
            disabled={!canRerun}
            disabledReason={rerunDisabledReason}
            onClick={handleRerunFromHere}
            highlight
          />
          <ContextMenuBtn
            icon={<Eye size={10} />}
            label="View outputs"
            shortcut=""
            disabled={!nodeHasOutput}
            disabledReason={!nodeHasOutput ? 'No outputs available' : ''}
            onClick={handleViewOutputs}
          />
          <ContextMenuBtn
            icon={<GitCompare size={10} />}
            label="Compare with..."
            shortcut=""
            disabled={!nodeHasOutput}
            disabledReason={!nodeHasOutput ? 'No outputs to compare' : ''}
            onClick={handleViewOutputs}
          />
          <div style={{ height: 1, background: T.border, margin: '2px 0' }} />
        </>
      )}

      {/* Standard actions */}
      <ContextMenuBtn
        icon={<Settings size={10} />}
        label="Edit Config"
        shortcut=""
        onClick={handleEditConfig}
      />
      <ContextMenuBtn
        icon={<Copy size={10} />}
        label="Duplicate"
        shortcut="\u2318C \u2318V"
        onClick={handleDuplicate}
      />
      <ContextMenuBtn
        icon={<Maximize size={10} />}
        label="Focus"
        shortcut="F"
        onClick={handleFocus}
      />
      <div style={{ height: 1, background: T.border, margin: '2px 0' }} />
      <ContextMenuBtn
        icon={<Trash2 size={10} />}
        label="Delete"
        shortcut="\u232B"
        color={T.red}
        onClick={handleDelete}
      />
    </div>
  )
}

function ContextMenuBtn({ icon, label, shortcut, onClick, color, disabled, disabledReason, highlight }: {
  icon: React.ReactNode
  label: string
  shortcut: string
  onClick: () => void
  color?: string
  disabled?: boolean
  disabledReason?: string
  highlight?: boolean
}) {
  return (
    <button
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      title={disabled ? disabledReason : undefined}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        width: '100%',
        padding: '6px 12px',
        background: highlight && !disabled ? `${T.cyan}08` : 'none',
        border: 'none',
        color: disabled ? T.dim : color || T.sec,
        fontFamily: F,
        fontSize: FS.xs,
        cursor: disabled ? 'default' : 'pointer',
        textAlign: 'left',
        opacity: disabled ? 0.4 : 1,
        transition: 'background 0.1s',
      }}
      onMouseEnter={(e) => {
        if (!disabled) e.currentTarget.style.background = T.surface4
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = highlight && !disabled ? `${T.cyan}08` : 'none'
      }}
    >
      {icon}
      <span style={{ flex: 1, fontWeight: highlight && !disabled ? 600 : 400 }}>{label}</span>
      {shortcut && (
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>{shortcut}</span>
      )}
    </button>
  )
}
