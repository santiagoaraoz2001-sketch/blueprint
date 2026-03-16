/**
 * Client-side pipeline validator — comprehensive diagnostic report.
 * Runs instantly without backend, checks structure, config, compatibility,
 * hardware feasibility, and performance.
 */

import type { Node, Edge } from '@xyflow/react'
import type { BlockNodeData } from '@/stores/pipelineStore'
import { getBlockDefinition, isPortCompatible, resolvePort, type ConfigField } from './block-registry'
import { estimatePipeline, formatTime, type HardwareSpec, type PipelineEstimate } from './pipeline-estimator'
import { useHardwareStore } from '@/stores/hardwareStore'

// ─── Types ─────────────────────────────────────────────────────────

export interface DiagnosticItem {
  message: string
  nodeId?: string
  severity: 'error' | 'warning' | 'info'
  category: 'structure' | 'config' | 'compatibility' | 'hardware' | 'performance'
  suggestion?: string
}

export interface ReportSection {
  title: string
  status: 'pass' | 'fail' | 'warn'
  items: DiagnosticItem[]
}

export interface DiagnosticReport {
  valid: boolean
  score: number
  errors: DiagnosticItem[]
  warnings: DiagnosticItem[]
  info: DiagnosticItem[]
  stats: {
    blockCount: number
    edgeCount: number
    estimatedRuntime: number
    peakMemoryGB: number
    gpuRequired: boolean
  }
  hardware: {
    feasible: boolean
    ramAvailableGB: number
    gpuVramGB: number
    gpuType: string
    infeasibleBlocks: string[]
    recommendations: string[]
  }
  sections: ReportSection[]
}

// ─── Helpers ───────────────────────────────────────────────────────

function getConnectedInputs(nodeId: string, edges: Edge[]): Set<string> {
  const inputs = new Set<string>()
  for (const e of edges) {
    if (e.target === nodeId && e.targetHandle) {
      inputs.add(e.targetHandle)
    }
  }
  return inputs
}

// function getConnectedOutputs(nodeId: string, edges: Edge[]): Set<string> {
//   const outputs = new Set<string>()
//   for (const e of edges) {
//     if (e.source === nodeId && e.sourceHandle) {
//       outputs.add(e.sourceHandle)
//     }
//   }
//   return outputs
// }

/** DFS cycle detection */
function hasCycle(nodes: Node[], edges: Edge[]): string[] | null {
  const adj = new Map<string, string[]>()
  for (const e of edges) {
    if (!adj.has(e.source)) adj.set(e.source, [])
    adj.get(e.source)!.push(e.target)
  }

  const visited = new Set<string>()
  const stack = new Set<string>()
  const path: string[] = []

  function dfs(node: string): boolean {
    visited.add(node)
    stack.add(node)
    path.push(node)

    for (const neighbor of adj.get(node) || []) {
      if (stack.has(neighbor)) {
        path.push(neighbor)
        return true
      }
      if (!visited.has(neighbor) && dfs(neighbor)) return true
    }

    stack.delete(node)
    path.pop()
    return false
  }

  for (const node of nodes) {
    if (!visited.has(node.id)) {
      if (dfs(node.id)) return path
    }
  }
  return null
}

// Critical config fields that must be non-empty for specific block types
const CRITICAL_CONFIG: Record<string, { field: string; label: string }[]> = {
  llm_inference: [{ field: 'model_name', label: 'Model Name' }],
  vision_inference: [{ field: 'model_name', label: 'Model Name' }],
  prompt_chain: [{ field: 'model_name', label: 'Model Name' }],
  model_router: [{ field: 'primary_model', label: 'Primary Model' }],
  ab_test_inference: [{ field: 'model_a', label: 'Model A' }, { field: 'model_b', label: 'Model B' }],
  local_file_loader: [{ field: 'file_path', label: 'File Path' }],
  huggingface_loader: [{ field: 'dataset_name', label: 'Dataset Name' }],
  huggingface_model_loader: [{ field: 'model_id', label: 'Model ID' }],
  model_selector: [{ field: 'model_id', label: 'Model ID' }],
  save_csv: [{ field: 'file_path', label: 'File Path' }],
  save_json: [{ field: 'file_path', label: 'File Path' }],
  save_txt: [{ field: 'file_path', label: 'File Path' }],
}

