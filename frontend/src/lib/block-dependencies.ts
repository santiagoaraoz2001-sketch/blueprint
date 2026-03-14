/**
 * Maps block type IDs to their pip package dependencies.
 * Used for generating requirements.txt files from visual ML pipelines.
 */

export const BLOCK_DEPENDENCIES: Record<string, string[]> = {
  // ─── Source / External ───────────────────────────────────────────────
  huggingface_loader: ["datasets", "huggingface_hub"],
  huggingface_model: ["transformers", "huggingface_hub", "accelerate"],
  local_file_loader: ["pandas", "pyarrow"],
  api_data_fetcher: ["requests", "aiohttp"],
  web_scraper: ["beautifulsoup4", "requests"],
  sql_query: ["sqlalchemy"],
  document_ingestion: ["pypdf", "python-docx"],
  synthetic_data_gen: ["faker"],
  text_input: [],
  config_builder: ["pyyaml"],
  config_file_loader: ["pyyaml", "toml"],

  // ─── Data / Transform ────────────────────────────────────────────────
  filter_sample: ["pandas"],
  column_transform: ["pandas"],
  data_augmentation: ["nlpaug"],
  train_val_test_split: ["scikit-learn", "pandas"],
  data_preview: ["pandas"],
  data_merger: ["pandas"],
  text_chunker: ["langchain-text-splitters"],
  text_concatenator: [],
  prompt_template: ["jinja2"],

  // ─── Training ────────────────────────────────────────────────────────
  lora_finetuning: [
    "peft",
    "transformers",
    "torch",
    "datasets",
    "accelerate",
    "bitsandbytes",
  ],
  qlora_finetuning: [
    "peft",
    "transformers",
    "torch",
    "datasets",
    "accelerate",
    "bitsandbytes",
  ],
  full_finetuning: ["transformers", "torch", "datasets", "accelerate"],
  dpo_alignment: ["trl", "transformers", "torch", "datasets"],
  rlhf_ppo: ["trl", "transformers", "torch", "datasets"],
  distillation: ["transformers", "torch"],
  curriculum_training: ["transformers", "torch", "datasets"],
  reward_model_trainer: ["trl", "transformers", "torch"],
  continued_pretraining: [
    "transformers",
    "torch",
    "datasets",
    "accelerate",
  ],
  hyperparameter_sweep: ["optuna", "transformers", "torch"],
  checkpoint_selector: [],

  // ─── Model / Inference ───────────────────────────────────────────────
  llm_inference: ["transformers", "torch"],
  quantize_model: ["auto-gptq", "transformers", "torch"],
  reranker: ["sentence-transformers", "torch"],
  slerp_merge: ["mergekit"],
  ties_merge: ["mergekit"],
  dare_merge: ["mergekit"],
  frankenmerge: ["mergekit"],
  mergekit_merge: ["mergekit"],

  // ─── Evaluate / Metrics ──────────────────────────────────────────────
  mmlu_eval: ["lm-eval"],
  lm_eval_harness: ["lm-eval"],
  human_eval: ["human-eval"],
  toxicity_eval: ["detoxify"],
  factuality_checker: ["transformers", "torch"],
  custom_eval: [],
  results_formatter: ["pandas"],
  experiment_logger: [],

  // ─── Embedding ───────────────────────────────────────────────────────
  vector_store_build: ["chromadb", "sentence-transformers"],
  embedding_generator: ["sentence-transformers", "torch"],
  embedding_similarity_search: ["faiss-cpu", "numpy"],
  embedding_clustering: ["scikit-learn", "numpy"],
  embedding_visualizer: ["matplotlib", "scikit-learn"],

  // ─── Agents ──────────────────────────────────────────────────────────
  retrieval_agent: ["langchain", "chromadb"],
  agent_orchestrator: ["langchain"],
  agent_evaluator: ["langchain"],
  chain_of_thought: [],
  code_agent: [],
  multi_agent_debate: [],
  tool_registry: [],
  agent_memory: [],
  agent_text_bridge: [],

  // ─── Utilities / Flow ────────────────────────────────────────────────
  conditional_branch: [],
  loop_iterator: [],
  aggregator: [],
  parallel_fan_out: [],
  python_runner: [],
  artifact_viewer: [],

  // ─── Interventions ───────────────────────────────────────────────────
  manual_review: [],
  notification_hub: ["requests"],
  ab_split_test: [],
  quality_gate: [],
  rollback_point: [],
  agentic_review_loop: ["transformers", "torch"],

  // ─── Save ────────────────────────────────────────────────────────────
  save_csv: ["pandas"],
  save_txt: [],
  save_json: [],
  save_parquet: ["pandas", "pyarrow"],
  save_pdf: ["reportlab"],
  save_model: ["safetensors", "torch"],
  save_embeddings: ["numpy", "faiss-cpu"],
  save_yaml: ["pyyaml"],
};

/** Packages always included in every generated requirements file. */
const BASE_DEPENDENCIES: string[] = ["numpy", "tqdm", "torch"];

/**
 * Generate a requirements.txt content string from an array of block type IDs.
 *
 * 1. Collects all pip dependencies for the given block types.
 * 2. Adds base dependencies (numpy, tqdm, torch).
 * 3. Deduplicates entries.
 * 4. Sorts alphabetically.
 * 5. Returns a newline-separated string with a header comment.
 *
 * Unknown block type IDs are silently ignored.
 */
export function generateRequirements(blockTypes: string[]): string {
  const depsSet = new Set<string>(BASE_DEPENDENCIES);

  for (const blockType of blockTypes) {
    const deps = BLOCK_DEPENDENCIES[blockType];
    if (deps) {
      for (const dep of deps) {
        depsSet.add(dep);
      }
    }
  }

  const sorted = Array.from(depsSet).sort((a, b) =>
    a.toLowerCase().localeCompare(b.toLowerCase()),
  );

  const header = "# Generated by Blueprint — pip install -r requirements.txt";
  return [header, ...sorted].join("\n") + "\n";
}
