/** Block-level search aliases for natural language search */
export const BLOCK_ALIASES: Record<string, string[]> = {
  // Source blocks
  huggingface_loader: ['download dataset', 'hf dataset', 'hugging face', 'load data', 'import data'],
  huggingface_model: ['download model', 'hf model', 'hugging face', 'load model', 'pretrained'],
  text_input: ['text', 'prompt', 'input text', 'write', 'manual input'],
  local_file_loader: ['file', 'csv', 'jsonl', 'parquet', 'local data', 'upload'],
  api_data_fetcher: ['api', 'rest', 'http', 'fetch', 'endpoint', 'web data'],
  web_scraper: ['scrape', 'crawl', 'website', 'html', 'extract web'],
  sql_query: ['sql', 'database', 'query', 'postgres', 'mysql', 'sqlite'],
  document_ingestion: ['document', 'pdf', 'docx', 'ingest', 'parse document'],
  synthetic_data_gen: ['synthetic', 'generate data', 'augment', 'fake data', 'artificial data'],
  config_builder: ['config', 'configuration', 'settings', 'parameters'],
  config_file_loader: ['config file', 'yaml', 'toml', 'load config'],

  // Transform blocks
  filter_sample: ['filter', 'sample', 'subset', 'select rows', 'where'],
  column_transform: ['column', 'rename', 'map', 'transform column', 'feature engineering'],
  data_augmentation: ['augment', 'expand data', 'paraphrase', 'more data', 'oversample'],
  train_val_test_split: ['split', 'divide', 'partition', 'train test', 'validation split', 'holdout'],
  data_preview: ['preview', 'inspect', 'view data', 'head', 'sample data'],
  data_merger: ['merge data', 'join', 'concat', 'combine data', 'union'],
  text_chunker: ['chunk', 'split text', 'segment', 'window', 'tokenize'],
  vector_store_build: ['vector store', 'index', 'faiss', 'chromadb', 'vector db', 'embeddings store'],
  text_concatenator: ['concatenate', 'join text', 'combine text', 'append'],

  // Training blocks
  lora_finetuning: ['lora', 'fine-tune', 'finetune', 'adapt', 'customize model', 'peft'],
  qlora_finetuning: ['qlora', 'quantized training', '4bit', '4-bit', 'efficient training'],
  full_finetuning: ['full training', 'supervised', 'sft', 'full fine-tune'],
  dpo_alignment: ['dpo', 'alignment', 'preference', 'rlhf', 'human feedback', 'align'],
  sft_training: ['sft', 'supervised fine-tuning', 'instruction tuning'],
  rl_ppo: ['rl', 'ppo', 'reinforcement', 'reward', 'policy optimization'],
  distillation: ['distill', 'compress', 'student teacher', 'knowledge distillation', 'smaller model'],
  curriculum_training: ['curriculum', 'progressive', 'staged training', 'difficulty order'],
  model_quantization: ['quantize', 'compress', 'gptq', 'awq', 'int8', 'int4', 'smaller model'],
  model_pruning: ['prune', 'sparse', 'remove weights', 'slim model'],
  reward_model_training: ['reward model', 'rm training', 'preference model'],

  // Inference blocks
  llm_inference: ['chat', 'talk', 'prompt', 'generate', 'ask', 'respond', 'completion', 'gpt', 'llm', 'language model', 'run model', 'ollama', 'mlx', 'gguf', 'local model', 'apple silicon', 'quantized model'],
  batch_inference: ['bulk', 'batch', 'mass generate', 'multiple prompts', 'batch run'],
  embeddings: ['embed', 'vector', 'vectorize', 'similarity', 'semantic search'],
  text_generation: ['generate text', 'write', 'compose', 'creative writing'],
  structured_output: ['json output', 'structured', 'schema', 'typed output', 'format output'],
  vllm_inference: ['vllm', 'fast inference', 'high throughput', 'optimized inference'],

  // Evaluate blocks
  mmlu_eval: ['mmlu', 'benchmark', 'evaluate', 'test model', 'accuracy', 'knowledge test'],
  lm_eval_harness: ['eval harness', 'leaderboard', 'benchmark suite', 'eleuther'],
  human_eval: ['human eval', 'code generation', 'coding benchmark', 'pass@k'],
  toxicity_eval: ['toxic', 'safety', 'harmful', 'content filter', 'moderation'],
  factuality_checker: ['factuality', 'fact check', 'hallucination', 'grounded'],
  perplexity_eval: ['perplexity', 'language quality', 'fluency'],
  custom_eval: ['custom scoring', 'user eval', 'scoring function', 'grade', 'custom metric'],

  // Merge blocks
  slerp_merge: ['slerp', 'merge models', 'combine models', 'blend', 'model soup', 'interpolate'],
  ties_merge: ['ties', 'trim merge', 'task arithmetic'],
  dare_merge: ['dare', 'drop merge', 'random merge'],
  frankenmerge: ['franken', 'layer swap', 'frankenstein', 'layer merge'],
  mergekit_merge: ['mergekit', 'merge toolkit', 'advanced merge'],

  // Agent blocks
  agent_loop: ['agent', 'autonomous', 'tool use', 'react agent', 'agentic'],
  multi_turn_agent: ['multi-turn', 'conversation', 'dialogue agent', 'chat agent'],
  retrieval: ['rag', 'retrieve', 'search documents', 'context retrieval', 'knowledge base'],
  tool_router: ['tool', 'router', 'function calling', 'tool selection'],
  multi_step_chain: ['chain', 'pipeline', 'sequential', 'multi-step', 'workflow'],
  plan_and_execute: ['plan', 'execute', 'planning agent', 'task decomposition'],
  evaluator_agent: ['evaluator', 'judge', 'auto eval', 'llm judge'],
  critic_agent: ['critic', 'feedback', 'self-critique', 'reflection'],
  semantic_search: ['semantic', 'similarity search', 'nearest neighbor', 'knn'],

  // Flow blocks
  conditional_branch: ['if', 'branch', 'condition', 'switch', 'route', 'decision'],
  loop_iterator: ['loop', 'iterate', 'repeat', 'for each', 'batch process', 'map'],
  aggregator: ['aggregate', 'collect', 'gather', 'reduce', 'combine results'],
  parallel_fan_out: ['parallel', 'fan out', 'concurrent', 'split work'],
  python_runner: ['code', 'script', 'python', 'custom logic', 'custom code', 'execute'],
  data_exporter: ['export', 'save', 'json', 'csv', 'jsonl', 'tsv', 'download data', 'output file', 'write file'],
  results_formatter: ['format', 'output', 'display', 'render results'],
  report_generator: ['report', 'summary', 'document', 'write report'],
  artifact_packager: ['package', 'artifact', 'export', 'bundle', 'save'],
  model_card_writer: ['model card', 'documentation', 'readme', 'model info'],
  leaderboard_publisher: ['leaderboard', 'publish', 'ranking', 'compare models'],
  artifact_viewer: ['view', 'inspect', 'browse', 'artifact viewer'],
  knowledge_graph_builder: ['knowledge graph', 'graph', 'entities', 'relations', 'ontology'],
  // Intervention blocks
  manual_review: ['manual review', 'human scoring', 'rubric', 'annotate', 'score', 'quality review'],
  notification_hub: ['telegram', 'slack', 'email alert', 'messaging', 'multi-channel', 'notification hub'],
  agentic_review_loop: ['agentic review', 'LLM judge', 'iterative', 'self-critique', 'auto-review', 'refinement loop'],
  ab_split_test: ['A/B test', 'split test', 'comparison', 'experiment', 'bucket test', 'variant'],
  quality_gate: ['quality check', 'threshold', 'pass/fail', 'validation gate', 'metric check'],
  rollback_point: ['rollback', 'snapshot', 'undo', 'recovery', 'restore point', 'state save'],
  // Save blocks
  save_csv: ['export CSV', 'write CSV', 'save spreadsheet', 'CSV output'],
  save_txt: ['export text', 'write text', 'save TXT', 'plain text export'],
  save_json: ['export JSON', 'write JSON', 'JSONL output', 'save structured'],
  save_parquet: ['export Parquet', 'write Parquet', 'columnar export', 'arrow export'],
  save_pdf: ['export PDF', 'write PDF', 'PDF report', 'document export'],
  save_model: ['export model', 'save weights', 'save checkpoint', 'serialize model'],
  save_embeddings: ['export embeddings', 'save vectors', 'vector export', 'FAISS export'],
  save_yaml: ['export YAML', 'write YAML', 'config export', 'save config'],
}

