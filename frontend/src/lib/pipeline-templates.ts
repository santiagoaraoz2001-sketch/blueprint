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

export type TemplateDifficulty = 'beginner' | 'intermediate' | 'advanced'

export interface TemplateVariable {
  id: string
  label: string
  description: string
  type: 'text' | 'number' | 'select'
  default: string | number
  options?: string[]
  required: boolean
  bindings: Array<{
    nodeId: string
    configKey: string
  }>
}

export interface PipelineTemplate {
  id: string
  name: string
  description: string
  icon: string
  category: string
  blockCount: number
  nodes: Node<BlockNodeData>[]
  edges: Edge[]
  difficulty?: TemplateDifficulty
  estimatedTime?: string
  variables?: TemplateVariable[]
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

  // ═══════════════════════════════════════════════════════════════
  //  QUICKSTART TEMPLATES — with variable binding
  // ═══════════════════════════════════════════════════════════════

  // ── QS1. Fine-Tune a LoRA ──────────────────────────────────
  {
    id: 'qs-finetune-lora',
    name: 'Fine-Tune a LoRA',
    description:
      'Load a dataset, split it, fine-tune a model with LoRA, evaluate with LM Eval Harness, and format results.',
    icon: 'Zap',
    category: 'training',
    blockCount: 6,
    difficulty: 'beginner',
    estimatedTime: '5 min',
    variables: [
      {
        id: 'base_model',
        label: 'Base Model',
        description: 'HuggingFace model ID to fine-tune',
        type: 'text',
        default: 'meta-llama/Llama-2-7b-hf',
        required: true,
        bindings: [
          { nodeId: 'qs1_3', configKey: 'model_name' },
        ],
      },
      {
        id: 'dataset_name',
        label: 'Dataset Name',
        description: 'HuggingFace dataset ID',
        type: 'text',
        default: 'tatsu-lab/alpaca',
        required: true,
        bindings: [
          { nodeId: 'qs1_1', configKey: 'dataset_name' },
        ],
      },
      {
        id: 'learning_rate',
        label: 'Learning Rate',
        description: 'Training learning rate',
        type: 'number',
        default: 0.0001,
        required: false,
        bindings: [
          { nodeId: 'qs1_4', configKey: 'lr' },
        ],
      },
    ],
    nodes: [
      tNode('qs1_1', 'huggingface_loader', 'HuggingFace Loader', 'external', 'Download', TPL_ACCENT.external,
        { x: 80, y: 200 }, { dataset_name: 'tatsu-lab/alpaca', split: 'train', max_samples: 5000 }),
      tNode('qs1_2', 'train_val_test_split', 'Train/Val/Test Split', 'data', 'Split', TPL_ACCENT.data,
        { x: 360, y: 200 }, { train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 42 }),
      tNode('qs1_3', 'model_selector', 'Model Selector', 'model', 'Cpu', TPL_ACCENT.model,
        { x: 640, y: 80 }, { model_name: 'meta-llama/Llama-2-7b-hf', source: 'huggingface' }),
      tNode('qs1_4', 'lora_finetuning', 'LoRA Fine-Tuning', 'training', 'Zap', TPL_ACCENT.training,
        { x: 640, y: 320 }, { r: 16, alpha: 32, lr: 0.0001, epochs: 3, batch_size: 4 }),
      tNode('qs1_5', 'lm_eval_harness', 'LM Eval Harness', 'metrics', 'ClipboardCheck', TPL_ACCENT.metrics,
        { x: 920, y: 200 }, { tasks: 'hellaswag,arc_easy', num_fewshot: 0, batch_size: 'auto' }),
      tNode('qs1_6', 'results_formatter', 'Results Formatter', 'metrics', 'FileOutput', TPL_ACCENT.metrics,
        { x: 1200, y: 200 }, { format: 'csv', include_config: true }),
    ],
    edges: [
      tEdge('qs1_e1', 'qs1_1', 'qs1_2', 'dataset', 'dataset', '#22D3EE'),
      tEdge('qs1_e2', 'qs1_2', 'qs1_4', 'train', 'dataset', '#22D3EE'),
      tEdge('qs1_e3', 'qs1_3', 'qs1_4', 'model', 'model', '#A78BFA'),
      tEdge('qs1_e4', 'qs1_4', 'qs1_5', 'model', 'model', '#A78BFA'),
      tEdge('qs1_e5', 'qs1_5', 'qs1_6', 'metrics', 'metrics', '#34D399'),
    ],
  },

