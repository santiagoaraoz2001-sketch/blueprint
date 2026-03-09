import { useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { BLOCK_REGISTRY, type BlockDefinition, isPortCompatible } from '@/lib/block-registry'
import { usePipelineStore } from '@/stores/pipelineStore'
import { getIcon } from '@/lib/icon-utils'
import { Sparkles, Plus, Lightbulb } from 'lucide-react'

/**
 * RecommendedBlocks — persistent right-side panel that analyzes the current
 * pipeline and suggests blocks the user might want to add next.
 *
 * Recommendation logic:
 * 1. Find all unconnected output ports in the pipeline
 * 2. Suggest blocks whose inputs are compatible with those outputs
 * 3. Detect missing pipeline patterns (e.g., training without evaluation)
 * 4. Prioritize by relevance score
 */

interface Recommendation {
  block: BlockDefinition
  reason: string
  score: number
}

export default function RecommendedBlocks() {
  const { nodes, edges, addNode } = usePipelineStore()

  const recommendations = useMemo(() => {
    if (nodes.length === 0) return getEmptyPipelineRecommendations()
    return computeRecommendations(nodes, edges)
  }, [nodes, edges])

  const handleAdd = (blockType: string) => {
    // Place new block below-right of the last node
    const lastNode = nodes[nodes.length - 1]
    const x = lastNode ? (lastNode.position?.x ?? 200) + 50 : 200
    const y = lastNode ? (lastNode.position?.y ?? 200) + 280 : 200
    addNode(blockType, { x, y })
  }

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
        {recommendations.length === 0 ? (
          <div style={{
            padding: '24px 12px', textAlign: 'center',
            fontFamily: F, fontSize: FS.xs, color: T.dim,
          }}>
            <Sparkles size={20} color={T.dim} style={{ marginBottom: 8 }} />
            <div>Add blocks to get recommendations</div>
          </div>
        ) : (
          recommendations.map((rec, idx) => {
            const IconComp = getIcon(rec.block.icon)
            const accent = rec.block.accent || T.cyan
            return (
              <div
                key={`${rec.block.type}-${idx}`}
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
                onClick={() => handleAdd(rec.block.type)}
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
          })
        )}
      </div>
    </div>
  )
}

// ── Recommendation engine ──

function getEmptyPipelineRecommendations(): Recommendation[] {
  // Suggest starter blocks for an empty pipeline
  const starters = ['text_input', 'huggingface_loader', 'local_file_loader', 'model_selector']
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
): Recommendation[] {
  const recommendations: Recommendation[] = []
  const existingTypes = new Set(nodes.map((n) => n.data?.type).filter(Boolean))

  // 1. Find unconnected output ports
  const connectedSources = new Set(
    edges.map((e) => `${e.source}:${e.sourceHandle}`)
  )

  const openOutputs: { nodeType: string; portType: string; portLabel: string }[] = []
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
        })
      }
    }
  }

  // 2. Suggest blocks compatible with open output ports
  for (const open of openOutputs) {
    for (const candidate of BLOCK_REGISTRY) {
      if (existingTypes.has(candidate.type)) continue
      const hasCompatibleInput = candidate.inputs.some((inp) =>
        isPortCompatible(open.portType, inp.dataType)
      )
      if (hasCompatibleInput) {
        const existing = recommendations.find((r) => r.block.type === candidate.type)
        if (existing) {
          existing.score += 1
        } else {
          recommendations.push({
            block: candidate,
            reason: `Connects to open "${open.portLabel}" output`,
            score: 3,
          })
        }
      }
    }
  }

  // 3. Pattern-based recommendations
  const categories = new Set(nodes.map((n) => n.data?.category).filter(Boolean))
  const types = existingTypes

  // Has training but no evaluation
  if (categories.has('training') && !categories.has('evaluate')) {
    const evalBlocks = BLOCK_REGISTRY.filter((b) => b.category === 'evaluate' && !types.has(b.type))
    for (const eb of evalBlocks.slice(0, 2)) {
      const existing = recommendations.find((r) => r.block.type === eb.type)
      if (existing) {
        existing.score += 5
        existing.reason = 'Evaluate your trained model'
      } else {
        recommendations.push({ block: eb, reason: 'Evaluate your trained model', score: 5 })
      }
    }
  }

  // Has data source but no transform
  if (categories.has('source') && !categories.has('transform')) {
    const transformBlocks = ['filter_sample', 'train_val_test_split', 'data_preview']
    for (const tbType of transformBlocks) {
      if (types.has(tbType)) continue
      const block = BLOCK_REGISTRY.find((b) => b.type === tbType)
      if (block) {
        const existing = recommendations.find((r) => r.block.type === block.type)
        if (existing) {
          existing.score += 4
        } else {
          recommendations.push({ block, reason: 'Process your data before training', score: 4 })
        }
      }
    }
  }

  // Has model output but no export/save
  if (types.has('llm_inference') || categories.has('training') || categories.has('merge')) {
    const exportBlocks = ['results_exporter', 'experiment_logger', 'report_generator']
    for (const ebType of exportBlocks) {
      if (types.has(ebType)) continue
      const block = BLOCK_REGISTRY.find((b) => b.type === ebType)
      if (block) {
        const existing = recommendations.find((r) => r.block.type === block.type)
        if (existing) {
          existing.score += 3
        } else {
          recommendations.push({ block, reason: 'Save and export your results', score: 3 })
        }
      }
    }
  }

  // No model selector but has training/inference
  if ((categories.has('training') || categories.has('inference')) && !types.has('model_selector')) {
    const block = BLOCK_REGISTRY.find((b) => b.type === 'model_selector')
    if (block) {
      recommendations.push({ block, reason: 'Select a base model for your pipeline', score: 6 })
    }
  }

  // Has blocks but no human review gate
  if (nodes.length >= 3 && !types.has('human_review_gate')) {
    const block = BLOCK_REGISTRY.find((b) => b.type === 'human_review_gate')
    if (block) {
      recommendations.push({ block, reason: 'Add a review checkpoint', score: 2 })
    }
  }

  // Sort by score descending, limit to 8
  recommendations.sort((a, b) => b.score - a.score)
  return recommendations.slice(0, 8)
}
