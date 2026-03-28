/**
 * Client-side Copilot Rule Engine — zero-latency pipeline linting.
 *
 * TypeScript port of backend/services/copilot_rules.py.
 * Runs entirely in the browser with no network calls.
 * Uses the frontend block registry for schema lookups.
 * Uses the generated model catalog for OOM/context predictions.
 */

import { getBlockDefinition, type BlockDefinition } from '@/lib/block-registry'
import { lookupModel, type ModelInfo } from '@/lib/generated/model-catalog.generated'
import type { Node, Edge } from '@xyflow/react'

// ── Types ─────────────────────────────────────────────────────────

export interface CopilotAlert {
  id: string
  severity: 'info' | 'warning' | 'error'
  title: string
  message: string
  affected_node_id: string | null
  suggested_action: string | null
  auto_dismissible: boolean
}

interface Capabilities {
  available_memory_gb?: number
}

// ── Classification Sets ───────────────────────────────────────────

const TRAINING_CATEGORIES = new Set(['training'])
const TRAINING_TYPES = new Set([
  'fine_tune', 'lora_fine_tune', 'qlora_fine_tune', 'full_fine_tune',
  'train', 'trainer', 'sft_trainer', 'dpo_trainer', 'reward_model_trainer',
])
const EVALUATION_CATEGORIES = new Set(['metrics'])
const EVALUATION_TYPES = new Set([
  'evaluate', 'evaluator', 'benchmark', 'perplexity', 'bleu_score',
  'rouge_score', 'human_eval', 'mmlu', 'lm_eval',
])
const INFERENCE_CATEGORIES = new Set(['inference', 'endpoints'])
const INFERENCE_TYPES = new Set([
  'inference', 'text_generation', 'chat_completion', 'generate',
  'serve', 'deploy',
])
const OUTPUT_TYPES = new Set([
  'save_model', 'export', 'push_to_hub', 'save_dataset',
  'write_file', 'artifact_export',
])
const VISUAL_NODE_TYPES = new Set(['groupNode', 'stickyNote'])

// ── Variant Field Highlighting ────────────────────────────────────

const VARIANT_FIELD_HINTS: Record<string, string[]> = {
  training: ['model_name', 'learning_rate', 'lr', 'epochs', 'num_train_epochs', 'batch_size', 'per_device_train_batch_size'],
  inference: ['model_name', 'model', 'temperature', 'max_tokens', 'max_new_tokens', 'top_p'],
  evaluation: ['model_name', 'model', 'benchmark', 'dataset', 'num_samples'],
}

// ── Node Helpers ──────────────────────────────────────────────────

function getNodeData(node: Node): any {
  return (node as any).data ?? {}
}

function getNodeType(node: Node): string {
  return getNodeData(node).type ?? ''
}

function getNodeLabel(node: Node): string {
  return getNodeData(node).label ?? node.id
}

function getNodeConfig(node: Node): Record<string, any> {
  return getNodeData(node).config ?? {}
}

function getBlockDef(node: Node): BlockDefinition | undefined {
  const bt = getNodeType(node)
  return bt ? getBlockDefinition(bt) : undefined
}

function getCategory(node: Node): string {
  return getBlockDef(node)?.category ?? ''
}

function isTraining(node: Node): boolean {
  return TRAINING_CATEGORIES.has(getCategory(node)) || TRAINING_TYPES.has(getNodeType(node))
}

function isEvaluation(node: Node): boolean {
  return EVALUATION_CATEGORIES.has(getCategory(node)) || EVALUATION_TYPES.has(getNodeType(node))
}

function isInference(node: Node): boolean {
  return INFERENCE_CATEGORIES.has(getCategory(node)) || INFERENCE_TYPES.has(getNodeType(node))
}

function isOutput(node: Node): boolean {
  return OUTPUT_TYPES.has(getNodeType(node))
}

function isBlockNode(node: Node): boolean {
  return !VISUAL_NODE_TYPES.has(node.type ?? '') && !!getNodeType(node)
}