  // ── QS2. Evaluate a Model ──────────────────────────────────
  {
    id: 'qs-evaluate-model',
    name: 'Evaluate a Model',
    description:
      'Pick a model, run standard benchmarks, and format the results. The fastest way to evaluate any model.',
    icon: 'ClipboardCheck',
    category: 'metrics',
    blockCount: 3,
    difficulty: 'beginner',
    estimatedTime: '2 min',
    variables: [
      {
        id: 'model_name',
        label: 'Model Name',
        description: 'HuggingFace model ID or local path',
        type: 'text',
        default: '',
        required: true,
        bindings: [
          { nodeId: 'qs2_1', configKey: 'model_name' },
        ],
      },
      {
        id: 'benchmark',
        label: 'Benchmark',
        description: 'Comma-separated eval tasks',
        type: 'text',
        default: 'hellaswag,arc_easy',
        required: true,
        bindings: [
          { nodeId: 'qs2_2', configKey: 'tasks' },
        ],
      },
    ],
    nodes: [
      tNode('qs2_1', 'model_selector', 'Model Selector', 'model', 'Cpu', TPL_ACCENT.model,
        { x: 80, y: 200 }, { model_name: '', source: 'huggingface' }),
      tNode('qs2_2', 'lm_eval_harness', 'LM Eval Harness', 'metrics', 'ClipboardCheck', TPL_ACCENT.metrics,
        { x: 400, y: 200 }, { tasks: 'hellaswag,arc_easy', num_fewshot: 0, batch_size: 'auto' }),
      tNode('qs2_3', 'results_formatter', 'Results Formatter', 'metrics', 'FileOutput', TPL_ACCENT.metrics,
        { x: 720, y: 200 }, { format: 'csv', include_config: true }),
    ],
    edges: [
      tEdge('qs2_e1', 'qs2_1', 'qs2_2', 'model', 'model', '#A78BFA'),
      tEdge('qs2_e2', 'qs2_2', 'qs2_3', 'metrics', 'metrics', '#34D399'),
    ],
  },

  // ── QS3. Build a RAG Pipeline ──────────────────────────────
  {
    id: 'qs-rag-pipeline',
    name: 'Build a RAG Pipeline',
    description:
      'Ingest documents, chunk text, generate embeddings, build a vector store, select a chat model, and wire up retrieval-augmented generation.',
    icon: 'Search',
    category: 'agents',
    blockCount: 6,
    difficulty: 'intermediate',
    estimatedTime: '10 min',
    variables: [
      {
        id: 'document_path',
        label: 'Document Path',
        description: 'Local directory containing documents',
        type: 'text',
        default: '',
        required: true,
        bindings: [
          { nodeId: 'qs3_1', configKey: 'file_path' },
        ],
      },
      {
        id: 'embedding_model',
        label: 'Embedding Model',
        description: 'Model for generating embeddings',
        type: 'text',
        default: 'sentence-transformers/all-MiniLM-L6-v2',
        required: true,
        bindings: [
          { nodeId: 'qs3_3', configKey: 'model_name' },
        ],
      },
      {
        id: 'chat_model',
        label: 'Chat Model',
        description: 'LLM for answering queries',
        type: 'text',
        default: '',
        required: true,
        bindings: [
          { nodeId: 'qs3_5', configKey: 'model_name' },
        ],
      },
    ],
    nodes: [
      tNode('qs3_1', 'local_file_loader', 'Local File Loader', 'external', 'FileInput', TPL_ACCENT.external,
        { x: 80, y: 200 }, { file_path: '', format: 'auto' }),
      tNode('qs3_2', 'text_chunker', 'Text Chunker', 'data', 'Scissors', TPL_ACCENT.data,
        { x: 360, y: 200 }, { chunk_size: 1000, chunk_overlap: 200, strategy: 'recursive' }),
      tNode('qs3_3', 'embedding_generator', 'Embedding Generator', 'inference', 'Hash', TPL_ACCENT.inference,
        { x: 640, y: 200 }, { model_name: 'sentence-transformers/all-MiniLM-L6-v2' }),
      tNode('qs3_4', 'vector_store_build', 'Vector Store Builder', 'embedding', 'Database', TPL_ACCENT.embedding,
        { x: 920, y: 200 }, { store_type: 'chroma', collection_name: 'blueprint_rag' }),
      tNode('qs3_5', 'model_selector', 'Chat Model', 'model', 'Cpu', TPL_ACCENT.model,
        { x: 920, y: 400 }, { model_name: '', source: 'ollama' }),
      tNode('qs3_6', 'rag_pipeline', 'RAG Pipeline', 'agents', 'Search', TPL_ACCENT.agents,
        { x: 1200, y: 300 }, { top_k: 5, max_tokens: 1024 }),
    ],
    edges: [
      tEdge('qs3_e1', 'qs3_1', 'qs3_2', 'dataset', 'dataset', '#22D3EE'),
      tEdge('qs3_e2', 'qs3_2', 'qs3_3', 'dataset', 'dataset', '#22D3EE'),
      tEdge('qs3_e3', 'qs3_3', 'qs3_4', 'embedding', 'embedding', '#FB7185'),
      tEdge('qs3_e4', 'qs3_4', 'qs3_6', 'config', 'config', '#F97316'),
      tEdge('qs3_e5', 'qs3_5', 'qs3_6', 'model', 'model', '#A78BFA'),
    ],
  },

