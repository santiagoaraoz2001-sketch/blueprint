import { useMemo, useCallback, type RefObject } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { T, F, FS, CATEGORY_COLORS } from '@/lib/design-tokens'
import { getAllBlocks, getBlockDefinition, isPortCompatible } from '@/lib/block-registry'
import { computeBlockWidth } from '@/lib/block-registry-types'
import type { BlockDefinition, PortDefinition } from '@/lib/block-registry-types'
import { usePipelineStore } from '@/stores/pipelineStore'
import { getIcon } from '@/lib/icon-utils'
import { useShallow } from 'zustand/react/shallow'

const MAX_SUGGESTIONS = 5
const POPUP_WIDTH = 220
const ITEM_HEIGHT = 32
const HEADER_HEIGHT = 28
const PADDING = 8

interface PortMatch {
  sourcePort: PortDefinition
  targetPort: PortDefinition
  direction: 'downstream' | 'upstream'
  quality: number // 0-1
}

function scoreSuggestion(block: BlockDefinition, matches: PortMatch[]): number {
  if (matches.length === 0) return 0
  const bestMatch = Math.max(...matches.map((m) => m.quality))
  const recBonus = block.recommended ? 0.1 : 0
  return bestMatch + recBonus
}

function matchQuality(sourceType: string, targetType: string): number {
  if (!isPortCompatible(sourceType, targetType)) return 0
  if (sourceType === targetType) return 1.0
  return 0.5
}

interface BlockSuggestionsProps {
  /** Converts flow-space position → screen-space position. Obtained from useReactFlow(). */
  flowToScreenPosition: (pos: { x: number; y: number }) => { x: number; y: number }
  /** Ref to the outer container div of the canvas, used for viewport-relative clamping. */
  containerRef: RefObject<HTMLDivElement | null>
}