/** Category-level aliases */
export const CATEGORY_ALIASES: Record<string, string[]> = {
  external: ['load', 'import', 'input', 'file', 'download', 'fetch', 'api', 'cloud', 'export', 'connect'],
  data: ['clean', 'process', 'filter', 'map', 'convert', 'prepare', 'wrangle', 'transform', 'split', 'chunk'],
  model: ['merge', 'combine', 'blend', 'quantize', 'select', 'weights', 'package', 'load model'],
  inference: ['run', 'generate', 'predict', 'chat', 'infer', 'prompt', 'llm', 'batch', 'rerank', 'completion', 'translate', 'summarize', 'classify'],
  training: ['train', 'fine-tune', 'learn', 'optimize', 'fit', 'finetune', 'lora', 'qlora', 'dpo'],
  metrics: ['eval', 'test', 'benchmark', 'score', 'assess', 'measure', 'judge', 'evaluate', 'report'],
  embedding: ['embed', 'vector', 'similarity', 'vectorize', 'rag', 'index', 'faiss', 'chromadb'],
  utilities: ['control', 'logic', 'loop', 'branch', 'parallel', 'code', 'script', 'flow', 'gate'],
  agents: ['agent', 'tool', 'autonomous', 'chain', 'workflow', 'agentic', 'orchestrate', 'debate'],
  interventions: ['review', 'approve', 'human', 'quality', 'gate', 'notify', 'rollback', 'split', 'test', 'intervention'],
  save: ['save', 'export', 'write', 'output', 'persist', 'csv', 'json', 'parquet', 'pdf', 'yaml'],
}
