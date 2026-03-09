import { CATEGORY_COLORS } from './design-tokens'

// Category-based accent colors for template nodes
const TPL_ACCENT = {
  external:      CATEGORY_COLORS.external,       // #F97316 — orange
  data:          CATEGORY_COLORS.data,           // #22D3EE — cyan
  model:         CATEGORY_COLORS.model,          // #A78BFA — violet
  inference:     CATEGORY_COLORS.inference,      // #A3E635 — lime
  training:      CATEGORY_COLORS.training,       // #3B82F6 — blue
  metrics:       CATEGORY_COLORS.metrics,        // #34D399 — emerald
  embedding:     CATEGORY_COLORS.embedding,      // #FB7185 — rose
  utilities:     CATEGORY_COLORS.utilities,      // #94A3B8 — slate
  agents:        CATEGORY_COLORS.agents,         // #F43F5E — crimson
  interventions: CATEGORY_COLORS.interventions,  // #FBBF24 — amber/gold
  endpoints:     CATEGORY_COLORS.endpoints,      // #38BDF8 — sky blue
}
import type { Node, Edge } from '@xyflow/react'
import type { BlockNodeData } from '@/stores/pipelineStore'
import { LLM_DEFAULTS } from './llm-prompts'

export interface PipelineTemplate {
  id: string
  name: string
  description: string
  icon: string
  category: string
  blockCount: number
  nodes: Node<BlockNodeData>[]
  edges: Edge[]
}

// Helper to create a block node for templates
function tNode(
  id: string,
  type: string,
  label: string,
  category: string,
  icon: string,
  accent: string,
  position: { x: number; y: number },
  config: Record<string, any> = {},
): Node<BlockNodeData> {
  return {
    id,
    type: 'blockNode',
    position,
    data: {
      type,
      label,
      category,
      icon,
      accent,
      config,
      status: 'idle',
      progress: 0,
    },
  }
}

function tEdge(
  id: string,
  source: string,
  target: string,
  sourceHandle: string,
  targetHandle: string,
  color: string,
): Edge {
  return {
    id,
    source,
    target,
    sourceHandle,
    targetHandle,
    type: 'smoothstep',
    animated: true,
    style: { stroke: color, strokeWidth: 1.5 },
  }
}

