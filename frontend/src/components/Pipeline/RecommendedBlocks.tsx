import { useMemo } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { T, F, FS } from '@/lib/design-tokens'
import { BLOCK_REGISTRY, type BlockDefinition, isPortCompatible, getPortNames } from '@/lib/block-registry'
import { usePipelineStore } from '@/stores/pipelineStore'
import { getIcon } from '@/lib/icon-utils'
import { Sparkles, Plus, Lightbulb, ArrowDownToLine, ArrowUpFromLine } from 'lucide-react'

/**
 * RecommendedBlocks — persistent right-side panel that analyzes the current
 * pipeline and suggests blocks the user might want to add next.
 *
 * Recommendation logic:
 * 1. Find all unconnected output ports → suggest compatible downstream blocks
 * 2. Find all unconnected required input ports → suggest compatible upstream blocks
 * 3. Detect missing pipeline patterns (e.g., training without evaluation)
 * 4. Prioritize by relevance score
 * 5. Display in two sections: Input Blocks (producers) and Output Blocks (consumers)
 */

interface Recommendation {
  block: BlockDefinition
  reason: string
  score: number
}

interface SplitRecommendations {
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
          width: 18, height: 18, borderRadius: 4,
          background: `${accent}10`, flexShrink: 0,
        }}>
          <Plus size={10} color={accent} />
        </div>
      </div>

      {/* Reason tag */}
      <div style={{
        fontFamily: F, fontSize: '8px', color: T.dim,
        lineHeight: 1.4, marginLeft: 30,
      }}>
        {rec.reason}
      </div>
    </div>
  )
}

export default function RecommendedBlocks() {
  const { nodes, edges, addNode } = usePipelineStore(useShallow((s) => ({
    nodes: s.nodes, edges: s.edges, addNode: s.addNode,
  })))

  const { inputBlocks, outputBlocks } = useMemo<SplitRecommendations>(() => {
    if (nodes.length === 0) {
      return { inputBlocks: getEmptyPipelineRecommendations(), outputBlocks: [] }
    }
    return computeRecommendations(nodes, edges)
  }, [nodes, edges])

  const handleAdd = (blockType: string) => {
    const lastNode = nodes[nodes.length - 1]
    const x = lastNode ? (lastNode.position?.x ?? 200) + 50 : 200
    const y = lastNode ? (lastNode.position?.y ?? 200) + 280 : 200
    addNode(blockType, { x, y })
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
            Based on your pipeline
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
                    onAdd={() => handleAdd(rec.block.type)}
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
                    onAdd={() => handleAdd(rec.block.type)}
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

function computeRecommendations(
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

  const openOutputs: { nodeType: string; portType: string; portLabel: string; portNames: Set<string> }[] = []
  for (const node of nodes) {
    const def = BLOCK_REGISTRY.find((b) => b.type === node.data?.type)
    if (!def) continue
    for (const out of def.outputs) {
      const key = `${node.id}:${out.id}`
      if (!connectedSources.has(key)) {
        openOutputs.push({
          nodeType: def.type,
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
          })
        }
      }
    }
  }

  // ── 2. Find unconnected required input ports → suggest upstream blocks ──
  const connectedTargets = new Set(
    edges.map((e) => `${e.target}:${e.targetHandle}`)
  )

  const openInputs: { nodeType: string; portType: string; portLabel: string; portNames: Set<string> }[] = []
  for (const node of nodes) {
    const def = BLOCK_REGISTRY.find((b) => b.type === node.data?.type)
    if (!def) continue
    for (const inp of def.inputs) {
      if (!inp.required) continue
      const key = `${node.id}:${inp.id}`
      if (!connectedTargets.has(key)) {
        openInputs.push({
          nodeType: def.type,
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
          })
        }
      }
    }
  }

  // ── 3. Pattern-based recommendations ──
  const categories = new Set(nodes.map((n) => n.data?.category).filter(Boolean))
  const types = existingTypes

  // Has training but no evaluation
  if (categories.has('training') && !categories.has('evaluation')) {
    const evalBlocks = BLOCK_REGISTRY.filter((b) => b.category === 'evaluation' && !types.has(b.type))
    for (const eb of evalBlocks.slice(0, 2)) {
      const existing = outputRecs.find((r) => r.block.type === eb.type)
      if (existing) {
        existing.score += 5
        existing.reason = 'Evaluate your trained model'
      } else {
        outputRecs.push({ block: eb, reason: 'Evaluate your trained model', score: 5 })
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
          outputRecs.push({ block, reason: 'Process your data before training', score: 4 })
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
          outputRecs.push({ block, reason: 'Save and export your results', score: 3 })
        }
      }
    }
  }

  // No model selector but has training/inference
  if ((categories.has('training') || categories.has('inference')) && !types.has('model_selector')) {
    const block = BLOCK_REGISTRY.find((b) => b.type === 'model_selector')
    if (block) {
      inputRecs.push({ block, reason: 'Select a base model for your pipeline', score: 6 })
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
        inputRecs.push({ block, reason: 'Provide text input for inference', score: 5 })
      }
    }
  }

  // Has blocks but no human review gate
  if (nodes.length >= 3 && !types.has('human_review_gate')) {
    const block = BLOCK_REGISTRY.find((b) => b.type === 'human_review_gate')
    if (block) {
      outputRecs.push({ block, reason: 'Add a review checkpoint', score: 2 })
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