  // ── QS4. Merge Two Models ──────────────────────────────────
  {
    id: 'qs-merge-models',
    name: 'Merge Two Models',
    description:
      'Select two models, merge them with SLERP interpolation, evaluate the result, and format a comparison report.',
    icon: 'GitMerge',
    category: 'model',
    blockCount: 5,
    difficulty: 'intermediate',
    estimatedTime: '15 min',
    variables: [
      {
        id: 'model_a',
        label: 'Model A',
        description: 'First model to merge',
        type: 'text',
        default: '',
        required: true,
        bindings: [
          { nodeId: 'qs4_1', configKey: 'model_name' },
        ],
      },
      {
        id: 'model_b',
        label: 'Model B',
        description: 'Second model to merge',
        type: 'text',
        default: '',
        required: true,
        bindings: [
          { nodeId: 'qs4_2', configKey: 'model_name' },
        ],
      },
      {
        id: 'merge_ratio',
        label: 'Merge Ratio',
        description: 'Interpolation factor (0 = all A, 1 = all B)',
        type: 'number',
        default: 0.5,
        required: false,
        bindings: [
          { nodeId: 'qs4_3', configKey: 't' },
        ],
      },
    ],
    nodes: [
      tNode('qs4_1', 'model_selector', 'Model A', 'model', 'Cpu', TPL_ACCENT.model,
        { x: 80, y: 100 }, { model_name: '', source: 'huggingface' }),
      tNode('qs4_2', 'model_selector', 'Model B', 'model', 'Cpu', TPL_ACCENT.model,
        { x: 80, y: 350 }, { model_name: '', source: 'huggingface' }),
      tNode('qs4_3', 'slerp_merge', 'SLERP Merge', 'model', 'GitMerge', TPL_ACCENT.model,
        { x: 400, y: 225 }, { t: 0.5, output_format: 'safetensors' }),
      tNode('qs4_4', 'lm_eval_harness', 'LM Eval Harness', 'metrics', 'ClipboardCheck', TPL_ACCENT.metrics,
        { x: 720, y: 225 }, { tasks: 'hellaswag,arc_easy', num_fewshot: 0, batch_size: 'auto' }),
      tNode('qs4_5', 'results_formatter', 'Results Formatter', 'metrics', 'FileOutput', TPL_ACCENT.metrics,
        { x: 1040, y: 225 }, { format: 'csv', include_config: true }),
    ],
    edges: [
      tEdge('qs4_e1', 'qs4_1', 'qs4_3', 'model', 'model_a', '#A78BFA'),
      tEdge('qs4_e2', 'qs4_2', 'qs4_3', 'model', 'model_b', '#A78BFA'),
      tEdge('qs4_e3', 'qs4_3', 'qs4_4', 'model', 'model', '#A78BFA'),
      tEdge('qs4_e4', 'qs4_4', 'qs4_5', 'metrics', 'metrics', '#34D399'),
    ],
  },

