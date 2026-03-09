/**
 * Pipeline Estimation Engine
 *
 * Provides per-block time estimates, memory requirements, and
 * hardware feasibility checks. All estimates are calibrated for
 * an M3 Pro (10-core, 36 GB) as the reference machine.
 */

import type { Node } from '@xyflow/react'
import type { BlockNodeData } from '@/stores/pipelineStore'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface BlockEstimate {
  nodeId: string
  blockType: string
  label: string
  seconds: number
  memoryGB: number
  gpuRequired: boolean
  warnings: string[]
}

export interface PipelineEstimate {
  totalSeconds: number
  peakMemoryGB: number
  blockEstimates: BlockEstimate[]
  feasible: boolean
  warnings: string[]
}

export interface HardwareSpec {
  ramGB: number
  gpuVramGB: number
  gpuType: 'metal' | 'cuda' | 'rocm' | 'cpu'
  cpuCores: number
}

/* ------------------------------------------------------------------ */
/*  Base estimates per block type                                      */
/*  Reference: M3 Pro 10-core / 36 GB / Metal                         */
/* ------------------------------------------------------------------ */

interface BaseEst {
  seconds: number
  memoryGB: number
  gpuRequired: boolean
}

const BASE_ESTIMATES: Record<string, BaseEst> = {
  // ── External / Source ──
  huggingface_loader:    { seconds: 15,   memoryGB: 1,    gpuRequired: false },
  huggingface_model:     { seconds: 30,   memoryGB: 4,    gpuRequired: false },
  text_input:            { seconds: 1,    memoryGB: 0.01, gpuRequired: false },
  local_file_loader:     { seconds: 3,    memoryGB: 0.5,  gpuRequired: false },
  api_data_fetcher:      { seconds: 5,    memoryGB: 0.1,  gpuRequired: false },
  web_scraper:           { seconds: 10,   memoryGB: 0.2,  gpuRequired: false },
  sql_query:             { seconds: 5,    memoryGB: 0.3,  gpuRequired: false },
  document_ingestion:    { seconds: 8,    memoryGB: 0.5,  gpuRequired: false },
  synthetic_data_gen:    { seconds: 20,   memoryGB: 1,    gpuRequired: false },
  config_builder:        { seconds: 1,    memoryGB: 0.01, gpuRequired: false },
  config_file_loader:    { seconds: 1,    memoryGB: 0.01, gpuRequired: false },
  model_selector:        { seconds: 2,    memoryGB: 0.1,  gpuRequired: false },
  cloud_compute_provider:{ seconds: 5,    memoryGB: 0.1,  gpuRequired: false },
  streaming_server:      { seconds: 2,    memoryGB: 0.2,  gpuRequired: false },
  data_exporter:         { seconds: 3,    memoryGB: 0.2,  gpuRequired: false },
  results_exporter:      { seconds: 3,    memoryGB: 0.2,  gpuRequired: false },

  // ── Transform / Data ──
  filter_sample:         { seconds: 2,    memoryGB: 0.5,  gpuRequired: false },
  column_transform:      { seconds: 3,    memoryGB: 0.5,  gpuRequired: false },
  data_augmentation:     { seconds: 15,   memoryGB: 1,    gpuRequired: false },
  train_val_test_split:  { seconds: 2,    memoryGB: 0.5,  gpuRequired: false },
  data_preview:          { seconds: 1,    memoryGB: 0.1,  gpuRequired: false },
  data_merger:           { seconds: 3,    memoryGB: 0.5,  gpuRequired: false },
  text_chunker:          { seconds: 5,    memoryGB: 0.3,  gpuRequired: false },
  text_concatenator:     { seconds: 1,    memoryGB: 0.1,  gpuRequired: false },
  text_classifier:       { seconds: 10,   memoryGB: 2,    gpuRequired: true  },
  text_summarizer:       { seconds: 20,   memoryGB: 4,    gpuRequired: true  },
  text_translator:       { seconds: 25,   memoryGB: 4,    gpuRequired: true  },
  prompt_template:       { seconds: 1,    memoryGB: 0.01, gpuRequired: false },

  // ── Training ──
  lora_finetuning:       { seconds: 1800, memoryGB: 12,   gpuRequired: true  },
  qlora_finetuning:      { seconds: 1200, memoryGB: 8,    gpuRequired: true  },
  full_finetuning:       { seconds: 3600, memoryGB: 24,   gpuRequired: true  },
  dpo_alignment:         { seconds: 2400, memoryGB: 16,   gpuRequired: true  },
  rlhf_ppo:             { seconds: 3000, memoryGB: 20,   gpuRequired: true  },
  distillation:          { seconds: 1800, memoryGB: 16,   gpuRequired: true  },
  curriculum_training:   { seconds: 2400, memoryGB: 14,   gpuRequired: true  },
  reward_model_trainer:  { seconds: 1800, memoryGB: 12,   gpuRequired: true  },
  continued_pretraining: { seconds: 7200, memoryGB: 24,   gpuRequired: true  },
  hyperparameter_sweep:  { seconds: 5400, memoryGB: 12,   gpuRequired: true  },
  checkpoint_selector:   { seconds: 5,    memoryGB: 0.5,  gpuRequired: false },

  // ── Model / Inference ──
  llm_inference:         { seconds: 10,   memoryGB: 6,    gpuRequired: true  },
  batch_inference:       { seconds: 60,   memoryGB: 8,    gpuRequired: true  },
  quantize_model:        { seconds: 120,  memoryGB: 10,   gpuRequired: true  },
  reranker:              { seconds: 15,   memoryGB: 4,    gpuRequired: true  },
  artifact_packager:     { seconds: 10,   memoryGB: 2,    gpuRequired: false },
  model_card_writer:     { seconds: 5,    memoryGB: 0.5,  gpuRequired: false },

  // ── New Inference ──
  chat_completion:       { seconds: 12,   memoryGB: 6,    gpuRequired: true  },
  structured_output:     { seconds: 15,   memoryGB: 6,    gpuRequired: true  },
  vision_inference:      { seconds: 20,   memoryGB: 8,    gpuRequired: true  },
  function_calling:      { seconds: 12,   memoryGB: 6,    gpuRequired: true  },
  few_shot_prompting:    { seconds: 15,   memoryGB: 6,    gpuRequired: true  },
  guardrails:            { seconds: 5,    memoryGB: 2,    gpuRequired: false },
  prompt_chain:          { seconds: 30,   memoryGB: 6,    gpuRequired: true  },
  ab_test_inference:     { seconds: 25,   memoryGB: 8,    gpuRequired: true  },
  token_counter:         { seconds: 2,    memoryGB: 0.1,  gpuRequired: false },
  response_parser:       { seconds: 2,    memoryGB: 0.1,  gpuRequired: false },
  model_router:          { seconds: 12,   memoryGB: 6,    gpuRequired: true  },

  // ── Merge ──
  slerp_merge:           { seconds: 120,  memoryGB: 16,   gpuRequired: false },
  ties_merge:            { seconds: 120,  memoryGB: 16,   gpuRequired: false },
  dare_merge:            { seconds: 120,  memoryGB: 16,   gpuRequired: false },
  frankenmerge:          { seconds: 180,  memoryGB: 20,   gpuRequired: false },
  mergekit_merge:        { seconds: 150,  memoryGB: 18,   gpuRequired: false },

  // ── Evaluate / Metrics ──
  mmlu_eval:             { seconds: 300,  memoryGB: 8,    gpuRequired: true  },
  lm_eval_harness:       { seconds: 600,  memoryGB: 10,   gpuRequired: true  },
  human_eval:            { seconds: 300,  memoryGB: 8,    gpuRequired: true  },
  toxicity_eval:         { seconds: 120,  memoryGB: 4,    gpuRequired: true  },
  factuality_checker:    { seconds: 60,   memoryGB: 4,    gpuRequired: true  },
  custom_eval:           { seconds: 60,   memoryGB: 2,    gpuRequired: false },
  results_formatter:     { seconds: 2,    memoryGB: 0.1,  gpuRequired: false },
  experiment_logger:     { seconds: 2,    memoryGB: 0.1,  gpuRequired: false },
  ab_comparator:         { seconds: 5,    memoryGB: 0.2,  gpuRequired: false },
  control_tower:         { seconds: 3,    memoryGB: 0.1,  gpuRequired: false },
  custom_benchmark:      { seconds: 300,  memoryGB: 6,    gpuRequired: true  },
  latency_profiler:      { seconds: 30,   memoryGB: 0.5,  gpuRequired: false },
  leaderboard_publisher: { seconds: 5,    memoryGB: 0.1,  gpuRequired: false },
  report_generator:      { seconds: 10,   memoryGB: 0.5,  gpuRequired: false },
  model_telemetry:       { seconds: 5,    memoryGB: 0.2,  gpuRequired: false },

  // ── Embedding ──
  vector_store_build:    { seconds: 30,   memoryGB: 3,    gpuRequired: true  },
  embedding_generator:   { seconds: 20,   memoryGB: 3,    gpuRequired: true  },
  embedding_similarity_search: { seconds: 5, memoryGB: 2, gpuRequired: false },
  embedding_clustering:  { seconds: 15,   memoryGB: 2,    gpuRequired: false },
  embedding_visualizer:  { seconds: 5,    memoryGB: 1,    gpuRequired: false },

  // ── Agents ──
  retrieval_agent:       { seconds: 15,   memoryGB: 4,    gpuRequired: true  },
  agent_orchestrator:    { seconds: 30,   memoryGB: 6,    gpuRequired: true  },
  agent_evaluator:       { seconds: 20,   memoryGB: 4,    gpuRequired: true  },
  agent_memory:          { seconds: 5,    memoryGB: 2,    gpuRequired: false },
  tool_registry:         { seconds: 2,    memoryGB: 0.2,  gpuRequired: false },
  chain_of_thought:      { seconds: 20,   memoryGB: 6,    gpuRequired: true  },
  code_agent:            { seconds: 30,   memoryGB: 6,    gpuRequired: true  },
  multi_agent_debate:    { seconds: 60,   memoryGB: 8,    gpuRequired: true  },
  agent_text_bridge:     { seconds: 3,    memoryGB: 0.5,  gpuRequired: false },

  // ── Utilities / Flow ──
  conditional_branch:    { seconds: 1,    memoryGB: 0.01, gpuRequired: false },
  loop_iterator:         { seconds: 2,    memoryGB: 0.01, gpuRequired: false },
  aggregator:            { seconds: 2,    memoryGB: 0.1,  gpuRequired: false },
  parallel_fan_out:      { seconds: 1,    memoryGB: 0.01, gpuRequired: false },
  python_runner:         { seconds: 10,   memoryGB: 1,    gpuRequired: false },
  artifact_viewer:       { seconds: 2,    memoryGB: 0.1,  gpuRequired: false },

  // ── Interventions ──
  manual_review:         { seconds: 60,   memoryGB: 0.1,  gpuRequired: false },
  notification_hub:      { seconds: 3,    memoryGB: 0.05, gpuRequired: false },
  agentic_review_loop:   { seconds: 45,   memoryGB: 6,    gpuRequired: true  },
  ab_split_test:         { seconds: 5,    memoryGB: 0.2,  gpuRequired: false },
  quality_gate:          { seconds: 3,    memoryGB: 0.1,  gpuRequired: false },
  rollback_point:        { seconds: 2,    memoryGB: 0.5,  gpuRequired: false },
  human_review_gate:     { seconds: 30,   memoryGB: 0.1,  gpuRequired: false },
  notification_sender:   { seconds: 3,    memoryGB: 0.05, gpuRequired: false },
  error_handler:         { seconds: 1,    memoryGB: 0.01, gpuRequired: false },
  checkpoint_gate:       { seconds: 2,    memoryGB: 0.3,  gpuRequired: false },

  // ── Save ──
  save_csv:              { seconds: 3,    memoryGB: 0.2,  gpuRequired: false },
  save_txt:              { seconds: 2,    memoryGB: 0.1,  gpuRequired: false },
  save_json:             { seconds: 3,    memoryGB: 0.2,  gpuRequired: false },
  save_parquet:          { seconds: 5,    memoryGB: 0.3,  gpuRequired: false },
  save_pdf:              { seconds: 8,    memoryGB: 0.5,  gpuRequired: false },
  save_model:            { seconds: 15,   memoryGB: 2,    gpuRequired: false },
  save_embeddings:       { seconds: 10,   memoryGB: 1,    gpuRequired: false },
  save_yaml:             { seconds: 2,    memoryGB: 0.05, gpuRequired: false },
}