// ─── Config Field Validator ────────────────────────────────────────

/** Validate a single config value against its field schema. Returns error messages. */
function validateConfigField(field: ConfigField, value: unknown): string[] {
  const errors: string[] = []
  const label = field.label || field.name

  switch (field.type) {
    case 'integer': {
      const num = typeof value === 'string' ? parseInt(value, 10) : value
      if (typeof num !== 'number' || isNaN(num as number)) {
        errors.push(`"${label}" must be an integer, got "${value}"`)
        break
      }
      if (!Number.isInteger(num)) {
        errors.push(`"${label}" must be an integer, got float ${value}`)
        break
      }
      if (field.min !== undefined && (num as number) < field.min) {
        errors.push(`"${label}" value ${num} is below minimum ${field.min}`)
      }
      if (field.max !== undefined && (num as number) > field.max) {
        errors.push(`"${label}" value ${num} is above maximum ${field.max}`)
      }
      break
    }
    case 'float': {
      const num = typeof value === 'string' ? parseFloat(value as string) : value
      if (typeof num !== 'number' || isNaN(num as number)) {
        errors.push(`"${label}" must be a number, got "${value}"`)
        break
      }
      if (field.min !== undefined && (num as number) < field.min) {
        errors.push(`"${label}" value ${num} is below minimum ${field.min}`)
      }
      if (field.max !== undefined && (num as number) > field.max) {
        errors.push(`"${label}" value ${num} is above maximum ${field.max}`)
      }
      break
    }
    case 'boolean': {
      if (typeof value !== 'boolean') {
        const strVal = typeof value === 'string' ? value.toLowerCase() : ''
        if (strVal !== 'true' && strVal !== 'false') {
          errors.push(`"${label}" must be a boolean, got "${value}"`)
        }
      }
      break
    }
    case 'select': {
      if (field.options && field.options.length > 0) {
        const strValue = String(value)
        if (!field.options.includes(strValue)) {
          errors.push(`"${label}" value "${strValue}" is not a valid option (expected: ${field.options.join(', ')})`)
        }
      }
      break
    }
    // string, text_area, file_path — no further validation needed beyond presence
  }

  return errors
}

// ─── Main Validator ────────────────────────────────────────────────

