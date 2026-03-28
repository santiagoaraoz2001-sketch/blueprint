import { useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useRunStore } from '@/stores/runStore'
import { useReactFlow } from '@xyflow/react'
import { Settings, Copy, Maximize, Trash2, RotateCcw, Eye, GitCompare, Circle, Filter, FileText, Search } from 'lucide-react'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import BreakpointConditionDialog from '@/components/Debug/BreakpointConditionDialog'
import { containsLoopOrCycle } from '@/lib/graph-utils'

interface NodeContextMenuProps {
  visible: boolean
  x: number
  y: number
  nodeId: string
  onClose: () => void
  onShowDoc?: (blockType: string) => void
  onInspectConfig?: (nodeId: string) => void
}

export default function NodeContextMenu({ visible, x, y, nodeId, onClose, onShowDoc, onInspectConfig }: NodeContextMenuProps) {
  const { fitView } = useReactFlow()
  const runStatus = useRunStore((s) => s.status)
  const activeRunId = useRunStore((s) => s.activeRunId)
  const nodeStatuses = useRunStore((s) => s.nodeStatuses)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showConditionDialog, setShowConditionDialog] = useState(false)
  if (!visible && !showDeleteConfirm && !showConditionDialog) return null

  const isRunComplete = runStatus === 'complete' || runStatus === 'failed'
  const nodeRunStatus = nodeStatuses[nodeId]
  const nodeHasOutput = nodeRunStatus?.status === 'complete' || nodeRunStatus?.status === 'cached'
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

  // Kill switch: check if pipeline contains loops or cycles
  const { nodes: allNodes, edges: allEdges } = usePipelineStore.getState()
  const hasLoopOrCycle = containsLoopOrCycle(allNodes, allEdges)

  // Can only re-run if upstream is all good and no loops/cycles
  const canRerun = canRerunFromHere && allUpstreamHaveOutputs && !hasLoopOrCycle

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

  // Breakpoint state
  const hasBreakpoint = usePipelineStore((s) => {
    const node = s.nodes.find((n) => n.id === nodeId)
    return !!node?.data?.breakpoint
  })

  const handleToggleBreakpoint = () => {
    usePipelineStore.getState().toggleBreakpoint(nodeId)
    onClose()
  }

  const handleDelete = () => {
    setShowDeleteConfirm(true)
    onClose()
  }

  const confirmDelete = () => {
    usePipelineStore.getState().removeNode(nodeId)
    setShowDeleteConfirm(false)
  }

  // Compute disabled reason for tooltip
  let rerunDisabledReason = ''
  if (hasLoopOrCycle) {
    rerunDisabledReason = 'Partial re-run is not available for pipelines with loops or cycles'
  } else if (!isRunComplete) {
    rerunDisabledReason = 'Run must be complete first'
  } else if (!allUpstreamHaveOutputs) {
    rerunDisabledReason = 'Upstream nodes have no cached outputs'
  }

  return (
    <div onClick={(e) => e.stopPropagation()}>
    {visible && <div
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

      {/* Breakpoint toggle */}
      <ContextMenuBtn
        icon={<Circle size={10} fill={hasBreakpoint ? T.red : 'none'} color={T.red} />}
        label={hasBreakpoint ? 'Remove Breakpoint' : 'Toggle Breakpoint'}
        shortcut="B"
        onClick={handleToggleBreakpoint}
      />
      {hasBreakpoint && (
        <ContextMenuBtn
          icon={<Filter size={10} />}
          label="Set Condition"
          shortcut=""
          onClick={() => { setShowConditionDialog(true); onClose() }}
        />
      )}
      <div style={{ height: 1, background: T.border, margin: '2px 0' }} />

      {/* Standard actions */}
      <ContextMenuBtn
        icon={<Settings size={10} />}
        label="Edit Config"
        shortcut=""
        onClick={handleEditConfig}
      />
      <ContextMenuBtn
        icon={<Search size={10} />}
        label="Inspect Config"
        shortcut=""
        onClick={() => {
          onInspectConfig?.(nodeId)
          onClose()
        }}
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
      <ContextMenuBtn
        icon={<FileText size={10} />}
        label="Documentation"
        shortcut="?"
        onClick={() => {
          const node = usePipelineStore.getState().nodes.find((n) => n.id === nodeId)
          if (node && onShowDoc) onShowDoc(node.data.type)
          onClose()
        }}
      />
      <div style={{ height: 1, background: T.border, margin: '2px 0' }} />
      <ContextMenuBtn
        icon={<Trash2 size={10} />}
        label="Delete"
        shortcut="\u232B"
        color={T.red}
        onClick={handleDelete}
      />
    </div>}
    <ConfirmDialog
      open={showDeleteConfirm}
      title="Delete Block"
      message="This block and its connections will be removed. You can undo with \u2318Z."
      confirmLabel="Delete"
      confirmColor={T.red}
      onConfirm={confirmDelete}
      onCancel={() => setShowDeleteConfirm(false)}
    />
    <BreakpointConditionDialog
      nodeId={nodeId}
      open={showConditionDialog}
      onClose={() => setShowConditionDialog(false)}
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
