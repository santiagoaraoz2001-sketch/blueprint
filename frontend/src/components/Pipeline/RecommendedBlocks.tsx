import { useMemo } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { T, F, FS } from '@/lib/design-tokens'
import { BLOCK_REGISTRY, type BlockDefinition, isPortCompatible, getPortNames } from '@/lib/block-registry'
import { usePipelineStore } from '@/stores/pipelineStore'
import { getIcon } from '@/lib/icon-utils'
import { Sparkles, Plus, Lightbulb, ArrowDownToLine, ArrowUpFromLine, Zap } from 'lucide-react'

/**
 * RecommendedBlocks — persistent right-side panel that analyzes the current
 * pipeline and suggests blocks the user might want to add next.
 *
 * Now with AUTO-WIRING: clicking a recommendation adds the block AND connects
 * it to the relevant open port automatically.
 */

export interface Recommendation {
  block: BlockDefinition
  reason: string
  score: number
  // Connection info for auto-wiring
  connectTo?: {
    nodeId: string
    portId: string
    direction: 'upstream' | 'downstream'
  }
}

export interface SplitRecommendations {
  inputBlocks: Recommendation[]
  outputBlocks: Recommendation[]
}

function SectionHeader({ icon: Icon, label, accent }: { icon: any; label: string; accent: string }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      padding: '6px 4px 4px', marginTop: 4,
    }}>
      <Icon size={10} color={accent} />
      <div style={{
        fontFamily: F, fontSize: '8px', color: accent,
        fontWeight: 700, letterSpacing: '0.06em',
      }}>
        {label}
      </div>
    </div>
  )
}

function RecommendationCard({ rec, onAdd }: { rec: Recommendation; onAdd: () => void }) {
  const IconComp = getIcon(rec.block.icon)
  const accent = rec.block.accent || T.cyan
  const hasAutoWire = !!rec.connectTo
  return (
    <div
      style={{
        padding: '8px 10px',
        marginBottom: 6,
        background: T.surface1,
        border: `1px solid ${T.border}`,
        borderRadius: 6,
        cursor: 'pointer',
        transition: 'all 0.15s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = `${accent}60`
        e.currentTarget.style.background = T.surface2
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = T.border
        e.currentTarget.style.background = T.surface1
      }}
      onClick={onAdd}
    >
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4,
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          width: 22, height: 22, borderRadius: 4,
          background: `${accent}15`, border: `1px solid ${accent}30`,
          flexShrink: 0,
        }}>
          <IconComp size={11} color={accent} />
        </div>
        <div style={{
          fontFamily: F, fontSize: FS.sm, color: T.text,
          fontWeight: 600, flex: 1, overflow: 'hidden',
          textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {rec.block.name}
        </div>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          gap: 2,
          height: 18, borderRadius: 4,
          padding: hasAutoWire ? '0 6px' : undefined,
          width: hasAutoWire ? 'auto' : 18,
          background: hasAutoWire ? `${T.green}15` : `${accent}10`,
          border: hasAutoWire ? `1px solid ${T.green}30` : 'none',
          flexShrink: 0,
        }}>
          {hasAutoWire ? (
            <>
              <Zap size={8} color={T.green} />
              <span style={{ fontFamily: F, fontSize: '7px', color: T.green, fontWeight: 700, letterSpacing: '0.04em' }}>
                ADD
              </span>
            </>
          ) : (
            <Plus size={10} color={accent} />
          )}
        </div>
      </div>

      {/* Reason tag */}
      <div style={{
        fontFamily: F, fontSize: '8px', color: T.dim,
        lineHeight: 1.4, marginLeft: 30,
      }}>
        {hasAutoWire ? (
          <>
            <Zap size={7} color={T.green} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 3 }} />
            <span style={{ color: T.green }}>Auto-connects</span>
            {' · '}
          </>
        ) : null}
        {rec.reason}
      </div>
    </div>
  )
}