// ── Model Lookup ──────────────────────────────────────────────────

function lookupModelFromConfig(config: Record<string, any>): ModelInfo | null {
  // Check explicit parameter count
  for (const key of ['model_params_b', 'num_parameters', 'param_count']) {
    const val = config[key]
    if (val != null) {
      let params = parseFloat(val)
      if (!isNaN(params) && params > 0) {
        if (params > 1000) params /= 1e9
        return { params_b: params, context: null, source: 'config' }
      }
    }
  }

  // Try model name lookup
  for (const key of ['model_name', 'model', 'base_model', 'pretrained_model_name_or_path', 'model_id']) {
    const name = config[key]
    if (name && typeof name === 'string') {
      const info = lookupModel(name)
      if (info) return info
    }
  }

  return null
}

function getContextFromConfig(config: Record<string, any>): number | null {
  // Explicit context keys
  for (const key of ['model_max_length', 'max_position_embeddings', 'context_length']) {
    const val = config[key]
    if (val != null) {
      const num = parseInt(val, 10)
      if (!isNaN(num)) return num
    }
  }
  // Fall back to catalog
  const info = lookupModelFromConfig(config)
  return info?.context ?? null
}

// ── Rule Implementations ──────────────────────────────────────────

function ruleOOMPrediction(nodes: Node[], caps: Capabilities): CopilotAlert[] {
  const availableGb = caps.available_memory_gb
  if (availableGb == null) return []

  const alerts: CopilotAlert[] = []
  const availableBytes = availableGb * 1024 ** 3

  for (const node of nodes) {
    if (!isTraining(node)) continue

    const config = getNodeConfig(node)
    const modelInfo = lookupModelFromConfig(config)
    if (!modelInfo) continue

    const paramsB = modelInfo.params_b
    const batchSize = parseInt(config.batch_size ?? config.per_device_train_batch_size ?? '1', 10) || 1
    const gradAccum = parseInt(config.gradient_accumulation_steps ?? '1', 10) || 1
    const bytesPerParam = (config.dtype === 'float32') ? 4 : 2

    const overheadFactor = 3 // Adam optimizer
    const estimatedBytes =
      paramsB * 1e9 * bytesPerParam * overheadFactor +
      paramsB * 1e9 * bytesPerParam * batchSize * 0.1

    const estimatedGb = estimatedBytes / 1024 ** 3

    if (estimatedBytes > availableBytes) {
      alerts.push({
        id: `oom-${node.id}`,
        severity: 'error',
        title: 'Predicted Out of Memory',
        message:
          `Training '${getNodeLabel(node)}' with ${paramsB.toFixed(1)}B params, ` +
          `batch_size=${batchSize}, grad_accum=${gradAccum} is estimated to need ` +
          `~${estimatedGb.toFixed(1)} GB, but only ${availableGb.toFixed(1)} GB is available.`,
        affected_node_id: node.id,
        suggested_action:
          'Reduce batch_size, enable gradient checkpointing, use LoRA/QLoRA, or switch to a smaller model.',
        auto_dismissible: false,
      })
    }
  }

  return alerts
}

function ruleMissingEvaluation(nodes: Node[], edges: Edge[]): CopilotAlert[] {
  const trainingNodes = nodes.filter(isTraining)
  if (!trainingNodes.length) return []

  // Quick check: any eval node at all?
  if (nodes.some(isEvaluation)) return []

  // BFS from training nodes to find downstream eval
  const trainingIds = new Set(trainingNodes.map((n) => n.id))
  const downstream = new Map<string, Set<string>>()
  for (const edge of edges) {
    if (!downstream.has(edge.source)) downstream.set(edge.source, new Set())
    downstream.get(edge.source)!.add(edge.target)
  }

  const visited = new Set<string>()
  const queue = [...trainingIds]
  while (queue.length) {
    const current = queue.shift()!
    if (visited.has(current)) continue
    visited.add(current)
    for (const child of downstream.get(current) ?? []) {
      queue.push(child)
    }
  }

  const nodeMap = new Map(nodes.map((n) => [n.id, n]))
  for (const nid of visited) {
    if (trainingIds.has(nid)) continue
    const node = nodeMap.get(nid)
    if (node && isEvaluation(node)) return []
  }

  return [{
    id: 'missing-eval',
    severity: 'warning',
    title: 'No Evaluation After Training',
    message:
      'This pipeline has training blocks but no evaluation block. ' +
      'Add an evaluation step to measure model quality.',
    affected_node_id: trainingNodes[0].id,
    suggested_action: 'Add a benchmark or evaluation block after training.',
    auto_dismissible: true,
  }]
}