export default function BlockSuggestions({ flowToScreenPosition, containerRef }: BlockSuggestionsProps) {
  const { selectedNodeId, nodes, edges } = usePipelineStore(
    useShallow((s) => ({
      selectedNodeId: s.selectedNodeId,
      nodes: s.nodes,
      edges: s.edges,
    }))
  )

  const selectedNode = useMemo(
    () => nodes.find((n) => n.id === selectedNodeId),
    [nodes, selectedNodeId]
  )

  const selectedDef = useMemo(
    () => (selectedNode ? getBlockDefinition(selectedNode.data.type) : undefined),
    [selectedNode]
  )

  // Find unconnected ports on the selected node
  const unconnectedPorts = useMemo(() => {
    if (!selectedNode || !selectedDef) return { outputs: [] as PortDefinition[], inputs: [] as PortDefinition[] }

    const connectedOutputs = new Set(
      edges
        .filter((e) => e.source === selectedNode.id && e.sourceHandle)
        .map((e) => e.sourceHandle!)
    )
    const connectedInputs = new Set(
      edges
        .filter((e) => e.target === selectedNode.id && e.targetHandle)
        .map((e) => e.targetHandle!)
    )

    return {
      outputs: selectedDef.outputs.filter((p) => !connectedOutputs.has(p.id)),
      inputs: selectedDef.inputs.filter((p) => !connectedInputs.has(p.id)),
    }
  }, [selectedNode, selectedDef, edges])

  // Find suggested blocks
  const suggestions = useMemo(() => {
    if (!selectedNode || !selectedDef) return []
    const { outputs: openOutputs, inputs: openInputs } = unconnectedPorts
    if (openOutputs.length === 0 && openInputs.length === 0) return []

    const allBlocks = getAllBlocks()
    const scored: { block: BlockDefinition; score: number; bestMatch: PortMatch }[] = []

    for (const candidate of allBlocks) {
      if (candidate.type === selectedDef.type) continue

      const matches: PortMatch[] = []

      // Check if candidate's inputs match our unconnected outputs (downstream)
      for (const ourOutput of openOutputs) {
        for (const theirInput of candidate.inputs) {
          const quality = matchQuality(ourOutput.dataType, theirInput.dataType)
          if (quality > 0) {
            matches.push({
              sourcePort: ourOutput,
              targetPort: theirInput,
              direction: 'downstream',
              quality,
            })
          }
        }
      }

      // Check if candidate's outputs match our unconnected inputs (upstream)
      for (const ourInput of openInputs) {
        for (const theirOutput of candidate.outputs) {
          const quality = matchQuality(theirOutput.dataType, ourInput.dataType)
          if (quality > 0) {
            matches.push({
              sourcePort: theirOutput,
              targetPort: ourInput,
              direction: 'upstream',
              quality,
            })
          }
        }
      }

      if (matches.length > 0) {
        const score = scoreSuggestion(candidate, matches)
        const bestMatch = matches.sort((a, b) => b.quality - a.quality)[0]
        scored.push({ block: candidate, score, bestMatch })
      }
    }

    return scored
      .sort((a, b) => b.score - a.score)
      .slice(0, MAX_SUGGESTIONS)
  }, [selectedNode, selectedDef, unconnectedPorts])

  const handleAddSuggestion = useCallback(
    (block: BlockDefinition, match: PortMatch) => {
      if (!selectedNode) return
      const state = usePipelineStore.getState()

      if (match.direction === 'downstream') {
        state.addNodeAndConnect(block.type, {
          nodeId: selectedNode.id,
          portId: match.sourcePort.id,
          direction: 'downstream',
        })
      } else {
        state.addNodeAndConnect(block.type, {
          nodeId: selectedNode.id,
          portId: match.targetPort.id,
          direction: 'upstream',
        })
      }
    },
    [selectedNode]
  )

  // Don't render if no node is selected or no suggestions
  if (!selectedNode || !selectedDef || suggestions.length === 0) return null

  // ── Viewport-aware positioning ──
  // 1. Get node's right edge in flow coordinates
  const blockW = selectedNode.measured?.width ?? computeBlockWidth(selectedDef)
  const flowAnchor = {
    x: selectedNode.position.x + blockW + 16,
    y: selectedNode.position.y,
  }

  // 2. Convert to screen coordinates
  const screenPos = flowToScreenPosition(flowAnchor)

  // 3. Offset relative to the canvas container (absolute positioning within it)
  const containerRect = containerRef.current?.getBoundingClientRect()
  const containerW = containerRect?.width ?? window.innerWidth
  const containerH = containerRect?.height ?? window.innerHeight
  const containerLeft = containerRect?.left ?? 0
  const containerTop = containerRect?.top ?? 0

  let popupLeft = screenPos.x - containerLeft
  let popupTop = screenPos.y - containerTop

  // 4. Estimate popup height for clamping
  const popupH = HEADER_HEIGHT + suggestions.length * ITEM_HEIGHT + PADDING * 2

  // 5. Clamp to container bounds with margin
  const MARGIN = 8
  if (popupLeft + POPUP_WIDTH > containerW - MARGIN) {
    // Flip to left side of the node
    const leftFlowAnchor = { x: selectedNode.position.x - POPUP_WIDTH - 16, y: selectedNode.position.y }
    const leftScreenPos = flowToScreenPosition(leftFlowAnchor)
    popupLeft = leftScreenPos.x - containerLeft
    // If still out of bounds, clamp
    if (popupLeft < MARGIN) popupLeft = MARGIN
  }
  if (popupTop + popupH > containerH - MARGIN) {
    popupTop = Math.max(MARGIN, containerH - popupH - MARGIN)
  }
  if (popupLeft < MARGIN) popupLeft = MARGIN
  if (popupTop < MARGIN) popupTop = MARGIN

  return (
    <AnimatePresence>
      <motion.div
        key={selectedNode.id}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 4 }}
        transition={{ duration: 0.2, delay: 0.3 }}
        style={{
          position: 'absolute',
          left: popupLeft,
          top: popupTop,
          zIndex: 50,
          pointerEvents: 'auto',
        }}
      >
        <div
          style={{
            background: `linear-gradient(145deg, ${T.surface2} 0%, ${T.surface1} 100%)`,
            border: `1px solid ${T.borderHi}`,
            borderRadius: 8,
            boxShadow: `0 8px 24px ${T.shadow}`,
            padding: `${PADDING}px 6px`,
            minWidth: 180,
            maxWidth: POPUP_WIDTH,
          }}
        >
          {/* Header */}
          <div
            style={{
              fontFamily: F,
              fontSize: FS.xxs,
              color: T.dim,
              fontWeight: 900,
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              padding: '2px 8px 6px',
            }}
          >
            Connect next
          </div>

          {/* Suggestion chips */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {suggestions.map(({ block, bestMatch }) => {
              const IconComp = getIcon(block.icon)
              const catColor = CATEGORY_COLORS[block.category] || T.dim
              return (
                <button
                  key={block.type}
                  onClick={() => handleAddSuggestion(block, bestMatch)}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = `${T.cyan}12`
                    e.currentTarget.style.borderColor = `${T.cyan}25`
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'transparent'
                    e.currentTarget.style.borderColor = 'transparent'
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '6px 8px',
                    background: 'transparent',
                    border: '1px solid transparent',
                    borderRadius: 6,
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'background 0.1s, border-color 0.1s',
                    width: '100%',
                  }}
                >
                  {/* Category icon dot */}
                  <div
                    style={{
                      width: 20,
                      height: 20,
                      borderRadius: 4,
                      background: `${catColor}15`,
                      border: `1px solid ${catColor}30`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                    }}
                  >
                    <IconComp size={10} color={catColor} />
                  </div>
                  <span
                    style={{
                      fontFamily: F,
                      fontSize: FS.xxs,
                      color: T.text,
                      fontWeight: 600,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {block.name}
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