/* ------------------------------------------------------------------ */
/*  Fallback for unknown blocks                                        */
/* ------------------------------------------------------------------ */

const UNKNOWN_ESTIMATE: BaseEst = { seconds: 10, memoryGB: 1, gpuRequired: false }

/* ------------------------------------------------------------------ */
/*  Config-based scaling factors                                       */
/* ------------------------------------------------------------------ */

function applyConfigScaling(base: BaseEst, config: Record<string, any>, blockType: string): BaseEst {
  let { seconds, memoryGB } = base
  const gpuRequired = base.gpuRequired

  // Epoch scaling for training blocks
  const epochs = config.epochs ?? config.num_epochs
  if (typeof epochs === 'number' && epochs > 0) {
    seconds *= (epochs / 3) // reference is 3 epochs
  }

  // Batch size inversely affects time
  const batchSize = config.batch_size
  if (typeof batchSize === 'number' && batchSize > 0) {
    seconds *= (4 / batchSize) // reference is batch=4
  }

  // Max samples scaling
  const maxSamples = config.max_samples
  if (typeof maxSamples === 'number' && maxSamples > 0) {
    const sampleFactor = maxSamples / 5000 // reference is 5000
    seconds *= Math.max(0.1, sampleFactor)
  }

  // Max tokens for inference
  const maxTokens = config.max_tokens
  if (typeof maxTokens === 'number' && maxTokens > 0 && blockType.includes('inference')) {
    seconds *= (maxTokens / 512) // reference is 512
  }

  // Max iterations for agentic loops
  const maxIter = config.max_iterations
  if (typeof maxIter === 'number' && maxIter > 0) {
    seconds *= (maxIter / 3) // reference is 3
  }

  return { seconds: Math.max(1, Math.round(seconds)), memoryGB, gpuRequired }
}