export const PIPELINE_TEMPLATES: PipelineTemplate[] = [
  // ── 0. Blank Canvas ────────────────────────────────────
  {
    id: 'blank-canvas',
    name: 'Blank Canvas',
    description: 'Start with a completely empty pipeline and build your custom workflow from scratch.',
    icon: 'LayoutTemplate',
    category: 'utilities',
    blockCount: 0,
    nodes: [],
    edges: [],
  },
  // ── 1. Fine-Tune & Evaluate ────────────────────────────
  {
    id: 'fine-tune-evaluate',
    name: 'Fine-Tune & Evaluate',
    description:
      'End-to-end fine-tuning pipeline: load a HuggingFace dataset, split into train/val/test, fine-tune with LoRA, evaluate with LM Eval Harness, and format the results.',
    icon: 'Zap',
    category: 'training',
    blockCount: 5,
    nodes: [
      tNode(
        'tpl_fte_1', 'huggingface_loader', 'HuggingFace Loader', 'external', 'Download', TPL_ACCENT.external,
        { x: 400, y: 80 },
        { dataset_name: 'tatsu-lab/alpaca', split: 'train', max_samples: 5000 },
      ),
      tNode(
        'tpl_fte_2', 'train_val_test_split', 'Train/Val/Test Split', 'data', 'Split', TPL_ACCENT.data,
        { x: 400, y: 240 },
        { train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 42, stratify: '' },
      ),
      tNode(
        'tpl_fte_3', 'lora_finetuning', 'LoRA Fine-Tuning', 'training', 'Zap', TPL_ACCENT.training,
        { x: 400, y: 400 },
        { model_name: 'meta-llama/Llama-2-7b-hf', r: 16, alpha: 32, lr: 1e-4, epochs: 3, batch_size: 4 },
      ),
      tNode(
        'tpl_fte_4', 'lm_eval_harness', 'LM Eval Harness', 'metrics', 'ClipboardCheck', TPL_ACCENT.metrics,
        { x: 400, y: 560 },
        { tasks: 'hellaswag,arc_easy', num_fewshot: 0, batch_size: 'auto' },
      ),
      tNode(
        'tpl_fte_5', 'results_formatter', 'Results Formatter', 'metrics', 'FileOutput', TPL_ACCENT.metrics,
        { x: 400, y: 720 },
        { format: 'csv', include_config: true },
      ),
    ],
    edges: [
      tEdge('tpl_fte_e1', 'tpl_fte_1', 'tpl_fte_2', 'dataset', 'dataset', '#22D3EE'),
      tEdge('tpl_fte_e2', 'tpl_fte_2', 'tpl_fte_3', 'train', 'dataset', '#22D3EE'),
      tEdge('tpl_fte_e3', 'tpl_fte_3', 'tpl_fte_4', 'model', 'model', '#A78BFA'),
      tEdge('tpl_fte_e4', 'tpl_fte_4', 'tpl_fte_5', 'metrics', 'metrics', '#34D399'),
    ],
  },

  // ── 2. RAG Pipeline ────────────────────────────────────
  {
    id: 'rag-pipeline',
    name: 'RAG Pipeline',
    description:
      'Retrieval-Augmented Generation: load local files, ingest documents, chunk text, build a vector store, and query with a retrieval agent.',
    icon: 'Search',
    category: 'agents',
    blockCount: 5,
    nodes: [
      tNode(
        'tpl_rag_1', 'local_file_loader', 'Local File Loader', 'external', 'FileInput', TPL_ACCENT.external,
        { x: 300, y: 80 },
        { file_path: '', format: 'auto' },
      ),
      tNode(
        'tpl_rag_2', 'document_ingestion', 'Document Ingestion', 'external', 'FileText', TPL_ACCENT.external,
        { x: 600, y: 80 },
        { directory_path: '', glob_pattern: '*.pdf' },
      ),
      tNode(
        'tpl_rag_3', 'text_chunker', 'Text Chunker', 'data', 'Scissors', TPL_ACCENT.data,
        { x: 450, y: 260 },
        { chunk_size: 1000, chunk_overlap: 200, strategy: 'recursive' },
      ),
      tNode(
        'tpl_rag_4', 'vector_store_build', 'Vector Store Builder', 'embedding', 'Database', TPL_ACCENT.embedding,
        { x: 450, y: 440 },
        { store_type: 'chroma', collection_name: 'blueprint_rag' },
      ),
      tNode(
        'tpl_rag_5', 'retrieval_agent', 'Retrieval Agent', 'agents', 'Search', TPL_ACCENT.agents,
        { x: 450, y: 620 },
        { top_k: 5, rerank: true, max_tokens: 1024 },
      ),
    ],
    edges: [
      tEdge('tpl_rag_e1', 'tpl_rag_1', 'tpl_rag_3', 'dataset', 'dataset', '#22D3EE'),
      tEdge('tpl_rag_e2', 'tpl_rag_2', 'tpl_rag_3', 'dataset', 'dataset', '#22D3EE'),
      tEdge('tpl_rag_e3', 'tpl_rag_3', 'tpl_rag_4', 'dataset', 'dataset', '#22D3EE'),
      tEdge('tpl_rag_e4', 'tpl_rag_4', 'tpl_rag_5', 'config', 'config', '#22D3EE'),
    ],
  },

  // ── 3. Model Comparison ────────────────────────────────
  {
    id: 'model-comparison',
    name: 'Model Comparison',
    description:
      'Compare two models side-by-side: load data, split it, run LM Eval Harness on each model in parallel, then format combined results.',
    icon: 'GitCompareArrows',
    category: 'metrics',
    blockCount: 5,
    nodes: [
      tNode(
        'tpl_mc_1', 'huggingface_loader', 'HuggingFace Loader', 'external', 'Download', TPL_ACCENT.external,
        { x: 450, y: 80 },
        { dataset_name: '', split: 'test', max_samples: 1000 },
      ),
      tNode(
        'tpl_mc_2', 'train_val_test_split', 'Train/Val/Test Split', 'data', 'Split', TPL_ACCENT.data,
        { x: 450, y: 240 },
        { train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 42, stratify: '' },
      ),
      tNode(
        'tpl_mc_3a', 'lm_eval_harness', 'LM Eval — Model A', 'metrics', 'ClipboardCheck', TPL_ACCENT.metrics,
        { x: 250, y: 420 },
        { tasks: 'hellaswag,arc_easy', num_fewshot: 0, batch_size: 'auto' },
      ),
      tNode(
        'tpl_mc_3b', 'lm_eval_harness', 'LM Eval — Model B', 'metrics', 'ClipboardCheck', TPL_ACCENT.metrics,
        { x: 650, y: 420 },
        { tasks: 'hellaswag,arc_easy', num_fewshot: 0, batch_size: 'auto' },
      ),
      tNode(
        'tpl_mc_4', 'results_formatter', 'Results Formatter', 'metrics', 'FileOutput', TPL_ACCENT.metrics,
        { x: 450, y: 600 },
        { format: 'csv', include_config: true },
      ),
    ],
    edges: [
      tEdge('tpl_mc_e1', 'tpl_mc_1', 'tpl_mc_2', 'dataset', 'dataset', '#22D3EE'),
      tEdge('tpl_mc_e3a', 'tpl_mc_3a', 'tpl_mc_4', 'metrics', 'metrics', '#34D399'),
      tEdge('tpl_mc_e3b', 'tpl_mc_3b', 'tpl_mc_4', 'metrics', 'metrics', '#34D399'),
    ],
  },

  // ── 4. Data Processing ─────────────────────────────────
  {
    id: 'data-processing',
    name: 'Data Processing',
    description:
      'Standard data pipeline: load a local file, filter and sample rows, split into train/val/test, and preview the results.',
    icon: 'Database',
    category: 'data',
    blockCount: 4,
    nodes: [
      tNode(
        'tpl_dp_1', 'local_file_loader', 'Local File Loader', 'external', 'FileInput', TPL_ACCENT.external,
        { x: 400, y: 80 },
        { file_path: '', format: 'auto' },
      ),
      tNode(
        'tpl_dp_2', 'filter_sample', 'Filter & Sample', 'data', 'Filter', TPL_ACCENT.data,
        { x: 400, y: 240 },
        { method: 'length', min_tokens: 10, sample_size: 0 },
      ),
      tNode(
        'tpl_dp_3', 'train_val_test_split', 'Train/Val/Test Split', 'data', 'Split', TPL_ACCENT.data,
        { x: 400, y: 400 },
        { train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 42, stratify: '' },
      ),
      tNode(
        'tpl_dp_4', 'data_preview', 'Data Preview', 'data', 'Eye', TPL_ACCENT.data,
        { x: 400, y: 560 },
        { num_rows: 20 },
      ),
    ],
    edges: [
      tEdge('tpl_dp_e1', 'tpl_dp_1', 'tpl_dp_2', 'dataset', 'dataset', '#22D3EE'),
      tEdge('tpl_dp_e2', 'tpl_dp_2', 'tpl_dp_3', 'dataset', 'dataset', '#22D3EE'),
      tEdge('tpl_dp_e3', 'tpl_dp_3', 'tpl_dp_4', 'train', 'dataset', '#22D3EE'),
    ],
  },

  // ── 5. Quick Inference ─────────────────────────────────
  {
    id: 'quick-inference',
    name: 'Quick Inference',
    description:
      'Standalone Model + Prompt block for fast inference. Send a prompt to a local or cloud LLM and get a response immediately.',
    icon: 'MessageSquare',
    category: 'model',
    blockCount: 1,
    nodes: [
      tNode(
        'tpl_qi_1', 'llm_inference', 'Model + Prompt', 'inference', 'MessageSquare', TPL_ACCENT.inference,
        { x: 400, y: 160 },
        {
          model_name: '',
          prompt_template: 'You are a helpful assistant.\n\n{context}\n\nUser: {input}\nAssistant:',
          user_input: '',
          provider: 'ollama',
          endpoint: LLM_DEFAULTS.endpoints.ollama,
          temperature: 0.7,
          max_tokens: 512,
        },
      ),
    ],
    edges: [],
  },
]
