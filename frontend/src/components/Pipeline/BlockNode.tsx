import { memo, useCallback, useMemo, useState } from 'react'
import { Handle, Position, useStore } from '@xyflow/react'
import { T, F, FS } from '@/lib/design-tokens'
import { getBlockDefinition, getPortColor, computeBlockWidth } from '@/lib/block-registry'
import { getIcon } from '@/lib/icon-utils'
import ProgressBar from '@/components/shared/ProgressBar'
import { usePipelineStore, type BlockNodeData, type NodeExecutionState } from '@/stores/pipelineStore'
import { useRunStore } from '@/stores/runStore'
import { OVERLAY_COLORS } from './InheritanceOverlay'
import { AlertTriangle, Clock, Lock } from 'lucide-react'
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
  const effectiveStatus: 'idle' | 'running' | 'complete' | 'failed' | 'pending' | 'cached' =
    nodeRunStatus?.status ?? (data.status as any) ?? 'idle'
  const effectiveProgress = nodeRunStatus?.progress ?? data.progress ?? 0

  // Re-run mode visual state
  const rerunNodeState: NodeExecutionState | null = usePipelineStore(
    (s) => s.rerunMode?.nodeStates[id] ?? null
  )
  const isRerunActive = usePipelineStore((s) => s.rerunMode?.active ?? false)

  const def = getBlockDefinition(data.type)
  const accent = data.accent || T.cyan

  const IconComponent = getIcon(data.icon)

  const statusColors: Record<string, string> = {
    idle: T.dim,
    running: T.amber,
    complete: T.green,
    failed: T.red,
    cached: T.dim,
    pending: T.dim,
  }
  const statusColor = statusColors[effectiveStatus] || T.dim

  // Rerun mode visual overrides
  const isCached = isRerunActive && rerunNodeState === 'cached'
  const isWillRerun = isRerunActive && rerunNodeState === 'will_rerun'
  const isWillRerunDownstream = isRerunActive && rerunNodeState === 'will_rerun_downstream'
  // Also dim nodes during live partial run when they're cached via SSE
  const isLiveCached = !isRerunActive && effectiveStatus === 'cached'
  const rerunOpacity = isCached || isLiveCached ? 0.45 : 1
  const rerunBorderColor = isWillRerun ? T.blue : isWillRerunDownstream ? `${T.blue}80` : undefined

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

  // Tiered label rendering: per-side based on port count
  // Tier 1 (1-3): horizontal labels, Tier 2 (4-5): rotated -45°, Tier 3 (6+): hover-only + dots
  const inputTier = inputCount >= 6 ? 3 : inputCount >= 4 ? 2 : 1
  const outputTier = outputCount >= 6 ? 3 : outputCount >= 4 ? 2 : 1

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
        border: `1px solid ${
          rerunBorderColor
            ? rerunBorderColor
            : isErrorFocused ? T.red : selected ? accent : isHovered ? T.borderHi : T.border
        }`,
        transition: 'border-color 0.2s, box-shadow 0.2s, opacity 0.3s',
        boxShadow: isWillRerun
          ? `0 0 0 2px ${T.blue}, 0 8px 32px ${T.blue}30`
          : isWillRerunDownstream
            ? `0 0 0 1px ${T.blue}60, 0 4px 16px ${T.blue}15`
            : isErrorFocused
              ? `0 8px 32px ${T.red}60, 0 0 0 2px ${T.red}`
              : selected
                ? `0 0 0 1px ${accent}40, 0 8px 32px ${T.shadowHeavy}`
                : isHovered
                  ? `0 8px 24px ${T.shadow}, inset 0 1px 0 rgba(255,255,255,0.05)`
                  : `0 4px 12px ${T.shadow}`,
        position: 'relative',
        overflow: 'visible',
        zIndex: selected || isErrorFocused ? 10 : isHovered ? 5 : 1,
        opacity: overlayRole === 'dimmed' ? 0.2 : rerunOpacity,
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

      {/* Cached badge (lock icon) — shown during re-run mode */}
      {isCached && (
        <div
          style={{
            position: 'absolute',
            top: 8,
            left: 8,
            display: 'flex',
            alignItems: 'center',
            gap: 3,
            background: `${T.surface4}dd`,
            border: `1px solid ${T.border}`,
            borderRadius: 4,
            padding: '2px 6px',
            zIndex: 20,
          }}
        >
          <Lock size={7} color={T.dim} />
          <span style={{ fontFamily: F, fontSize: 6.5, color: T.dim, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            Cached
          </span>
        </div>
      )}

      {/* Will re-run indicator */}
      {isWillRerun && (
        <div
          style={{
            position: 'absolute',
            top: 8,
            left: 8,
            display: 'flex',
            alignItems: 'center',
            gap: 3,
            background: `${T.blue}20`,
            border: `1px solid ${T.blue}60`,
            borderRadius: 4,
            padding: '2px 6px',
            zIndex: 20,
          }}
        >
          <span style={{ fontFamily: F, fontSize: 6.5, color: T.blue, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            Will re-run
          </span>
        </div>
      )}

      {/* Will re-run downstream indicator */}
      {isWillRerunDownstream && (
        <div
          style={{
            position: 'absolute',
            top: 8,
            left: 8,
            display: 'flex',
            alignItems: 'center',
            gap: 3,
            background: `${T.blue}10`,
            border: `1px solid ${T.blue}30`,
            borderRadius: 4,
            padding: '2px 6px',
            zIndex: 20,
          }}
        >
          <span style={{ fontFamily: F, fontSize: 6.5, color: `${T.blue}bb`, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            Downstream
          </span>
        </div>
      )}

      {/* SSE cached status badge (during live run) */}
      {effectiveStatus === 'cached' && !isRerunActive && (
        <div
          style={{
            position: 'absolute',
            top: 8,
            left: 8,
            display: 'flex',
            alignItems: 'center',
            gap: 3,
            background: `${T.surface4}dd`,
            border: `1px solid ${T.border}`,
            borderRadius: 4,
            padding: '2px 6px',
            zIndex: 20,
          }}
        >
          <Lock size={7} color={T.dim} />
          <span style={{ fontFamily: F, fontSize: 6.5, color: T.dim, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            Cached
          </span>
        </div>
      )}

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
        const maxLabelChars = inputTier === 3 ? 6 : inputTier === 2 ? 12 : 20
        const labelText = input.label.length > maxLabelChars
          ? input.label.slice(0, maxLabelChars - 1) + '…'
          : input.label
        const showLabel = inputTier < 3 || isPortHovered
        const labelRotation = inputTier === 2 ? -45 : 0
        const labelOffset = inputTier === 2 ? -28 : -22
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
            {/* Required indicator on handle (always visible) */}
            {isRequired && (
              <div style={{
                position: 'absolute',
                left: leftPx + 7,
                top: -3,
                color: T.red,
                fontSize: 10,
                fontWeight: 900,
                pointerEvents: 'none',
                zIndex: 20,
              }}>*</div>
            )}
            {/* Port label — above block, tiered rendering */}
            {showLabel && (
              <div style={{
                position: 'absolute',
                left: leftPx,
                top: labelOffset,
                transform: `translateX(-50%)${labelRotation ? ` rotate(${labelRotation}deg)` : ''}`,
                transformOrigin: 'center bottom',
                fontFamily: F,
                fontSize: inputTier === 2 ? 7.5 : 8,
                color: portColor,
                letterSpacing: '0.04em',
                fontWeight: 600,
                pointerEvents: 'none',
                whiteSpace: 'nowrap',
                textAlign: 'center',
                opacity: 0.9,
                zIndex: 15,
                textShadow: '0 1px 3px rgba(0,0,0,0.8)',
              }}>
                {labelText}
                {!isRequired && inputTier < 3 && <span style={{ opacity: 0.5 }}> ?</span>}
              </div>
            )}
            {/* Color dot indicator for Tier 3 (hover-only labels) */}
            {inputTier === 3 && !isPortHovered && (
              <div style={{
                position: 'absolute',
                left: leftPx,
                top: -14,
                transform: 'translateX(-50%)',
                width: 4,
                height: 4,
                borderRadius: '50%',
                background: portColor,
                opacity: 0.6,
                pointerEvents: 'none',
                zIndex: 15,
              }} />
            )}
            {/* Multi-connection badge */}
            {connCount > 1 && (
              <div style={{
                position: 'absolute',
                left: leftPx,
                top: inputTier === 3 ? (isPortHovered ? -34 : -20) : inputTier === 2 ? -42 : -34,
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
                transition: 'top 0.15s',
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
        const maxLabelChars = outputTier === 3 ? 6 : outputTier === 2 ? 12 : 20
        const labelText = output.label.length > maxLabelChars
          ? output.label.slice(0, maxLabelChars - 1) + '…'
          : output.label
        const showLabel = outputTier < 3 || isPortHovered
        const labelRotation = outputTier === 2 ? 45 : 0
        const labelOffset = outputTier === 2 ? -28 : -22
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
            {/* Required indicator on handle (always visible) */}
            {isRequired && (
              <div style={{
                position: 'absolute',
                left: leftPx + 7,
                bottom: -3,
                color: T.red,
                fontSize: 10,
                fontWeight: 900,
                pointerEvents: 'none',
                zIndex: 20,
              }}>*</div>
            )}
            {/* Port label — below block, tiered rendering */}
            {showLabel && (
              <div style={{
                position: 'absolute',
                left: leftPx,
                bottom: labelOffset,
                transform: `translateX(-50%)${labelRotation ? ` rotate(${labelRotation}deg)` : ''}`,
                transformOrigin: 'center top',
                fontFamily: F,
                fontSize: outputTier === 2 ? 7.5 : 8,
                color: portColor,
                letterSpacing: '0.04em',
                fontWeight: 600,
                pointerEvents: 'none',
                whiteSpace: 'nowrap',
                textAlign: 'center',
                opacity: 0.9,
                zIndex: 15,
                textShadow: '0 1px 3px rgba(0,0,0,0.8)',
              }}>
                {labelText}
              </div>
            )}
            {/* Color dot indicator for Tier 3 (hover-only labels) */}
            {outputTier === 3 && !isPortHovered && (
              <div style={{
                position: 'absolute',
                left: leftPx,
                bottom: -14,
                transform: 'translateX(-50%)',
                width: 4,
                height: 4,
                borderRadius: '50%',
                background: portColor,
                opacity: 0.6,
                pointerEvents: 'none',
                zIndex: 15,
              }} />
            )}
            {/* Multi-connection badge */}
            {connCount > 1 && (
              <div style={{
                position: 'absolute',
                left: leftPx,
                bottom: outputTier === 3 ? (isPortHovered ? -34 : -20) : outputTier === 2 ? -42 : -34,
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
                transition: 'bottom 0.15s',
              }}>
                x{connCount}
              </div>
            )}
          </div>
        )
      })}

      {/* ── Side input handles — LEFT side, vertically distributed ── */}
      {def?.side_inputs?.map((sideInput, i) => {
        const portColor = getPortColor(sideInput.dataType)
        const isPortHovered = hoveredPort === `side-${sideInput.id}`
        const sideCount = def.side_inputs?.length ?? 0
        // Use percentage-based positioning so ports adapt to any block height
        const topPct = ((i + 1) / (sideCount + 1)) * 100

        return (
          <div key={`side-${sideInput.id}`}>
            <Handle
              type="target"
              position={Position.Left}
              id={sideInput.id}
              onMouseEnter={() => setHoveredPort(`side-${sideInput.id}`)}
              onMouseLeave={() => setHoveredPort(null)}
              style={{
                width: 10,
                height: 10,
                background: T.surface0,
                border: `2px solid ${portColor}`,
                borderRadius: 2,
                left: -5,
                top: `${topPct}%`,
                transform: 'translateY(-50%)',
                boxShadow: isPortHovered ? `0 0 12px ${portColor}` : `0 1px 4px ${T.shadow}`,
                transition: 'box-shadow 0.15s',
                zIndex: 10,
              }}
            />
            {/* Side port label — to the left of the handle */}
            {isPortHovered && (
              <div style={{
                position: 'absolute',
                left: -60,
                top: `${topPct}%`,
                transform: 'translateY(-50%)',
                fontFamily: F,
                fontSize: 7,
                color: portColor,
                fontWeight: 600,
                pointerEvents: 'none',
                whiteSpace: 'nowrap',
                textAlign: 'right',
                opacity: 0.9,
                zIndex: 15,
              }}>
                {sideInput.label}
              </div>
            )}
          </div>
        )
      })}

      {/* Hovered port tooltip — shows detailed info on handle hover */}
      {hoveredPort && def && (() => {
        const isSide = hoveredPort.startsWith('side-')
        if (isSide) return null // Side ports show their own hover label
        const isInput = hoveredPort.startsWith('in-')
        const pid = hoveredPort.replace(/^(in|out)-/, '')
        const port = isInput
          ? def.inputs.find((p) => p.id === pid)
          : def.outputs.find((p) => p.id === pid)
        if (!port) return null
        const pc = getPortColor(port.dataType)
        const hoverTier = isInput ? inputTier : outputTier
        const tooltipOffset = hoverTier === 2 ? -54 : -40
        return (
          <div
            style={{
              position: 'absolute',
              [isInput ? 'top' : 'bottom']: tooltipOffset,
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
