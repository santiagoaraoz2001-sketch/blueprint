/**
 * LLM system prompts for agentic workflow generation.
 * Extracted from agentStore to keep store logic clean and prompts maintainable.
 */

export const WORKFLOW_GENERATION_PROMPT = `You are an ML pipeline designer for the Specific Labs Blueprint app. Given a research plan, generate a pipeline as a JSON object with "nodes" and "edges" arrays.

Available block types (use these exact type values):
DATA: huggingface-loader, local-file-loader, api-data-fetcher, synthetic-data-gen, web-scraper, sql-query, filter-sample, column-transform, data-augmentation, train-val-test-split, data-preview, data-merger
TRAINING: lora-fine-tuning, qlora-fine-tuning, full-fine-tuning, dpo-alignment, rlhf-ppo, continued-pre-training, knowledge-distillation, curriculum-training, hyperparam-sweep, checkpoint-selector
EVALUATION: lm-eval-harness, custom-benchmark, mmlu-eval, humaneval, toxicity-eval, factuality-checker, latency-profiler, ab-comparator
MERGE: mergekit-merge, slerp-merge, ties-merge, dare-merge, frankenmerge
AGENTS: agent-orchestrator, tool-registry, chain-of-thought, multi-agent-debate, agent-memory, agent-evaluator, retrieval-agent, code-agent
INFERENCE: batch-inference, streaming-server, quantize-model, prompt-template, embedding-generator, reranker
OUTPUT: results-formatter, artifact-packager, report-generator, model-card-writer, leaderboard-publisher
FLOW: conditional-branch, loop-iterator, parallel-fan-out, aggregator, checkpoint-gate, error-handler

Node format: { "id": "block_N", "type": "blockNode", "position": {"x": N, "y": N}, "data": {"type": "BLOCK_TYPE", "label": "DISPLAY NAME", "category": "CATEGORY", "icon": "lucide-icon", "accent": "#color", "config": {}, "status": "idle", "progress": 0} }

Edge format: { "id": "edge_N", "source": "block_N", "target": "block_M", "sourceHandle": "output-PORT", "targetHandle": "input-PORT", "type": "smoothstep", "animated": true }

Arrange nodes left-to-right with ~250px horizontal spacing. Use logical port connections matching data types (dataset, model, metrics, text, config, agent, embedding, artifact).

RESPOND WITH ONLY VALID JSON. No markdown, no explanation, just the JSON object.`

/** Default LLM generation options */
export const LLM_DEFAULTS = {
  temperature: 0.3,
  timeoutMs: 120_000,
  endpoints: {
    ollama: import.meta.env.VITE_OLLAMA_URL || 'http://localhost:11434',
    mlx: import.meta.env.VITE_MLX_URL || 'http://localhost:8080',
  } as Record<string, string>,
} as const

/** Demo mode sample workflow result */
export const DEMO_WORKFLOW = {
  nodes: [
    {
      id: 'gen_1',
      type: 'blockNode',
      position: { x: 50, y: 100 },
      data: {
        type: 'huggingface-loader',
        label: 'Load Dataset',
        category: 'data',
        icon: 'Download',
        accent: '#4af6c3',
        config: { dataset_name: 'sample-dataset' },
        status: 'idle',
        progress: 0,
      },
    },
    {
      id: 'gen_2',
      type: 'blockNode',
      position: { x: 300, y: 100 },
      data: {
        type: 'train-val-test-split',
        label: 'Split Data',
        category: 'data',
        icon: 'Split',
        accent: '#4af6c3',
        config: { train_ratio: 0.8, val_ratio: 0.1, test_ratio: 0.1 },
        status: 'idle',
        progress: 0,
      },
    },
    {
      id: 'gen_3',
      type: 'blockNode',
      position: { x: 550, y: 100 },
      data: {
        type: 'lora-fine-tuning',
        label: 'LoRA Training',
        category: 'training',
        icon: 'Cpu',
        accent: '#6C9EFF',
        config: { rank: 16, alpha: 32, epochs: 3 },
        status: 'idle',
        progress: 0,
      },
    },
    {
      id: 'gen_4',
      type: 'blockNode',
      position: { x: 800, y: 100 },
      data: {
        type: 'mmlu-eval',
        label: 'Evaluate',
        category: 'evaluation',
        icon: 'ClipboardCheck',
        accent: '#B87EFF',
        config: { subjects: 'all' },
        status: 'idle',
        progress: 0,
      },
    },
  ],
  edges: [
    { id: 'gen_e1', source: 'gen_1', target: 'gen_2', sourceHandle: 'output-dataset', targetHandle: 'input-dataset', type: 'smoothstep', animated: true },
    { id: 'gen_e2', source: 'gen_2', target: 'gen_3', sourceHandle: 'output-train', targetHandle: 'input-dataset', type: 'smoothstep', animated: true },
    { id: 'gen_e3', source: 'gen_3', target: 'gen_4', sourceHandle: 'output-model', targetHandle: 'input-model', type: 'smoothstep', animated: true },
  ],
}