export function validatePipelineClient(
  nodes: Node<BlockNodeData>[],
  edges: Edge[],
  hardware?: HardwareSpec,
): DiagnosticReport {
  const errors: DiagnosticItem[] = []
  const warnings: DiagnosticItem[] = []
  const info: DiagnosticItem[] = []

  // Filter to only block nodes (not sticky notes or groups)
  const blockNodes = nodes.filter(n => n.type === 'blockNode' && n.data?.type)
  const nodeMap = new Map(blockNodes.map(n => [n.id, n]))

  // ═══ STRUCTURE CHECKS ═══

  // 1. Empty pipeline
  if (blockNodes.length === 0) {
    errors.push({
      message: 'Pipeline is empty — add blocks to get started',
      severity: 'error',
      category: 'structure',
      suggestion: 'Drag blocks from the Module Library on the left',
    })
  }

  // 2. Duplicate IDs
  const idSet = new Set<string>()
  for (const n of blockNodes) {
    if (idSet.has(n.id)) {
      errors.push({
        message: `Duplicate node ID: ${n.id}`,
        nodeId: n.id,
        severity: 'error',
        category: 'structure',
      })
    }
    idSet.add(n.id)
  }

  // 3. Cycle detection
  if (blockNodes.length > 0) {
    const cycle = hasCycle(blockNodes, edges)
    if (cycle) {
      errors.push({
        message: 'Pipeline contains a cycle — blocks form a loop',
        severity: 'error',
        category: 'structure',
        suggestion: 'Remove one of the edges creating the cycle',
      })
    }
  }

  // 4. Disconnected nodes
  const connectedNodeIds = new Set<string>()
  for (const e of edges) {
    connectedNodeIds.add(e.source)
    connectedNodeIds.add(e.target)
  }
  for (const n of blockNodes) {
    if (blockNodes.length > 1 && !connectedNodeIds.has(n.id)) {
      warnings.push({
        message: `"${n.data.label}" is disconnected from the pipeline`,
        nodeId: n.id,
        severity: 'warning',
        category: 'structure',
        suggestion: 'Connect it to other blocks or remove it',
      })
    }
  }

  // 5. No terminal node
  const hasOutputEdge = new Set(edges.map(e => e.source))
  const terminalNodes = blockNodes.filter(n => !hasOutputEdge.has(n.id))
  if (blockNodes.length > 0 && terminalNodes.length === 0) {
    warnings.push({
      message: 'No terminal block — pipeline has no endpoint',
      severity: 'warning',
      category: 'structure',
      suggestion: 'Add an endpoint block (Save, Export, etc.) to capture results',
    })
  }

  // 6. No source node
  const hasInputEdge = new Set(edges.map(e => e.target))
  const sourceNodes = blockNodes.filter(n => !hasInputEdge.has(n.id))
  if (blockNodes.length > 1 && sourceNodes.length === 0) {
    info.push({
      message: 'No source block detected — all blocks receive input from others',
      severity: 'info',
      category: 'structure',
    })
  }

  // ═══ CONFIGURATION CHECKS ═══

  for (const node of blockNodes) {
    const def = getBlockDefinition(node.data.type)
    if (!def) continue

    const connectedInputIds = getConnectedInputs(node.id, edges)

    // 7. Required inputs not connected
    for (const input of def.inputs) {
      if (input.required && !connectedInputIds.has(input.id)) {
        errors.push({
          message: `"${node.data.label}" requires input "${input.label}" but it is not connected`,
          nodeId: node.id,
          severity: 'error',
          category: 'config',
          suggestion: `Connect a ${input.dataType} output to the "${input.label}" port`,
        })
      }
    }

    // 8 & 9. Critical and non-critical config
    const criticals = CRITICAL_CONFIG[node.data.type]
    if (criticals) {
      for (const { field, label } of criticals) {
        const val = node.data.config?.[field]
        // Skip model_name check if a model input is connected
        if (field === 'model_name' && connectedInputIds.has('model')) continue
        if (!val || (typeof val === 'string' && val.trim() === '')) {
          errors.push({
            message: `"${node.data.label}" is missing required config "${label}"`,
            nodeId: node.id,
            severity: 'error',
            category: 'config',
            suggestion: `Set "${label}" in the block configuration panel`,
          })
        }
      }
    }
  }

  // ═══ DEEP CONFIG VALIDATION ═══
  // Validates config values against block.yaml schema (types, bounds, select options)

  for (const node of blockNodes) {
    const def = getBlockDefinition(node.data.type)
    if (!def || !def.configFields || def.configFields.length === 0) continue

    const config = node.data.config ?? {}

    for (const field of def.configFields) {
      const value = config[field.name]

      // Skip empty/missing — already handled by critical config checks above
      if (value === undefined || value === null || value === '') continue

      const fieldErrors = validateConfigField(field, value)
      for (const msg of fieldErrors) {
        warnings.push({
          message: `"${node.data.label}": ${msg}`,
          nodeId: node.id,
          severity: 'warning',
          category: 'config',
          suggestion: `Check the "${field.label}" setting in the block configuration panel`,
        })
      }
    }
  }

  // ═══ COMPATIBILITY CHECKS ═══

  for (const edge of edges) {
    // 11. Source/target exists
    if (!nodeMap.has(edge.source)) {
      errors.push({
        message: `Edge references missing source node: ${edge.source}`,
        severity: 'error',
        category: 'compatibility',
      })
      continue
    }
    if (!nodeMap.has(edge.target)) {
      errors.push({
        message: `Edge references missing target node: ${edge.target}`,
        severity: 'error',
        category: 'compatibility',
      })
      continue
    }

    // 12. Self-loops
    if (edge.source === edge.target) {
      errors.push({
        message: `Self-loop detected on "${nodeMap.get(edge.source)?.data.label}"`,
        nodeId: edge.source,
        severity: 'error',
        category: 'compatibility',
      })
      continue
    }

    // 13. Port type compatibility
    const sourceNode = nodeMap.get(edge.source)!
    const targetNode = nodeMap.get(edge.target)!
    const sourceDef = getBlockDefinition(sourceNode.data.type)
    const targetDef = getBlockDefinition(targetNode.data.type)

    if (sourceDef && targetDef && edge.sourceHandle && edge.targetHandle) {
      const sourcePort = resolvePort(sourceDef.outputs, edge.sourceHandle)
      const targetPort = resolvePort(targetDef.inputs, edge.targetHandle)

      if (sourcePort && targetPort && !isPortCompatible(sourcePort.dataType, targetPort.dataType)) {
        errors.push({
          message: `Type mismatch: "${sourceNode.data.label}" outputs ${sourcePort.dataType} but "${targetNode.data.label}" expects ${targetPort.dataType}`,
          nodeId: edge.target,
          severity: 'error',
          category: 'compatibility',
          suggestion: `These port types are incompatible. Remove this connection.`,
        })
      }
    }
  }

  // ═══ HARDWARE CHECKS ═══

  // Get hardware info
  let hw: HardwareSpec
  if (hardware) {
    hw = hardware
  } else {
    const profile = useHardwareStore.getState().profile
    if (profile) {
      const gpu = profile.gpu?.[0]
      hw = {
        ramGB: profile.ram?.total_gb ?? 16,
        gpuVramGB: gpu?.vram_gb ?? 0,
        gpuType: gpu?.type === 'metal' ? 'metal' : gpu?.type === 'cuda' ? 'cuda' : gpu?.type === 'rocm' ? 'rocm' : 'cpu',
        cpuCores: profile.cpu?.cores ?? 4,
      }
    } else {
      hw = { ramGB: 16, gpuVramGB: 0, gpuType: 'cpu', cpuCores: 4 }
    }
  }

  let estimate: PipelineEstimate | null = null
  const infeasibleBlocks: string[] = []
  const recommendations: string[] = []

  if (blockNodes.length > 0) {
    estimate = estimatePipeline(blockNodes, hw)

    // 14. Memory check
    if (estimate.peakMemoryGB > hw.ramGB * 0.9) {
      errors.push({
        message: `Peak memory (${estimate.peakMemoryGB.toFixed(1)} GB) exceeds 90% of available RAM (${hw.ramGB} GB)`,
        severity: 'error',
        category: 'hardware',
        suggestion: 'Reduce batch sizes or use quantization to lower memory usage',
      })
    } else if (estimate.peakMemoryGB > hw.ramGB * 0.7) {
      warnings.push({
        message: `Peak memory (${estimate.peakMemoryGB.toFixed(1)} GB) uses >70% of RAM (${hw.ramGB} GB)`,
        severity: 'warning',
        category: 'hardware',
        suggestion: 'Consider closing other applications before running',
      })
    }

    // 15-17. Per-block hardware checks
    for (const be of estimate.blockEstimates) {
      if (be.gpuRequired && hw.gpuType === 'cpu') {
        warnings.push({
          message: `"${be.label}" requires GPU but none detected — will use CPU (slower)`,
          nodeId: be.nodeId,
          severity: 'warning',
          category: 'hardware',
        })
      }
      if (be.memoryGB > hw.ramGB * 0.95) {
        infeasibleBlocks.push(be.label)
        errors.push({
          message: `"${be.label}" needs ~${be.memoryGB.toFixed(1)} GB RAM (only ${hw.ramGB} GB available)`,
          nodeId: be.nodeId,
          severity: 'error',
          category: 'hardware',
          suggestion: 'Use a smaller model or quantized variant',
        })
      }
    }

    // Recommendations
    if (hw.gpuType === 'cpu') {
      recommendations.push('Add a GPU to significantly speed up model operations')
    }
    if (hw.ramGB < 16) {
      recommendations.push('16+ GB RAM recommended for most model operations')
    }
    if (estimate.peakMemoryGB > hw.ramGB * 0.5) {
      recommendations.push('Consider reducing batch sizes to lower memory usage')
    }
  }

  // ═══ PERFORMANCE CHECKS ═══

  if (estimate) {
    // 18. Runtime estimate
    info.push({
      message: `Estimated total runtime: ${formatTime(estimate.totalSeconds)}`,
      severity: 'info',
      category: 'performance',
    })

    // 19. Long runtime warning
    if (estimate.totalSeconds > 3600) {
      warnings.push({
        message: `Pipeline may take over 1 hour (${formatTime(estimate.totalSeconds)})`,
        severity: 'warning',
        category: 'performance',
        suggestion: 'Consider breaking into smaller sub-pipelines',
      })
    }

    // 20. Bottleneck identification
    if (estimate.blockEstimates.length > 1) {
      const sorted = [...estimate.blockEstimates].sort((a, b) => b.seconds - a.seconds)
      const slowest = sorted[0]
      if (slowest.seconds > estimate.totalSeconds * 0.5) {
        info.push({
          message: `Bottleneck: "${slowest.label}" takes ${formatTime(slowest.seconds)} (${Math.round(slowest.seconds / estimate.totalSeconds * 100)}% of total)`,
          nodeId: slowest.nodeId,
          severity: 'info',
          category: 'performance',
        })
      }
    }
  }

  // ═══ BUILD SECTIONS ═══

  const sectionCategories: Array<{ key: DiagnosticItem['category']; title: string }> = [
    { key: 'structure', title: 'Structure' },
    { key: 'config', title: 'Configuration' },
    { key: 'compatibility', title: 'Compatibility' },
    { key: 'hardware', title: 'Hardware' },
    { key: 'performance', title: 'Performance' },
  ]

  const allItems = [...errors, ...warnings, ...info]
  const sections: ReportSection[] = sectionCategories.map(({ key, title }) => {
    const items = allItems.filter(i => i.category === key)
    const hasError = items.some(i => i.severity === 'error')
    const hasWarning = items.some(i => i.severity === 'warning')
    return {
      title,
      status: hasError ? 'fail' : hasWarning ? 'warn' : 'pass',
      items,
    }
  })

  // ═══ HEALTH SCORE ═══

  let score = 100
  score -= errors.length * 20
  score -= warnings.length * 5
  if (infeasibleBlocks.length > 0) score -= 30
  score = Math.max(0, Math.min(100, score))

  const gpuRequired = estimate?.blockEstimates.some(b => b.gpuRequired) ?? false

  return {
    valid: errors.length === 0,
    score,
    errors,
    warnings,
    info,
    stats: {
      blockCount: blockNodes.length,
      edgeCount: edges.length,
      estimatedRuntime: estimate?.totalSeconds ?? 0,
      peakMemoryGB: estimate?.peakMemoryGB ?? 0,
      gpuRequired,
    },
    hardware: {
      feasible: infeasibleBlocks.length === 0,
      ramAvailableGB: hw.ramGB,
      gpuVramGB: hw.gpuVramGB,
      gpuType: hw.gpuType,
      infeasibleBlocks,
      recommendations,
    },
    sections,
  }
}