function ruleDisconnectedRequiredPort(nodes: Node[], edges: Edge[]): CopilotAlert[] {
  const connected = new Set<string>()
  for (const edge of edges) {
    if (edge.target && edge.targetHandle) {
      connected.add(`${edge.target}:${edge.targetHandle}`)
    }
  }

  const alerts: CopilotAlert[] = []
  for (const node of nodes) {
    const def = getBlockDef(node)
    if (!def) continue

    for (const inp of def.inputs) {
      if (inp.required && !connected.has(`${node.id}:${inp.id}`)) {
        alerts.push({
          id: `disconnected-${node.id}-${inp.id}`,
          severity: 'error',
          title: 'Required Port Not Connected',
          message: `Required input '${inp.id}' on '${getNodeLabel(node)}' is not connected.`,
          affected_node_id: node.id,
          suggested_action: `Connect a compatible block to the '${inp.id}' input.`,
          auto_dismissible: false,
        })
      }
    }
  }

  return alerts
}

function ruleConfigRange(nodes: Node[]): CopilotAlert[] {
  const alerts: CopilotAlert[] = []
  for (const node of nodes) {
    const config = getNodeConfig(node)
    const lr = config.learning_rate ?? config.lr
    if (lr != null) {
      const lrVal = parseFloat(lr)
      if (!isNaN(lrVal) && lrVal > 0.01) {
        alerts.push({
          id: `high-lr-${node.id}`,
          severity: 'warning',
          title: 'High Learning Rate',
          message:
            `Learning rate ${lrVal} on '${getNodeLabel(node)}' ` +
            'is unusually high (>0.01). This may cause training instability.',
          affected_node_id: node.id,
          suggested_action: 'Try a learning rate between 1e-5 and 1e-3.',
          auto_dismissible: true,
        })
      }
    }
  }
  return alerts
}

function ruleIncompatibleBlockVersion(nodes: Node[]): CopilotAlert[] {
  const alerts: CopilotAlert[] = []
  for (const node of nodes) {
    const def = getBlockDef(node)
    if (!def) continue

    const nodeVersion = getNodeData(node).version
    const registryVersion = def.version

    if (nodeVersion && registryVersion && nodeVersion !== registryVersion) {
      const nodeMajor = parseInt(String(nodeVersion).split('.')[0], 10)
      const regMajor = parseInt(String(registryVersion).split('.')[0], 10)
      if (!isNaN(nodeMajor) && !isNaN(regMajor) && nodeMajor !== regMajor) {
        alerts.push({
          id: `version-${node.id}`,
          severity: 'warning',
          title: 'Block Version Mismatch',
          message:
            `'${getNodeLabel(node)}' uses version ${nodeVersion} ` +
            `but the installed version is ${registryVersion}.`,
          affected_node_id: node.id,
          suggested_action: 'Update the block or check for breaking changes.',
          auto_dismissible: true,
        })
      }
    }
  }
  return alerts
}

