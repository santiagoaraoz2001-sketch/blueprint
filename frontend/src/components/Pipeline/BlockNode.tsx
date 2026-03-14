import { memo, useCallback, useMemo, useState } from 'react'
import { Handle, Position, useStore } from '@xyflow/react'
import { T, F, FS } from '@/lib/design-tokens'
import { getBlockDefinition, getPortColor, computeBlockWidth } from '@/lib/block-registry'
import { getIcon } from '@/lib/icon-utils'
import ProgressBar from '@/components/shared/ProgressBar'
import { usePipelineStore, type BlockNodeData } from '@/stores/pipelineStore'
import { useRunStore } from '@/stores/runStore'
import { OVERLAY_COLORS } from './InheritanceOverlay'
import { AlertTriangle, Clock } from 'lucide-react'
import { estimatePipeline, formatTimeShort } from '@/lib/pipeline-estimator'

function BlockNode({ id, data, selected }: { id: string; data: BlockNodeData; selected?: boolean }) {
  const [isHovered, setIsHovered] = useState(false)
  const [hoveredPort, setHoveredPort] = useState<string | null>(null)

  // Count connections per handle — uses ReactFlow internal store with custom equality
  // so this node ONLY re-renders when its OWN connection counts change (not all edges).
  const connectionSelector = useCallback(
    (s: any) => {
      const counts: Record<string, number> = {}
      for (const edge of s.edges) {
        if (edge.target === id && edge.targetHandle)
          counts[`in-${edge.targetHandle}`] = (counts[`in-${edge.targetHandle}`] || 0) + 1
        if (edge.source === id && edge.sourceHandle)
          counts[`out-${edge.sourceHandle}`] = (counts[`out-${edge.sourceHandle}`] || 0) + 1
      }
      return counts
    },
    [id]
  )
  const handleConnectionCounts = useStore(
    connectionSelector,
    (a, b) => JSON.stringify(a) === JSON.stringify(b)
  )

  const focusedErrorNodeId = usePipelineStore((s) => s.focusedErrorNodeId)
  const isErrorFocused = focusedErrorNodeId === id

  // Inheritance overlay — derived selector returns primitive for O(1) lookup + minimal re-renders
  const overlayRole = usePipelineStore(
    (s): 'origin' | 'inheriting' | 'overriding' | 'dimmed' | null => {
      if (!s.inheritanceOverlay) return null
      return s.inheritanceOverlay.nodeRoles[id] ?? 'dimmed'
    }
  )

  // Subscribe to live run status directly — avoids cascading pipelineStore updates
  const nodeRunStatus = useRunStore((s) => s.nodeStatuses[id])
  const effectiveStatus: 'idle' | 'running' | 'complete' | 'failed' | 'pending' =
    nodeRunStatus?.status ?? (data.status as any) ?? 'idle'
  const effectiveProgress = nodeRunStatus?.progress ?? data.progress ?? 0

  const def = getBlockDefinition(data.type)
  const accent = data.accent || T.cyan

  const IconComponent = getIcon(data.icon)

  const statusColors: Record<string, string> = {
    idle: T.dim,
    running: T.amber,
    complete: T.green,
    failed: T.red,
  }
  const statusColor = statusColors[effectiveStatus] || T.dim

  const configSummary = Object.entries(data.config || {})
    .filter(([, v]) => v !== '' && v !== 0 && v !== false && v !== null)
    .slice(0, 2)
    .map(([k, v]) => `${k}=${typeof v === 'number' ? v : `"${String(v).slice(0, 20)}"`}`)
    .join(', ')

  // Compute horizontal positions for top/bottom handles
  const inputCount = def?.inputs.length ?? 0
  const outputCount = def?.outputs.length ?? 0

  // Dynamic width based on port count
  const blockWidth = def ? computeBlockWidth(def) : 280

  // Should we truncate port labels? (5+ ports on a side)
  const maxPorts = Math.max(inputCount, outputCount)
  const truncateLabels = maxPorts >= 5

  // Time estimate for this block — stringify config to avoid unstable object reference
  const timeEst = useMemo(() => {
    const fakeNode = { id, data, position: { x: 0, y: 0 }, type: 'blockNode' as const }
    const result = estimatePipeline([fakeNode])
    return result.blockEstimates[0] ?? null
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, data.type, JSON.stringify(data.config)])

  return (
    <div
      role="group"
      aria-label={`${data.label} block, category ${data.category}, status ${effectiveStatus}`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => { setIsHovered(false); setHoveredPort(null) }}
      className={selected ? 'ring-pulse' : isErrorFocused ? 'error-pulse' : ''}
      style={{
        width: blockWidth,
        background: `linear-gradient(145deg, ${T.surface2} 0%, ${T.surface1} 100%)`,
        backdropFilter: 'blur(16px)',
        borderRadius: 8,
        border: `1px solid ${isErrorFocused ? T.red : selected ? accent : isHovered ? T.borderHi : T.border}`,
        transition: 'border-color 0.2s, box-shadow 0.2s, opacity 0.3s',
        boxShadow: isErrorFocused
          ? `0 8px 32px ${T.red}60, 0 0 0 2px ${T.red}`
          : selected
            ? `0 0 0 1px ${accent}40, 0 8px 32px ${T.shadowHeavy}`
            : isHovered
              ? `0 8px 24px ${T.shadow}, inset 0 1px 0 rgba(255,255,255,0.05)`
              : `0 4px 12px ${T.shadow}`,
        position: 'relative',
        overflow: 'visible',
        zIndex: selected || isErrorFocused ? 10 : isHovered ? 5 : 1,
        opacity: overlayRole === 'dimmed' ? 0.2 : 1,
      }}
    >
      {/* Top accent bar */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: 3,
          background: `linear-gradient(90deg, ${accent}, ${accent}40, transparent)`,
          opacity: isHovered || selected ? 1 : 0.6,
          transition: 'opacity 0.2s',
          boxShadow: `0 0 8px ${accent}40`,
          borderRadius: '8px 8px 0 0',
        }}
      />

      {/* Internal ambient glow */}
      {(isHovered || selected) && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: 60,
            background: `radial-gradient(100% 100% at 50% 0%, ${accent}15 0%, transparent 100%)`,
            pointerEvents: 'none',
            borderRadius: '8px 8px 0 0',
          }}
        />
      )}

      {/* Status dot */}
      <div
        role="status"
        aria-label={`Status: ${effectiveStatus}`}
        style={{
          position: 'absolute',
          top: 10,
          right: 12,
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: statusColor,
          boxShadow: effectiveStatus === 'running' || effectiveStatus === 'complete' ? `0 0 8px ${statusColor}` : 'none',
          animation: effectiveStatus === 'running' ? 'blink 2s ease-in-out infinite' : 'none',
          zIndex: 2,
        }}
      />

      {/* Inheritance overlay badge */}
      {overlayRole && overlayRole !== 'dimmed' && (
        <div style={{
          position: 'absolute',
          top: -5,
          left: -5,
          width: 12,
          height: 12,
          borderRadius: '50%',
          background: OVERLAY_COLORS[overlayRole],
          boxShadow: `0 0 8px ${OVERLAY_COLORS[overlayRole]}80`,
          zIndex: 20,
          border: '2px solid rgba(0,0,0,0.6)',
        }} />
      )}

      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '12px 14px 8px 14px',
          borderBottom: `1px solid ${T.border}`,
          zIndex: 1,
          position: 'relative',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 24,
            height: 24,
            borderRadius: 4,
            background: isErrorFocused ? `${T.red}20` : `linear-gradient(135deg, ${T.surface3}, ${T.surface1})`,
            border: `1px solid ${isErrorFocused ? T.red : T.borderHi}`,
            boxShadow: isHovered && !isErrorFocused ? `0 0 12px ${accent}30` : `0 2px 4px ${T.shadowLight}`,
            transition: 'all 0.2s',
          }}
        >
          {isErrorFocused ? (
            <AlertTriangle size={12} color={T.red} />
          ) : (
            <IconComponent size={12} color={accent} strokeWidth={2.5} />
          )}
        </div>
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <div
            style={{
              fontFamily: F,
              fontSize: FS.sm,
              color: T.text,
              fontWeight: 700,
              letterSpacing: '0.02em',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {data.label}
          </div>
        </div>
      </div>

      {/* Description — always visible */}
      {def?.description && (
        <div style={{ padding: '6px 12px', borderBottom: `1px solid ${T.border}`, background: `${T.surface1}90` }}>
          <div style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.sec,
            lineHeight: 1.5,
            overflow: 'hidden',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
          }}>
            {def.description}
          </div>
        </div>
      )}

      {/* Config summary */}
      {configSummary && (
        <div style={{ padding: '6px 12px 8px', background: T.shadowLight }}>
          <span
            style={{
              fontFamily: F,
              fontSize: FS.xs,
              color: T.dim,
              display: 'block',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {configSummary}
          </span>
        </div>
      )}

      {/* Progress bar (shown when running) */}
      {effectiveStatus === 'running' && (
        <div style={{ padding: '2px 8px 6px' }}>
          <ProgressBar value={effectiveProgress * 100} color={T.amber} height={2} showLabel />
        </div>
      )}

      {/* Time estimate badge — only when block is not running/complete/failed */}
      {timeEst && !nodeRunStatus && data.status === 'idle' && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          padding: '3px 10px 4px',
          borderTop: `1px solid ${T.border}08`,
        }}>
          <Clock size={8} color={timeEst.warnings.length > 0 ? T.amber : T.dim} />
          <span style={{
            fontFamily: F,
            fontSize: 7.5,
            color: timeEst.warnings.length > 0 ? T.amber : T.dim,
            letterSpacing: '0.04em',
            fontWeight: 600,
          }}>
            {formatTimeShort(timeEst.seconds)}
          </span>
          {timeEst.gpuRequired && (
            <span style={{
              fontFamily: F,
              fontSize: 6.5,
              color: T.dim,
              letterSpacing: '0.04em',
              opacity: 0.7,
            }}>
              GPU
            </span>
          )}
          {timeEst.warnings.length > 0 && (
            <AlertTriangle size={7} color={T.amber} />
          )}
        </div>
      )}

      {/* ── Input handles — TOP side, horizontally distributed with pixel spacing ── */}
      {def?.inputs.map((input, i) => {
        const portColor = getPortColor(input.dataType)
        const isPortHovered = hoveredPort === `in-${input.id}`
        const isRequired = input.required
        const connCount = handleConnectionCounts[`in-${input.id}`] || 0
        const portSpacing = blockWidth / (inputCount + 1)
        const leftPx = portSpacing * (i + 1)
        const labelText = truncateLabels && input.label.length > 8
          ? input.label.slice(0, 7) + '…'
          : input.label
        return (
          <div key={`in-${input.id}`}>
            <Handle
              type="target"
              position={Position.Top}
              id={input.id}
              onMouseEnter={() => setHoveredPort(`in-${input.id}`)}
              onMouseLeave={() => setHoveredPort(null)}
              style={{
                width: 12,
                height: 12,
                background: isRequired ? portColor : T.surface0,
                border: `2px solid ${portColor}`,
                borderRadius: '50%',
                left: leftPx,
                top: -6,
                boxShadow: isPortHovered
                  ? `0 0 12px ${portColor}`
                  : `0 1px 4px ${T.shadow}`,
                transition: 'box-shadow 0.15s',
                zIndex: 10,
              }}
            />
            {/* Port label — above block, outside boundary */}
            <div style={{
              position: 'absolute',
              left: leftPx,
              top: -22,
              transform: 'translateX(-50%)',
              fontFamily: F,
              fontSize: 8,
              color: portColor,
              letterSpacing: '0.04em',
              fontWeight: 600,
              pointerEvents: 'none',
              whiteSpace: 'nowrap',
              textAlign: 'center',
              opacity: 0.9,
              zIndex: 15,
              textShadow: '0 1px 3px rgba(0,0,0,0.8)',
              maxWidth: truncateLabels ? portSpacing - 4 : undefined,
              overflow: truncateLabels ? 'hidden' : undefined,
              textOverflow: truncateLabels ? 'ellipsis' : undefined,
            }}>
              {isRequired && <span style={{ color: T.red, fontWeight: 900 }}>*</span>}
              {labelText}
              {!isRequired && <span style={{ opacity: 0.5 }}> ?</span>}
            </div>
            {/* Multi-connection badge */}
            {connCount > 1 && (
              <div style={{
                position: 'absolute',
                left: leftPx,
                top: -34,
                transform: 'translateX(-50%)',
                background: portColor,
                color: '#000',
                fontFamily: F,
                fontSize: '7px',
                fontWeight: 900,
                borderRadius: 6,
                padding: '0 3px',
                lineHeight: '12px',
                zIndex: 16,
                pointerEvents: 'none',
              }}>
                x{connCount}
              </div>
            )}
          </div>
        )
      })}

      {/* ── Output handles — BOTTOM side, horizontally distributed with pixel spacing ── */}
      {def?.outputs.map((output, i) => {
        const portColor = getPortColor(output.dataType)
        const isPortHovered = hoveredPort === `out-${output.id}`
        const isRequired = output.required
        const connCount = handleConnectionCounts[`out-${output.id}`] || 0
        const portSpacing = blockWidth / (outputCount + 1)
        const leftPx = portSpacing * (i + 1)
        const labelText = truncateLabels && output.label.length > 8
          ? output.label.slice(0, 7) + '…'
          : output.label
        return (
          <div key={`out-${output.id}`}>
            <Handle
              type="source"
              position={Position.Bottom}
              id={output.id}
              onMouseEnter={() => setHoveredPort(`out-${output.id}`)}
              onMouseLeave={() => setHoveredPort(null)}
              style={{
                width: 12,
                height: 12,
                background: isRequired ? portColor : T.surface0,
                border: `2px solid ${portColor}`,
                borderRadius: '50%',
                left: leftPx,
                bottom: -6,
                boxShadow: isPortHovered
                  ? `0 0 12px ${portColor}`
                  : `0 1px 4px ${T.shadow}`,
                transition: 'box-shadow 0.15s',
                zIndex: 10,
              }}
            />
            {/* Port label — below block, outside boundary */}
            <div style={{
              position: 'absolute',
              left: leftPx,
              bottom: -22,
              transform: 'translateX(-50%)',
              fontFamily: F,
              fontSize: 8,
              color: portColor,
              letterSpacing: '0.04em',
              fontWeight: 600,
              pointerEvents: 'none',
              whiteSpace: 'nowrap',
              textAlign: 'center',
              opacity: 0.9,
              zIndex: 15,
              textShadow: '0 1px 3px rgba(0,0,0,0.8)',
              maxWidth: truncateLabels ? portSpacing - 4 : undefined,
              overflow: truncateLabels ? 'hidden' : undefined,
              textOverflow: truncateLabels ? 'ellipsis' : undefined,
            }}>
              {labelText}
            </div>
            {/* Multi-connection badge */}
            {connCount > 1 && (
              <div style={{
                position: 'absolute',
                left: leftPx,
                bottom: -34,
                transform: 'translateX(-50%)',
                background: portColor,
                color: '#000',
                fontFamily: F,
                fontSize: '7px',
                fontWeight: 900,
                borderRadius: 6,
                padding: '0 3px',
                lineHeight: '12px',
                zIndex: 16,
                pointerEvents: 'none',
              }}>
                x{connCount}
              </div>
            )}
          </div>
        )
      })}

      {/* Hovered port tooltip — shows detailed info on handle hover */}
      {hoveredPort && def && (() => {
        const isInput = hoveredPort.startsWith('in-')
        const pid = hoveredPort.replace(/^(in|out)-/, '')
        const port = isInput
          ? def.inputs.find((p) => p.id === pid)
          : def.outputs.find((p) => p.id === pid)
        if (!port) return null
        const pc = getPortColor(port.dataType)
        return (
          <div
            style={{
              position: 'absolute',
              [isInput ? 'top' : 'bottom']: isInput ? -40 : -40,
              left: '50%',
              transform: 'translateX(-50%)',
              background: T.surface5,
              border: `1px solid ${pc}40`,
              padding: '3px 8px',
              zIndex: 100,
              whiteSpace: 'nowrap',
              pointerEvents: 'none',
              borderRadius: 4,
            }}
          >
            <span style={{ fontFamily: F, fontSize: 8, color: pc, fontWeight: 700, letterSpacing: '0.04em' }}>
              {port.label} · {port.dataType} · {port.required ? 'required' : 'optional'}
            </span>
          </div>
        )
      })()}
    </div>
  )
}

export default memo(BlockNode)