/* ------------------------------------------------------------------ */
/*  Hardware adjustment                                                */
/* ------------------------------------------------------------------ */

const REFERENCE_HW: HardwareSpec = {
  ramGB: 36,
  gpuVramGB: 36,
  gpuType: 'metal',
  cpuCores: 10,
}

function adjustForHardware(seconds: number, hw: HardwareSpec): number {
  // More cores = faster for CPU-bound work
  const coreFactor = REFERENCE_HW.cpuCores / Math.max(1, hw.cpuCores)
  // More VRAM = faster for GPU work (rough proxy)
  const vramFactor = hw.gpuType === 'cpu'
    ? 2.0 // CPU-only is ~2x slower
    : REFERENCE_HW.gpuVramGB / Math.max(1, hw.gpuVramGB)

  const factor = Math.max(coreFactor, vramFactor)
  return Math.max(1, Math.round(seconds * Math.sqrt(factor)))
}

/* ------------------------------------------------------------------ */
/*  Main estimation function                                           */
/* ------------------------------------------------------------------ */

export function estimatePipeline(
  nodes: Node<BlockNodeData>[],
  hardware?: HardwareSpec,
): PipelineEstimate {
  const hw = hardware ?? REFERENCE_HW
  const blockEstimates: BlockEstimate[] = []
  const warnings: string[] = []
  let peakMemoryGB = 0

  for (const node of nodes) {
    const bt = node.data.type
    const config = node.data.config || {}
    const base = BASE_ESTIMATES[bt] ?? UNKNOWN_ESTIMATE

    const scaled = applyConfigScaling(base, config, bt)
    const adjustedSeconds = adjustForHardware(scaled.seconds, hw)

    const blockWarnings: string[] = []

    // Memory feasibility
    if (scaled.memoryGB > hw.ramGB * 0.9) {
      blockWarnings.push(`Requires ~${scaled.memoryGB.toFixed(1)} GB RAM (${hw.ramGB} GB available)`)
    }

    // GPU feasibility
    if (scaled.gpuRequired && hw.gpuType === 'cpu') {
      blockWarnings.push('Requires GPU — will fall back to CPU (much slower)')
    }

    if (scaled.memoryGB > peakMemoryGB) {
      peakMemoryGB = scaled.memoryGB
    }

    blockEstimates.push({
      nodeId: node.id,
      blockType: bt,
      label: node.data.label,
      seconds: adjustedSeconds,
      memoryGB: scaled.memoryGB,
      gpuRequired: scaled.gpuRequired,
      warnings: blockWarnings,
    })
  }

  // Total time is additive (sequential execution)
  const totalSeconds = blockEstimates.reduce((s, b) => s + b.seconds, 0)

  // Feasibility: any block exceeding memory = infeasible
  const infeasibleBlocks = blockEstimates.filter(b => b.memoryGB > hw.ramGB * 0.95)
  const feasible = infeasibleBlocks.length === 0

  if (!feasible) {
    warnings.push(`${infeasibleBlocks.length} block(s) may exceed available memory`)
  }

  if (blockEstimates.some(b => b.gpuRequired) && hw.gpuType === 'cpu') {
    warnings.push('Some blocks require GPU — performance will be degraded on CPU')
  }

  if (totalSeconds > 3600) {
    warnings.push(`Estimated total time exceeds 1 hour (${formatTime(totalSeconds)})`)
  }

  return {
    totalSeconds,
    peakMemoryGB,
    blockEstimates,
    feasible,
    warnings,
  }
}

/* ------------------------------------------------------------------ */
/*  Time formatting helper                                             */
/* ------------------------------------------------------------------ */

export function formatTime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return s > 0 ? `${m}m ${s}s` : `${m}m`
  }
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}

export function formatTimeShort(seconds: number): string {
  if (seconds < 60) return `~${seconds}s`
  if (seconds < 3600) return `~${Math.ceil(seconds / 60)}m`
  const h = Math.floor(seconds / 3600)
  const m = Math.ceil((seconds % 3600) / 60)
  return m > 0 ? `~${h}h${m}m` : `~${h}h`
}