  // ── QS5. Train, Evaluate & Publish ─────────────────────────
  {
    id: 'qs-train-eval-publish',
    name: 'Train, Evaluate & Publish',
    description:
      'Full pipeline: load data, fine-tune with LoRA, evaluate, format results, and push the trained model to HuggingFace Hub.',
    icon: 'Rocket',
    category: 'training',
    blockCount: 7,
    difficulty: 'advanced',
    estimatedTime: '30 min',
    variables: [
      {
        id: 'dataset_name',
        label: 'Dataset',
        description: 'HuggingFace dataset ID',
        type: 'text',
        default: '',
        required: true,
        bindings: [
          { nodeId: 'qs5_1', configKey: 'dataset_name' },
        ],
      },
      {
        id: 'base_model',
        label: 'Base Model',
        description: 'Model to fine-tune',
        type: 'text',
        default: '',
        required: true,
        bindings: [
          { nodeId: 'qs5_3', configKey: 'model_name' },
        ],
      },
      {
        id: 'hf_token',
        label: 'HF Token',
        description: 'HuggingFace API token for pushing',
        type: 'text',
        default: '',
        required: true,
        bindings: [
          { nodeId: 'qs5_7', configKey: 'token' },
        ],
      },
      {
        id: 'repo_id',
        label: 'Repo ID',
        description: 'HuggingFace repo to push to (e.g. username/model-name)',
        type: 'text',
        default: '',
        required: true,
        bindings: [
          { nodeId: 'qs5_7', configKey: 'repo_id' },
        ],
      },
    ],
    nodes: [
      tNode('qs5_1', 'huggingface_loader', 'HuggingFace Loader', 'external', 'Download', TPL_ACCENT.external,
        { x: 80, y: 200 }, { dataset_name: '', split: 'train', max_samples: 10000 }),
      tNode('qs5_2', 'train_val_test_split', 'Train/Val/Test Split', 'data', 'Split', TPL_ACCENT.data,
        { x: 360, y: 200 }, { train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1, seed: 42 }),
      tNode('qs5_3', 'lora_finetuning', 'LoRA Fine-Tuning', 'training', 'Zap', TPL_ACCENT.training,
        { x: 640, y: 200 }, { model_name: '', r: 16, alpha: 32, lr: 0.0001, epochs: 3, batch_size: 4 }),
      tNode('qs5_4', 'lm_eval_harness', 'LM Eval Harness', 'metrics', 'ClipboardCheck', TPL_ACCENT.metrics,
        { x: 920, y: 100 }, { tasks: 'hellaswag,arc_easy,mmlu', num_fewshot: 0, batch_size: 'auto' }),
      tNode('qs5_5', 'results_formatter', 'Results Formatter', 'metrics', 'FileOutput', TPL_ACCENT.metrics,
        { x: 1200, y: 100 }, { format: 'csv', include_config: true }),
      tNode('qs5_6', 'save_model', 'Save Model', 'utilities', 'Save', TPL_ACCENT.utilities,
        { x: 920, y: 350 }, { output_dir: './output/model' }),
      tNode('qs5_7', 'hf_hub_push', 'Push to HF Hub', 'external', 'Upload', TPL_ACCENT.external,
        { x: 1200, y: 350 }, { repo_id: '', token: '', private: false }),
    ],
    edges: [
      tEdge('qs5_e1', 'qs5_1', 'qs5_2', 'dataset', 'dataset', '#22D3EE'),
      tEdge('qs5_e2', 'qs5_2', 'qs5_3', 'train', 'dataset', '#22D3EE'),
      tEdge('qs5_e3', 'qs5_3', 'qs5_4', 'model', 'model', '#A78BFA'),
      tEdge('qs5_e4', 'qs5_4', 'qs5_5', 'metrics', 'metrics', '#34D399'),
      tEdge('qs5_e5', 'qs5_3', 'qs5_6', 'model', 'model', '#A78BFA'),
      tEdge('qs5_e6', 'qs5_6', 'qs5_7', 'artifact', 'artifact', '#38BDF8'),
    ],
  },

