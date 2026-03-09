// Demo mode sample data — realistic ML experiment data

export const DEMO_PROJECTS = [
  {
    id: 'demo-proj-1',
    name: 'LLM Fine-Tuning Research',
    description: 'Fine-tuning Llama-3-8B on domain-specific Q&A data using LoRA',
    status: 'active' as const,
    paper_number: 'SL-2025-001',
    created_at: '2025-11-15T10:00:00Z',
    updated_at: '2025-12-01T14:30:00Z',
    pipeline_count: 3,
    run_count: 12,
  },
  {
    id: 'demo-proj-2',
    name: 'Model Merging Experiments',
    description: 'Evaluating SLERP and TIES merge strategies for 7B parameter models',
    status: 'complete' as const,
    paper_number: 'SL-2025-002',
    created_at: '2025-10-01T08:00:00Z',
    updated_at: '2025-11-20T11:00:00Z',
    pipeline_count: 2,
    run_count: 8,
  },
  {
    id: 'demo-proj-3',
    name: 'RAG Pipeline Optimization',
    description: 'Testing retrieval-augmented generation with various embedding models',
    status: 'active' as const,
    paper_number: 'SL-2025-003',
    created_at: '2025-12-01T09:00:00Z',
    updated_at: '2025-12-10T16:00:00Z',
    pipeline_count: 1,
    run_count: 5,
  },
]

export const DEMO_PIPELINE = {
  id: 'demo-pipeline-1',
  name: 'LoRA Fine-Tuning Pipeline',
  definition: {
    nodes: [
      {
        id: 'demo_1',
        type: 'blockNode',
        position: { x: 50, y: 100 },
        data: {
          type: 'huggingface-loader',
          label: 'HuggingFace Loader',
          category: 'data',
          icon: 'database',
          accent: '#4af6c3',
          config: { dataset_name: 'tatsu-lab/alpaca', split: 'train' },
          status: 'complete',
          progress: 1,
        },
      },
      {
        id: 'demo_2',
        type: 'blockNode',
        position: { x: 350, y: 50 },
        data: {
          type: 'train-val-test-split',
          label: 'Train/Val/Test Split',
          category: 'data',
          icon: 'split',
          accent: '#4af6c3',
          config: { train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1 },
          status: 'complete',
          progress: 1,
        },
      },
      {
        id: 'demo_3',
        type: 'blockNode',
        position: { x: 650, y: 100 },
        data: {
          type: 'lora-fine-tuning',
          label: 'LoRA Fine-Tuning',
          category: 'training',
          icon: 'cpu',
          accent: '#6C9EFF',
          config: { base_model: 'meta-llama/Llama-3-8B', rank: 16, alpha: 32, epochs: 3 },
          status: 'running',
          progress: 0.65,
        },
      },
      {
        id: 'demo_4',
        type: 'blockNode',
        position: { x: 950, y: 50 },
        data: {
          type: 'mmlu-eval',
          label: 'MMLU Evaluation',
          category: 'evaluation',
          icon: 'clipboard-check',
          accent: '#B87EFF',
          config: { subjects: 'all', few_shot: 5 },
          status: 'idle',
          progress: 0,
        },
      },
      {
        id: 'demo_5',
        type: 'blockNode',
        position: { x: 950, y: 200 },
        data: {
          type: 'quantize-model',
          label: 'Quantize Model',
          category: 'inference',
          icon: 'minimize-2',
          accent: '#F472B6',
          config: { method: 'GPTQ', bits: 4 },
          status: 'idle',
          progress: 0,
        },
      },
      {
        id: 'demo_6',
        type: 'blockNode',
        position: { x: 1250, y: 100 },
        data: {
          type: 'report-generator',
          label: 'Report Generator',
          category: 'output',
          icon: 'file-text',
          accent: '#FBBF24',
          config: { format: 'markdown', include_charts: true },
          status: 'idle',
          progress: 0,
        },
      },
    ],
    edges: [
      { id: 'demo_e1', source: 'demo_1', target: 'demo_2', sourceHandle: 'output-dataset', targetHandle: 'input-dataset', type: 'smoothstep', animated: true, style: { stroke: '#4af6c3', strokeWidth: 1.5 } },
      { id: 'demo_e2', source: 'demo_2', target: 'demo_3', sourceHandle: 'output-train', targetHandle: 'input-dataset', type: 'smoothstep', animated: true, style: { stroke: '#4af6c3', strokeWidth: 1.5 } },
      { id: 'demo_e3', source: 'demo_3', target: 'demo_4', sourceHandle: 'output-model', targetHandle: 'input-model', type: 'smoothstep', animated: true, style: { stroke: '#6C9EFF', strokeWidth: 1.5 } },
      { id: 'demo_e4', source: 'demo_3', target: 'demo_5', sourceHandle: 'output-model', targetHandle: 'input-model', type: 'smoothstep', animated: true, style: { stroke: '#6C9EFF', strokeWidth: 1.5 } },
      { id: 'demo_e5', source: 'demo_4', target: 'demo_6', sourceHandle: 'output-metrics', targetHandle: 'input-metrics', type: 'smoothstep', animated: true, style: { stroke: '#B87EFF', strokeWidth: 1.5 } },
    ],
  },
}

export const DEMO_RUNS = [
  { id: 'run-1', pipeline_id: 'demo-pipeline-1', status: 'complete', started_at: '2025-12-08T10:00:00Z', completed_at: '2025-12-08T12:30:00Z', metrics: { loss: 0.342, accuracy: 0.847, perplexity: 12.4, mmlu: 0.623 } },
  { id: 'run-2', pipeline_id: 'demo-pipeline-1', status: 'complete', started_at: '2025-12-09T09:00:00Z', completed_at: '2025-12-09T11:45:00Z', metrics: { loss: 0.289, accuracy: 0.871, perplexity: 10.8, mmlu: 0.651 } },
  { id: 'run-3', pipeline_id: 'demo-pipeline-1', status: 'running', started_at: '2025-12-10T08:00:00Z', completed_at: null, metrics: { loss: 0.256, accuracy: 0.883, perplexity: 9.7 } },
  { id: 'run-4', pipeline_id: 'demo-pipeline-1', status: 'failed', started_at: '2025-12-07T14:00:00Z', completed_at: '2025-12-07T14:05:00Z', metrics: {} },
]

export const DEMO_DATASETS = [
  { id: 'ds-1', name: 'alpaca-cleaned', source: 'HuggingFace', rows: 52002, columns: 4, size_mb: 42.3, format: 'parquet' },
  { id: 'ds-2', name: 'code-instructions-122k', source: 'HuggingFace', rows: 122000, columns: 3, size_mb: 89.1, format: 'jsonl' },
  { id: 'ds-3', name: 'medical-qa-v2', source: 'Local', rows: 18500, columns: 5, size_mb: 15.7, format: 'csv' },
]

export const DEMO_PIPELINES_LIST = [
  { id: 'demo-pipeline-1', name: 'LoRA Fine-Tuning Pipeline', block_count: 6, created_at: '2025-12-01', updated_at: '2025-12-10' },
  { id: 'demo-pipeline-2', name: 'RAG Evaluation Pipeline', block_count: 4, created_at: '2025-11-20', updated_at: '2025-12-05' },
  { id: 'demo-pipeline-3', name: 'Model Merge Comparison', block_count: 8, created_at: '2025-10-15', updated_at: '2025-11-28' },
]