function ruleMissingDependency(nodes: Node[]): CopilotAlert[] {
  const alerts: CopilotAlert[] = []
  for (const node of nodes) {
    const blockType = getNodeType(node)
    if (!blockType) continue
    const def = getBlockDefinition(blockType)
    if (def) continue

    alerts.push({
      id: `missing-dep-${node.id}`,
      severity: 'error',
      title: 'Missing Block Type',
      message:
        `Block type '${blockType}' on '${getNodeLabel(node)}' ` +
        'is not in the registry. The block may not be installed.',
      affected_node_id: node.id,
      suggested_action: 'Install the block: check the marketplace or add it to blocks/.',
      auto_dismissible: false,
    })
  }
  return alerts
}

function ruleNoOutputBlock(nodes: Node[]): CopilotAlert[] {
  if (!nodes.length) return []
  if (nodes.some(isOutput)) return []

  return [{
    id: 'no-output',
    severity: 'info',
    title: 'No Output Block',
    message:
      'This pipeline has no explicit output block (save, export, push). ' +
      'Results will only be available in the run artifacts.',
    affected_node_id: null,
    suggested_action: 'Add a save or export block to persist results.',
    auto_dismissible: true,
  }]
}

function ruleLargeContext(nodes: Node[]): CopilotAlert[] {
  const alerts: CopilotAlert[] = []
  for (const node of nodes) {
    const config = getNodeConfig(node)
    const maxTokensRaw = config.max_tokens ?? config.max_new_tokens
    if (maxTokensRaw == null) continue

    const maxTok = parseInt(maxTokensRaw, 10)
    if (isNaN(maxTok)) continue

    const modelCtx = getContextFromConfig(config)
    if (modelCtx && maxTok > modelCtx) {
      alerts.push({
        id: `large-ctx-${node.id}`,
        severity: 'warning',
        title: 'Exceeds Model Context Window',
        message:
          `max_tokens=${maxTok} on '${getNodeLabel(node)}' ` +
          `exceeds the model's context window of ${modelCtx} tokens.`,
        affected_node_id: node.id,
        suggested_action: `Reduce max_tokens to ${modelCtx} or use a model with a larger context.`,
        auto_dismissible: true,
      })
    }
  }
  return alerts
}

// ── Public API ────────────────────────────────────────────────────

const SEVERITY_ORDER: Record<string, number> = { error: 0, warning: 1, info: 2 }

/**
 * Evaluate all copilot rules client-side. Zero network calls.
 * Semantically identical to backend RuleEngine.evaluate().
 */
export function evaluateRules(
  nodes: Node[],
  edges: Edge[],
  capabilities?: Capabilities,
): CopilotAlert[] {
  const caps = capabilities ?? {}
  const blockNodes = nodes.filter(isBlockNode)

  const alerts: CopilotAlert[] = [
    ...ruleOOMPrediction(blockNodes, caps),
    ...ruleMissingEvaluation(blockNodes, edges),
    ...ruleDisconnectedRequiredPort(blockNodes, edges),
    ...ruleConfigRange(blockNodes),
    ...ruleIncompatibleBlockVersion(blockNodes),
    ...ruleMissingDependency(blockNodes),
    ...ruleNoOutputBlock(blockNodes),
    ...ruleLargeContext(blockNodes),
  ]

  alerts.sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 3) - (SEVERITY_ORDER[b.severity] ?? 3))
  return alerts
}

/**
 * Get variant field hints (rule-based, no AI).
 * Returns {nodeId: [fieldKey, ...]} for commonly varied fields.
 */
export function getVariantFieldHints(nodes: Node[]): Record<string, string[]> {
  const hints: Record<string, string[]> = {}

  for (const node of nodes) {
    if (VISUAL_NODE_TYPES.has(node.type ?? '')) continue
    const config = getNodeConfig(node)
    if (!Object.keys(config).length) continue

    let archetype: string | null = null
    if (isTraining(node)) archetype = 'training'
    else if (isInference(node)) archetype = 'inference'
    else if (isEvaluation(node)) archetype = 'evaluation'
    if (!archetype) continue

    const suggested = VARIANT_FIELD_HINTS[archetype] ?? []
    const present = suggested.filter((f) => f in config)
    if (present.length) hints[node.id] = present
  }

  return hints
}