  // ── QS6. Synthetic Data Generation ────────────────────────
  {
    id: 'qs-synthetic-data',
    name: 'Synthetic Data Generation',
    description:
      'Generate synthetic training data: start with seed examples, use an LLM to produce variations, filter for quality, and export a clean dataset.',
    icon: 'Sparkles',
    category: 'data',
    blockCount: 5,
    difficulty: 'intermediate',
    estimatedTime: '10 min',
    variables: [
      {
        id: 'seed_data',
        label: 'Seed Dataset',
        description: 'HuggingFace dataset with seed examples',
        type: 'text',
        default: '',
        required: true,
        bindings: [{ nodeId: 'qs6_1', configKey: 'dataset_name' }],
      },
      {
        id: 'gen_model',
        label: 'Generator Model',
        description: 'LLM to generate synthetic samples',
        type: 'text',
        default: '',
        required: true,
        bindings: [{ nodeId: 'qs6_2', configKey: 'model_name' }],
      },
    ],
    nodes: [
      tNode('qs6_1', 'huggingface_loader', 'Seed Data', 'source', 'Download', TPL_ACCENT.external,
        { x: 80, y: 200 }, { dataset_name: '', split: 'train', max_samples: 500 }),
      tNode('qs6_2', 'synthetic_data_gen', 'Generate Variations', 'data', 'Sparkles', TPL_ACCENT.data,
        { x: 360, y: 200 }, { model_name: '', num_samples: 5000, temperature: 0.9 }),
      tNode('qs6_3', 'filter_sample', 'Quality Filter', 'data', 'Filter', TPL_ACCENT.data,
        { x: 640, y: 200 }, { strategy: 'quality_score', min_score: 0.7 }),
      tNode('qs6_4', 'data_augmentation', 'Augment', 'data', 'Shuffle', TPL_ACCENT.data,
        { x: 920, y: 200 }, { strategy: 'synonym_swap', augmentation_factor: 2 }),
      tNode('qs6_5', 'data_export', 'Export Dataset', 'endpoints', 'Download', TPL_ACCENT.endpoints,
        { x: 1200, y: 200 }, { format: 'jsonl', output_path: '' }),
    ],
    edges: [
      tEdge('qs6_e1', 'qs6_1', 'qs6_2', 'dataset', 'dataset', '#22D3EE'),
      tEdge('qs6_e2', 'qs6_2', 'qs6_3', 'dataset', 'dataset', '#22D3EE'),
      tEdge('qs6_e3', 'qs6_3', 'qs6_4', 'dataset', 'dataset', '#22D3EE'),
      tEdge('qs6_e4', 'qs6_4', 'qs6_5', 'dataset', 'dataset', '#22D3EE'),
    ],
  },