export default function RecommendedBlocks() {
  const { nodes, edges, addNode, addNodeAndConnect } = usePipelineStore(useShallow((s) => ({
    nodes: s.nodes, edges: s.edges, addNode: s.addNode, addNodeAndConnect: s.addNodeAndConnect,
  })))

  const { inputBlocks, outputBlocks } = useMemo<SplitRecommendations>(() => {
    if (nodes.length === 0) {
      return { inputBlocks: getEmptyPipelineRecommendations(), outputBlocks: [] }
    }
    return computeRecommendations(nodes, edges)
  }, [nodes, edges])

  const handleAdd = (rec: Recommendation) => {
    if (rec.connectTo) {
      addNodeAndConnect(rec.block.type, rec.connectTo)
    } else {
      const lastNode = nodes[nodes.length - 1]
      const x = lastNode ? (lastNode.position?.x ?? 200) + 50 : 200
      const y = lastNode ? (lastNode.position?.y ?? 200) + 280 : 200
      addNode(rec.block.type, { x, y })
    }
  }

  const hasAny = inputBlocks.length > 0 || outputBlocks.length > 0

  return (
    <div
      style={{
        width: 280,
        minWidth: 280,
        borderLeft: `1px solid ${T.border}`,
        display: 'flex',
        flexDirection: 'column',
        background: T.surface0,
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '10px 12px',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          borderBottom: `1px solid ${T.border}`,
          background: `linear-gradient(180deg, ${T.surface2} 0%, ${T.surface1} 100%)`,
        }}
      >
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          width: 22, height: 22, borderRadius: 4,
          background: `${T.amber}15`, border: `1px solid ${T.amber}30`,
        }}>
          <Lightbulb size={11} color={T.amber} />
        </div>
        <div>
          <div style={{
            fontFamily: F, fontSize: FS.xs, color: T.text,
            fontWeight: 700, letterSpacing: '0.06em',
          }}>
            RECOMMENDED
          </div>
          <div style={{
            fontFamily: F, fontSize: '7px', color: T.dim,
            letterSpacing: '0.04em',
          }}>
            Click to add &amp; auto-connect
          </div>
        </div>
      </div>

      {/* Recommendations list */}
      <div style={{ flex: 1, overflow: 'auto', padding: '8px 8px' }}>
        {!hasAny ? (
          <div style={{
            padding: '24px 12px', textAlign: 'center',
            fontFamily: F, fontSize: FS.xs, color: T.dim,
          }}>
            <Sparkles size={20} color={T.dim} style={{ marginBottom: 8 }} />
            <div>Add blocks to get recommendations</div>
          </div>
        ) : (
          <>
            {inputBlocks.length > 0 && (
              <>
                <SectionHeader icon={ArrowDownToLine} label="INPUT BLOCKS" accent={T.green} />
                {inputBlocks.map((rec, idx) => (
                  <RecommendationCard
                    key={`in-${rec.block.type}-${idx}`}
                    rec={rec}
                    onAdd={() => handleAdd(rec)}
                  />
                ))}
              </>
            )}
            {outputBlocks.length > 0 && (
              <>
                <SectionHeader icon={ArrowUpFromLine} label="OUTPUT BLOCKS" accent={T.cyan} />
                {outputBlocks.map((rec, idx) => (
                  <RecommendationCard
                    key={`out-${rec.block.type}-${idx}`}
                    rec={rec}
                    onAdd={() => handleAdd(rec)}
                  />
                ))}
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ── Recommendation engine ──

function getEmptyPipelineRecommendations(): Recommendation[] {
  const starters = ['text_input', 'huggingface_loader', 'local_file_loader', 'model_selector', 'metrics_input', 'config_builder']
  return starters
    .map((type) => {
      const block = BLOCK_REGISTRY.find((b) => b.type === type)
      if (!block) return null
      return {
        block,
        reason: 'Good starting point for your pipeline',
        score: 10,
      } as Recommendation
    })
    .filter(Boolean) as Recommendation[]
}

export function computeRecommendations(
  nodes: any[],
  edges: any[],
): SplitRecommendations {
  const inputRecs: Recommendation[] = []
  const outputRecs: Recommendation[] = []
  const existingTypes = new Set(nodes.map((n) => n.data?.type).filter(Boolean))

  // ── 1. Find unconnected output ports → suggest downstream blocks ──
  const connectedSources = new Set(
    edges.map((e) => `${e.source}:${e.sourceHandle}`)
  )

  const openOutputs: { nodeId: string; nodeType: string; portId: string; portType: string; portLabel: string; portNames: Set<string> }[] = []
  for (const node of nodes) {
    const def = BLOCK_REGISTRY.find((b) => b.type === node.data?.type)
    if (!def) continue
    for (const out of def.outputs) {
      const key = `${node.id}:${out.id}`
      if (!connectedSources.has(key)) {
        openOutputs.push({
          nodeId: node.id,
          nodeType: def.type,
          portId: out.id,
          portType: out.dataType,
          portLabel: out.label,
          portNames: new Set(getPortNames(out)),
        })
      }
    }
  }

  for (const open of openOutputs) {
    for (const candidate of BLOCK_REGISTRY) {
      if (existingTypes.has(candidate.type)) continue
      if (candidate.deprecated) continue
      const hasCompatibleInput = candidate.inputs.some((inp) =>
        isPortCompatible(open.portType, inp.dataType)
      )
      if (hasCompatibleInput) {
        // Bonus: port alias overlap means a stronger semantic match
        const aliasBonus = candidate.inputs.some((inp) =>
          getPortNames(inp).some((n) => open.portNames.has(n))
        ) ? 2 : 0
        const existing = outputRecs.find((r) => r.block.type === candidate.type)
        if (existing) {
          existing.score += 1 + aliasBonus
        } else {
          outputRecs.push({
            block: candidate,
            reason: `Connects to open "${open.portLabel}" output`,
            score: 3 + aliasBonus,
            connectTo: {
              nodeId: open.nodeId,
              portId: open.portId,
              direction: 'downstream',
            },
          })
        }
      }
    }
  }

  // ── 2. Find unconnected required input ports → suggest upstream blocks ──
  const connectedTargets = new Set(
    edges.map((e) => `${e.target}:${e.targetHandle}`)
  )

  const openInputs: { nodeId: string; nodeType: string; portId: string; portType: string; portLabel: string; portNames: Set<string> }[] = []
  for (const node of nodes) {
    const def = BLOCK_REGISTRY.find((b) => b.type === node.data?.type)
    if (!def) continue
    for (const inp of def.inputs) {
      if (!inp.required) continue
      const key = `${node.id}:${inp.id}`
      if (!connectedTargets.has(key)) {
        openInputs.push({
          nodeId: node.id,
          nodeType: def.type,
          portId: inp.id,
          portType: inp.dataType,
          portLabel: inp.label,
          portNames: new Set(getPortNames(inp)),
        })
      }
    }
  }

  for (const open of openInputs) {
    for (const candidate of BLOCK_REGISTRY) {
      if (existingTypes.has(candidate.type)) continue
      if (candidate.deprecated) continue
      const hasCompatibleOutput = candidate.outputs.some((out) =>
        isPortCompatible(out.dataType, open.portType)
      )
      if (hasCompatibleOutput) {
        // Bonus: port alias overlap means a stronger semantic match
        const aliasBonus = candidate.outputs.some((out) =>
          getPortNames(out).some((n) => open.portNames.has(n))
        ) ? 2 : 0
        const existing = inputRecs.find((r) => r.block.type === candidate.type)
        if (existing) {
          existing.score += 1 + aliasBonus
        } else {
          inputRecs.push({
            block: candidate,
            reason: `Provides "${open.portLabel}" input`,
            score: 4 + aliasBonus,
            connectTo: {
              nodeId: open.nodeId,
              portId: open.portId,
              direction: 'upstream',
            },
          })
        }
      }
    }
  }

  // ── 3. Pattern-based recommendations ──
  const categories = new Set(nodes.map((n) => n.data?.category).filter(Boolean))
  const types = existingTypes

  // For pattern-based recs, try to find a connection point
  const findConnectionForBlock = (block: BlockDefinition): Recommendation['connectTo'] => {
    // Check if any open output can connect to this block's inputs
    for (const open of openOutputs) {
      const match = block.inputs.some((inp) => isPortCompatible(open.portType, inp.dataType))
      if (match) return { nodeId: open.nodeId, portId: open.portId, direction: 'downstream' }
    }
    // Check if this block's outputs can connect to any open input
    for (const open of openInputs) {
      const match = block.outputs.some((out) => isPortCompatible(out.dataType, open.portType))
      if (match) return { nodeId: open.nodeId, portId: open.portId, direction: 'upstream' }
    }
    return undefined
  }

  // Has training but no evaluation
  if (categories.has('training') && !categories.has('evaluation')) {
    const evalBlocks = BLOCK_REGISTRY.filter((b) => b.category === 'evaluation' && !types.has(b.type))
    for (const eb of evalBlocks.slice(0, 2)) {
      const existing = outputRecs.find((r) => r.block.type === eb.type)
      if (existing) {
        existing.score += 5
        existing.reason = 'Evaluate your trained model'
      } else {
        outputRecs.push({ block: eb, reason: 'Evaluate your trained model', score: 5, connectTo: findConnectionForBlock(eb) })
      }
    }
  }

  // Has data source but no transform
  if (categories.has('source') && !categories.has('data')) {
    const transformBlocks = ['filter_sample', 'train_val_test_split', 'data_preview']
    for (const tbType of transformBlocks) {
      if (types.has(tbType)) continue
      const block = BLOCK_REGISTRY.find((b) => b.type === tbType)
      if (block) {
        const existing = outputRecs.find((r) => r.block.type === block.type)
        if (existing) {
          existing.score += 4
        } else {
          outputRecs.push({ block, reason: 'Process your data before training', score: 4, connectTo: findConnectionForBlock(block) })
        }
      }
    }
  }

  // Has model output but no export/save
  if (types.has('llm_inference') || categories.has('training') || categories.has('merge')) {
    const exportBlocks = ['experiment_logger', 'report_generator', 'save_model']
    for (const ebType of exportBlocks) {
      if (types.has(ebType)) continue
      const block = BLOCK_REGISTRY.find((b) => b.type === ebType)
      if (block) {
        const existing = outputRecs.find((r) => r.block.type === block.type)
        if (existing) {
          existing.score += 3
        } else {
          outputRecs.push({ block, reason: 'Save and export your results', score: 3, connectTo: findConnectionForBlock(block) })
        }
      }
    }
  }

  // No model selector but has training/inference
  if ((categories.has('training') || categories.has('inference')) && !types.has('model_selector')) {
    const block = BLOCK_REGISTRY.find((b) => b.type === 'model_selector')
    if (block) {
      inputRecs.push({ block, reason: 'Select a base model for your pipeline', score: 6, connectTo: findConnectionForBlock(block) })
    }
  }

  // No text_input but has inference blocks needing text
  if (categories.has('inference') && !types.has('text_input')) {
    const needsText = nodes.some((n) => {
      const def = BLOCK_REGISTRY.find((b) => b.type === n.data?.type)
      return def?.inputs.some((inp) => inp.dataType === 'text' && inp.required)
    })
    if (needsText) {
      const block = BLOCK_REGISTRY.find((b) => b.type === 'text_input')
      if (block) {
        inputRecs.push({ block, reason: 'Provide text input for inference', score: 5, connectTo: findConnectionForBlock(block) })
      }
    }
  }

  // Has blocks but no human review gate
  if (nodes.length >= 3 && !types.has('human_review_gate')) {
    const block = BLOCK_REGISTRY.find((b) => b.type === 'human_review_gate')
    if (block) {
      outputRecs.push({ block, reason: 'Add a review checkpoint', score: 2, connectTo: findConnectionForBlock(block) })
    }
  }

  // Sort by score descending, limit each section to 5
  inputRecs.sort((a, b) => b.score - a.score)
  outputRecs.sort((a, b) => b.score - a.score)
  return {
    inputBlocks: inputRecs.slice(0, 5),
    outputBlocks: outputRecs.slice(0, 5),
  }
}