  // ── QS7. Benchmark Suite ──────────────────────────────────
  {
    id: 'qs-benchmark-suite',
    name: 'Benchmark Suite',
    description:
      'Run a comprehensive benchmark suite: evaluate a model on MMLU, LM Eval Harness tasks, toxicity, and bias — then compile all results into a report.',
    icon: 'Award',
    category: 'evaluation',
    blockCount: 7,
    difficulty: 'intermediate',
    estimatedTime: '20 min',
    variables: [
      {
        id: 'model_name',
        label: 'Model',
        description: 'Model to benchmark',
        type: 'text',
        default: '',
        required: true,
        bindings: [{ nodeId: 'qs7_1', configKey: 'model_name' }],
      },
    ],
    nodes: [
      tNode('qs7_1', 'model_selector', 'Select Model', 'data', 'Box', TPL_ACCENT.model,
        { x: 80, y: 250 }, { model_name: '', source: 'huggingface' }),
      tNode('qs7_2', 'mmlu_eval', 'MMLU', 'evaluation', 'ClipboardCheck', TPL_ACCENT.metrics,
        { x: 400, y: 80 }, { num_fewshot: 5 }),
      tNode('qs7_3', 'lm_eval_harness', 'LM Eval Harness', 'evaluation', 'ClipboardCheck', TPL_ACCENT.metrics,
        { x: 400, y: 230 }, { tasks: 'hellaswag,arc_easy,winogrande', num_fewshot: 0, batch_size: 'auto' }),
      tNode('qs7_4', 'toxicity_eval', 'Toxicity Check', 'evaluation', 'ShieldAlert', TPL_ACCENT.metrics,
        { x: 400, y: 380 }, {}),
      tNode('qs7_5', 'bias_fairness_eval', 'Bias & Fairness', 'evaluation', 'Scale', TPL_ACCENT.metrics,
        { x: 400, y: 530 }, {}),
      tNode('qs7_6', 'results_formatter', 'Compile Results', 'output', 'FileOutput', TPL_ACCENT.metrics,
        { x: 720, y: 250 }, { format: 'json', include_config: true }),
      tNode('qs7_7', 'report_generator', 'Generate Report', 'output', 'FileText', TPL_ACCENT.metrics,
        { x: 1000, y: 250 }, { format: 'html' }),
    ],
    edges: [
      tEdge('qs7_e1', 'qs7_1', 'qs7_2', 'model', 'model', '#A78BFA'),
      tEdge('qs7_e2', 'qs7_1', 'qs7_3', 'model', 'model', '#A78BFA'),
      tEdge('qs7_e3', 'qs7_1', 'qs7_4', 'model', 'model', '#A78BFA'),
      tEdge('qs7_e4', 'qs7_1', 'qs7_5', 'model', 'model', '#A78BFA'),
      tEdge('qs7_e5', 'qs7_2', 'qs7_6', 'metrics', 'metrics', '#34D399'),
      tEdge('qs7_e6', 'qs7_3', 'qs7_6', 'metrics', 'metrics', '#34D399'),
      tEdge('qs7_e7', 'qs7_4', 'qs7_6', 'metrics', 'metrics', '#34D399'),
      tEdge('qs7_e8', 'qs7_5', 'qs7_6', 'metrics', 'metrics', '#34D399'),
      tEdge('qs7_e9', 'qs7_6', 'qs7_7', 'report', 'report', '#34D399'),
    ],
  },

  // ── QS8. Model Merge & Compare ────────────────────────────
  {
    id: 'qs-merge-compare',
    name: 'Merge & Compare Models',
    description:
      'Merge two models using SLERP, then compare the merged model against both originals on a benchmark to see if the merge improved performance.',
    icon: 'GitMerge',
    category: 'merge',
    blockCount: 7,
    difficulty: 'advanced',
    estimatedTime: '25 min',
    variables: [
      {
        id: 'model_a',
        label: 'Model A',
        description: 'First model to merge',
        type: 'text',
        default: '',
        required: true,
        bindings: [{ nodeId: 'qs8_1', configKey: 'model_name' }],
      },
      {
        id: 'model_b',
        label: 'Model B',
        description: 'Second model to merge',
        type: 'text',
        default: '',
        required: true,
        bindings: [{ nodeId: 'qs8_2', configKey: 'model_name' }],
      },
    ],
    nodes: [
      tNode('qs8_1', 'model_selector', 'Model A', 'data', 'Box', TPL_ACCENT.model,
        { x: 80, y: 120 }, { model_name: '', source: 'huggingface' }),
      tNode('qs8_2', 'model_selector', 'Model B', 'data', 'Box', TPL_ACCENT.model,
        { x: 80, y: 350 }, { model_name: '', source: 'huggingface' }),
      tNode('qs8_3', 'slerp_merge', 'SLERP Merge', 'merge', 'GitMerge', TPL_ACCENT.interventions,
        { x: 400, y: 230 }, { ratio: 0.5 }),
      tNode('qs8_4', 'model_comparison', 'Compare All Three', 'inference', 'BarChart2', TPL_ACCENT.inference,
        { x: 720, y: 230 }, {}),
      tNode('qs8_5', 'lm_eval_harness', 'Benchmark', 'evaluation', 'ClipboardCheck', TPL_ACCENT.metrics,
        { x: 1000, y: 120 }, { tasks: 'hellaswag,arc_easy', num_fewshot: 0, batch_size: 'auto' }),
      tNode('qs8_6', 'results_formatter', 'Format Results', 'output', 'FileOutput', TPL_ACCENT.metrics,
        { x: 1000, y: 350 }, { format: 'csv', include_config: true }),
      tNode('qs8_7', 'save_model', 'Save Merged', 'endpoints', 'Save', TPL_ACCENT.utilities,
        { x: 720, y: 430 }, { output_dir: './output/merged_model' }),
    ],
    edges: [
      tEdge('qs8_e1', 'qs8_1', 'qs8_3', 'model', 'model_a', '#A78BFA'),
      tEdge('qs8_e2', 'qs8_2', 'qs8_3', 'model', 'model_b', '#A78BFA'),
      tEdge('qs8_e3', 'qs8_3', 'qs8_4', 'model', 'model', '#A78BFA'),
      tEdge('qs8_e4', 'qs8_4', 'qs8_5', 'model', 'model', '#A78BFA'),
      tEdge('qs8_e5', 'qs8_5', 'qs8_6', 'metrics', 'metrics', '#34D399'),
      tEdge('qs8_e6', 'qs8_3', 'qs8_7', 'model', 'model', '#A78BFA'),
    ],
  },

  // ── QS9. DPO Alignment Pipeline ───────────────────────────
  {
    id: 'qs-dpo-alignment',
    name: 'DPO Alignment',
    description:
      'Align a model with human preferences using Direct Preference Optimization: load preference data, train with DPO, then evaluate on toxicity and bias.',
    icon: 'Target',
    category: 'training',
    blockCount: 6,
    difficulty: 'advanced',
    estimatedTime: '30 min',
    variables: [
      {
        id: 'preference_data',
        label: 'Preference Dataset',
        description: 'Dataset with chosen/rejected pairs',
        type: 'text',
        default: '',
        required: true,
        bindings: [{ nodeId: 'qs9_1', configKey: 'dataset_name' }],
      },
      {
        id: 'base_model',
        label: 'Base Model',
        description: 'Model to align',
        type: 'text',
        default: '',
        required: true,
        bindings: [{ nodeId: 'qs9_3', configKey: 'model_name' }],
      },
    ],
    nodes: [
      tNode('qs9_1', 'huggingface_loader', 'Preference Data', 'source', 'Download', TPL_ACCENT.external,
        { x: 80, y: 200 }, { dataset_name: '', split: 'train' }),
      tNode('qs9_2', 'train_val_test_split', 'Split Data', 'data', 'Split', TPL_ACCENT.data,
        { x: 360, y: 200 }, { train_ratio: 0.9, val_ratio: 0.1, test_ratio: 0, seed: 42 }),
      tNode('qs9_3', 'dpo_alignment', 'DPO Training', 'training', 'Target', TPL_ACCENT.training,
        { x: 640, y: 200 }, { model_name: '', lr: 5e-5, epochs: 1, batch_size: 4, beta: 0.1 }),
      tNode('qs9_4', 'toxicity_eval', 'Toxicity Eval', 'evaluation', 'ShieldAlert', TPL_ACCENT.metrics,
        { x: 920, y: 120 }, {}),
      tNode('qs9_5', 'bias_fairness_eval', 'Bias Eval', 'evaluation', 'Scale', TPL_ACCENT.metrics,
        { x: 920, y: 320 }, {}),
      tNode('qs9_6', 'results_formatter', 'Results', 'output', 'FileOutput', TPL_ACCENT.metrics,
        { x: 1200, y: 200 }, { format: 'json', include_config: true }),
    ],
    edges: [
      tEdge('qs9_e1', 'qs9_1', 'qs9_2', 'dataset', 'dataset', '#22D3EE'),
      tEdge('qs9_e2', 'qs9_2', 'qs9_3', 'train', 'dataset', '#22D3EE'),
      tEdge('qs9_e3', 'qs9_3', 'qs9_4', 'model', 'model', '#A78BFA'),
      tEdge('qs9_e4', 'qs9_3', 'qs9_5', 'model', 'model', '#A78BFA'),
      tEdge('qs9_e5', 'qs9_4', 'qs9_6', 'metrics', 'metrics', '#34D399'),
      tEdge('qs9_e6', 'qs9_5', 'qs9_6', 'metrics', 'metrics', '#34D399'),
    ],
  },
]
