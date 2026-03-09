/**
 * Advanced configuration defaults for blocks that wrap libraries with many parameters.
 * When a user toggles "Advanced Mode", these defaults populate the JSON editor
 * alongside the block's standard config values.
 */

export interface AdvancedConfigSchema {
  type: 'integer' | 'float' | 'string' | 'boolean' | 'array' | 'select'
  description: string
  min?: number
  max?: number
  options?: string[]
}

export interface AdvancedConfig {
  defaults: Record<string, any>
  schema: Record<string, AdvancedConfigSchema>
}

export const ADVANCED_CONFIGS: Record<string, AdvancedConfig> = {
  lora_finetuning: {
    defaults: {
      lora_alpha: 16,
      lora_dropout: 0.05,
      lora_target_modules: ['q_proj', 'v_proj'],
      gradient_accumulation_steps: 4,
      warmup_ratio: 0.03,
      lr_scheduler_type: 'cosine',
      gradient_checkpointing: true,
      max_grad_norm: 1.0,
      fp16: false,
      bf16: true,
      eval_strategy: 'no',
      save_strategy: 'epoch',
      logging_steps: 10,
      report_to: 'none',
      optim: 'adamw_torch',
      weight_decay: 0.01,
      max_seq_length: 2048,
    },
    schema: {
      lora_alpha: { type: 'integer', min: 1, max: 128, description: 'LoRA scaling factor' },
      lora_dropout: { type: 'float', min: 0, max: 1, description: 'Dropout probability for LoRA layers' },
      lora_target_modules: { type: 'array', description: 'Which modules to apply LoRA to' },
      gradient_accumulation_steps: { type: 'integer', min: 1, max: 128, description: 'Number of gradient accumulation steps' },
      warmup_ratio: { type: 'float', min: 0, max: 1, description: 'Warmup proportion of total steps' },
      lr_scheduler_type: { type: 'select', options: ['linear', 'cosine', 'cosine_with_restarts', 'polynomial', 'constant', 'constant_with_warmup'], description: 'Learning rate scheduler' },
      gradient_checkpointing: { type: 'boolean', description: 'Use gradient checkpointing to save memory' },
      max_grad_norm: { type: 'float', min: 0, max: 10, description: 'Max gradient norm for clipping' },
      fp16: { type: 'boolean', description: 'Use FP16 mixed precision' },
      bf16: { type: 'boolean', description: 'Use BF16 mixed precision' },
      eval_strategy: { type: 'select', options: ['no', 'steps', 'epoch'], description: 'Evaluation strategy' },
      save_strategy: { type: 'select', options: ['no', 'steps', 'epoch'], description: 'Checkpoint save strategy' },
      logging_steps: { type: 'integer', min: 1, description: 'Log metrics every N steps' },
      report_to: { type: 'select', options: ['none', 'wandb', 'mlflow', 'tensorboard'], description: 'Where to report metrics' },
      optim: { type: 'select', options: ['adamw_torch', 'adamw_hf', 'adafactor', 'sgd'], description: 'Optimizer' },
      weight_decay: { type: 'float', min: 0, max: 1, description: 'Weight decay for regularization' },
      max_seq_length: { type: 'integer', min: 64, max: 32768, description: 'Maximum sequence length' },
    },
  },

  qlora_finetuning: {
    defaults: {
      lora_alpha: 16,
      lora_dropout: 0.05,
      lora_target_modules: ['q_proj', 'v_proj'],
      bits: 4,
      double_quant: true,
      quant_type: 'nf4',
      gradient_accumulation_steps: 4,
      warmup_ratio: 0.03,
      lr_scheduler_type: 'cosine',
      gradient_checkpointing: true,
      max_grad_norm: 1.0,
      bf16: true,
      optim: 'paged_adamw_32bit',
      max_seq_length: 2048,
    },
    schema: {
      lora_alpha: { type: 'integer', min: 1, max: 128, description: 'LoRA scaling factor' },
      lora_dropout: { type: 'float', min: 0, max: 1, description: 'LoRA dropout' },
      lora_target_modules: { type: 'array', description: 'Target modules for LoRA' },
      bits: { type: 'select', options: ['4', '8'], description: 'Quantization bits' },
      double_quant: { type: 'boolean', description: 'Use double quantization' },
      quant_type: { type: 'select', options: ['nf4', 'fp4'], description: 'Quantization type' },
      gradient_accumulation_steps: { type: 'integer', min: 1, description: 'Gradient accumulation steps' },
      warmup_ratio: { type: 'float', min: 0, max: 1, description: 'Warmup ratio' },
      lr_scheduler_type: { type: 'select', options: ['linear', 'cosine', 'cosine_with_restarts', 'polynomial', 'constant'], description: 'LR scheduler' },
      gradient_checkpointing: { type: 'boolean', description: 'Gradient checkpointing' },
      max_grad_norm: { type: 'float', min: 0, max: 10, description: 'Max gradient norm' },
      bf16: { type: 'boolean', description: 'Use BF16' },
      optim: { type: 'select', options: ['paged_adamw_32bit', 'paged_adamw_8bit', 'adamw_torch'], description: 'Optimizer' },
      max_seq_length: { type: 'integer', min: 64, max: 32768, description: 'Max sequence length' },
    },
  },

  full_finetuning: {
    defaults: {
      gradient_accumulation_steps: 4,
      warmup_steps: 100,
      lr_scheduler_type: 'cosine',
      gradient_checkpointing: true,
      max_grad_norm: 1.0,
      fp16: false,
      bf16: true,
      eval_strategy: 'epoch',
      save_strategy: 'epoch',
      logging_steps: 10,
      report_to: 'none',
      optim: 'adamw_torch',
      weight_decay: 0.01,
      max_seq_length: 2048,
      dataloader_num_workers: 4,
    },
    schema: {
      gradient_accumulation_steps: { type: 'integer', min: 1, description: 'Gradient accumulation steps' },
      warmup_steps: { type: 'integer', min: 0, description: 'Number of warmup steps' },
      lr_scheduler_type: { type: 'select', options: ['linear', 'cosine', 'cosine_with_restarts', 'polynomial', 'constant'], description: 'LR scheduler' },
      gradient_checkpointing: { type: 'boolean', description: 'Gradient checkpointing' },
      max_grad_norm: { type: 'float', min: 0, max: 10, description: 'Max gradient norm' },
      fp16: { type: 'boolean', description: 'Use FP16' },
      bf16: { type: 'boolean', description: 'Use BF16' },
      eval_strategy: { type: 'select', options: ['no', 'steps', 'epoch'], description: 'Evaluation strategy' },
      save_strategy: { type: 'select', options: ['no', 'steps', 'epoch'], description: 'Save strategy' },
      logging_steps: { type: 'integer', min: 1, description: 'Logging steps' },
      report_to: { type: 'select', options: ['none', 'wandb', 'mlflow', 'tensorboard'], description: 'Report metrics to' },
      optim: { type: 'select', options: ['adamw_torch', 'adamw_hf', 'adafactor', 'sgd'], description: 'Optimizer' },
      weight_decay: { type: 'float', min: 0, max: 1, description: 'Weight decay' },
      max_seq_length: { type: 'integer', min: 64, max: 32768, description: 'Max sequence length' },
      dataloader_num_workers: { type: 'integer', min: 0, max: 16, description: 'Dataloader workers' },
    },
  },

  dpo_alignment: {
    defaults: {
      beta: 0.1,
      loss_type: 'sigmoid',
      max_length: 1024,
      max_prompt_length: 512,
      gradient_accumulation_steps: 4,
      warmup_ratio: 0.1,
      lr_scheduler_type: 'cosine',
      bf16: true,
      gradient_checkpointing: true,
      optim: 'adamw_torch',
    },
    schema: {
      beta: { type: 'float', min: 0, max: 1, description: 'DPO beta parameter (temperature)' },
      loss_type: { type: 'select', options: ['sigmoid', 'hinge', 'ipo', 'kto'], description: 'DPO loss type' },
      max_length: { type: 'integer', min: 64, max: 8192, description: 'Max sequence length' },
      max_prompt_length: { type: 'integer', min: 32, max: 4096, description: 'Max prompt length' },
      gradient_accumulation_steps: { type: 'integer', min: 1, description: 'Gradient accumulation steps' },
      warmup_ratio: { type: 'float', min: 0, max: 1, description: 'Warmup ratio' },
      lr_scheduler_type: { type: 'select', options: ['linear', 'cosine', 'constant'], description: 'LR scheduler' },
      bf16: { type: 'boolean', description: 'Use BF16' },
      gradient_checkpointing: { type: 'boolean', description: 'Gradient checkpointing' },
      optim: { type: 'select', options: ['adamw_torch', 'adamw_hf', 'adafactor'], description: 'Optimizer' },
    },
  },

  llm_inference: {
    defaults: {
      max_new_tokens: 512,
      temperature: 0.7,
      top_p: 0.9,
      top_k: 50,
      repetition_penalty: 1.1,
      do_sample: true,
      num_beams: 1,
      early_stopping: false,
      no_repeat_ngram_size: 0,
      min_length: 0,
      length_penalty: 1.0,
    },
    schema: {
      max_new_tokens: { type: 'integer', min: 1, max: 16384, description: 'Maximum number of tokens to generate' },
      temperature: { type: 'float', min: 0, max: 2, description: 'Sampling temperature' },
      top_p: { type: 'float', min: 0, max: 1, description: 'Top-p (nucleus) sampling' },
      top_k: { type: 'integer', min: 0, max: 200, description: 'Top-k sampling' },
      repetition_penalty: { type: 'float', min: 1, max: 2, description: 'Repetition penalty' },
      do_sample: { type: 'boolean', description: 'Use sampling (vs greedy decoding)' },
      num_beams: { type: 'integer', min: 1, max: 10, description: 'Number of beams for beam search' },
      early_stopping: { type: 'boolean', description: 'Stop beam search early' },
      no_repeat_ngram_size: { type: 'integer', min: 0, max: 10, description: 'Prevent n-gram repetition (0=off)' },
      min_length: { type: 'integer', min: 0, description: 'Minimum generation length' },
      length_penalty: { type: 'float', min: 0, max: 5, description: 'Length penalty for beam search' },
    },
  },

  model_quantization: {
    defaults: {
      bits: 4,
      quant_type: 'gptq',
      group_size: 128,
      desc_act: false,
      damp_percent: 0.01,
      sym: true,
      dataset: 'c4',
      num_samples: 128,
      seq_length: 2048,
    },
    schema: {
      bits: { type: 'select', options: ['2', '3', '4', '8'], description: 'Quantization bit width' },
      quant_type: { type: 'select', options: ['gptq', 'awq', 'bnb'], description: 'Quantization method' },
      group_size: { type: 'integer', min: 32, max: 256, description: 'Group size for quantization' },
      desc_act: { type: 'boolean', description: 'Use descending activation order' },
      damp_percent: { type: 'float', min: 0, max: 0.1, description: 'Dampening percentage' },
      sym: { type: 'boolean', description: 'Use symmetric quantization' },
      dataset: { type: 'select', options: ['c4', 'wikitext', 'ptb', 'custom'], description: 'Calibration dataset' },
      num_samples: { type: 'integer', min: 8, max: 1024, description: 'Number of calibration samples' },
      seq_length: { type: 'integer', min: 128, max: 8192, description: 'Sequence length for calibration' },
    },
  },

  slerp_merge: {
    defaults: {
      t: 0.5,
      embed_slerp: true,
      tokenizer_source: 'base',
    },
    schema: {
      t: { type: 'float', min: 0, max: 1, description: 'Interpolation factor (0=model_a, 1=model_b)' },
      embed_slerp: { type: 'boolean', description: 'Use SLERP for embedding layers' },
      tokenizer_source: { type: 'select', options: ['base', 'other', 'union'], description: 'Which tokenizer to use' },
    },
  },

  batch_inference: {
    defaults: {
      max_new_tokens: 512,
      temperature: 0.7,
      top_p: 0.9,
      batch_size: 8,
      show_progress: true,
    },
    schema: {
      max_new_tokens: { type: 'integer', min: 1, max: 16384, description: 'Maximum tokens per generation' },
      temperature: { type: 'float', min: 0, max: 2, description: 'Sampling temperature' },
      top_p: { type: 'float', min: 0, max: 1, description: 'Top-p sampling' },
      batch_size: { type: 'integer', min: 1, max: 64, description: 'Batch size for parallel inference' },
      show_progress: { type: 'boolean', description: 'Show progress bar' },
    },
  },

  rlhf_ppo: {
    defaults: {
      gradient_accumulation_steps: 1,
      max_new_tokens: 128,
      temperature: 0.7,
      ppo_epochs_internal: 4,
      target_kl: 0.1,
      init_kl_coef: 0.2,
    },
    schema: {
      gradient_accumulation_steps: { type: 'integer', min: 1, max: 64, description: 'Gradient accumulation steps' },
      max_new_tokens: { type: 'integer', min: 16, max: 1024, description: 'Max tokens for PPO response generation' },
      temperature: { type: 'float', min: 0.1, max: 2, description: 'Sampling temperature for response generation' },
      ppo_epochs_internal: { type: 'integer', min: 1, max: 10, description: 'Internal PPO optimization epochs per batch' },
      target_kl: { type: 'float', min: 0, max: 1, description: 'Target KL divergence for early stopping' },
      init_kl_coef: { type: 'float', min: 0, max: 1, description: 'Initial KL coefficient' },
    },
  },

  continued_pretraining: {
    defaults: {
      gradient_accumulation_steps: 4,
      lr_scheduler_type: 'cosine',
      weight_decay: 0.01,
      max_grad_norm: 1.0,
      fp16: false,
      bf16: true,
      save_strategy: 'epoch',
      logging_steps: 10,
      report_to: 'none',
    },
    schema: {
      gradient_accumulation_steps: { type: 'integer', min: 1, max: 128, description: 'Gradient accumulation steps' },
      lr_scheduler_type: { type: 'select', options: ['linear', 'cosine', 'cosine_with_restarts', 'polynomial', 'constant'], description: 'LR scheduler' },
      weight_decay: { type: 'float', min: 0, max: 1, description: 'Weight decay' },
      max_grad_norm: { type: 'float', min: 0, max: 10, description: 'Max gradient norm' },
      fp16: { type: 'boolean', description: 'Use FP16' },
      bf16: { type: 'boolean', description: 'Use BF16' },
      save_strategy: { type: 'select', options: ['no', 'steps', 'epoch'], description: 'Save strategy' },
      logging_steps: { type: 'integer', min: 1, description: 'Logging steps' },
      report_to: { type: 'select', options: ['none', 'wandb', 'mlflow', 'tensorboard'], description: 'Report metrics to' },
    },
  },

  distillation: {
    defaults: {
      gradient_accumulation_steps: 4,
      max_grad_norm: 1.0,
      weight_decay: 0.01,
      lr_scheduler_type: 'cosine',
      warmup_ratio: 0.1,
      fp16: false,
      bf16: true,
    },
    schema: {
      gradient_accumulation_steps: { type: 'integer', min: 1, max: 64, description: 'Gradient accumulation steps' },
      max_grad_norm: { type: 'float', min: 0, max: 10, description: 'Max gradient norm' },
      weight_decay: { type: 'float', min: 0, max: 1, description: 'Weight decay' },
      lr_scheduler_type: { type: 'select', options: ['linear', 'cosine', 'constant'], description: 'LR scheduler' },
      warmup_ratio: { type: 'float', min: 0, max: 1, description: 'Warmup ratio' },
      fp16: { type: 'boolean', description: 'Use FP16' },
      bf16: { type: 'boolean', description: 'Use BF16' },
    },
  },

  curriculum_training: {
    defaults: {
      gradient_accumulation_steps: 4,
      warmup_ratio: 0.1,
      weight_decay: 0.01,
      lr_scheduler_type: 'cosine',
      max_grad_norm: 1.0,
      fp16: false,
      bf16: true,
    },
    schema: {
      gradient_accumulation_steps: { type: 'integer', min: 1, max: 64, description: 'Gradient accumulation steps' },
      warmup_ratio: { type: 'float', min: 0, max: 1, description: 'Warmup ratio' },
      weight_decay: { type: 'float', min: 0, max: 1, description: 'Weight decay' },
      lr_scheduler_type: { type: 'select', options: ['linear', 'cosine', 'constant'], description: 'LR scheduler' },
      max_grad_norm: { type: 'float', min: 0, max: 10, description: 'Max gradient norm' },
      fp16: { type: 'boolean', description: 'Use FP16' },
      bf16: { type: 'boolean', description: 'Use BF16' },
    },
  },

  ballast_training: {
    defaults: {
      gradient_accumulation_steps: 4,
      warmup_ratio: 0.05,
      weight_decay: 0.01,
      lr_scheduler_type: 'cosine',
      max_grad_norm: 1.0,
      fp16: false,
      bf16: true,
      save_strategy: 'epoch',
    },
    schema: {
      gradient_accumulation_steps: { type: 'integer', min: 1, max: 64, description: 'Gradient accumulation steps' },
      warmup_ratio: { type: 'float', min: 0, max: 1, description: 'Warmup ratio' },
      weight_decay: { type: 'float', min: 0, max: 1, description: 'Weight decay' },
      lr_scheduler_type: { type: 'select', options: ['linear', 'cosine', 'constant'], description: 'LR scheduler' },
      max_grad_norm: { type: 'float', min: 0, max: 10, description: 'Max gradient norm' },
      fp16: { type: 'boolean', description: 'Use FP16' },
      bf16: { type: 'boolean', description: 'Use BF16' },
      save_strategy: { type: 'select', options: ['no', 'steps', 'epoch'], description: 'Save strategy' },
    },
  },

  reward_model_trainer: {
    defaults: {
      gradient_accumulation_steps: 4,
      warmup_ratio: 0.1,
      weight_decay: 0.01,
      lr_scheduler_type: 'linear',
      max_grad_norm: 1.0,
      bf16: true,
      save_strategy: 'epoch',
      logging_steps: 10,
    },
    schema: {
      gradient_accumulation_steps: { type: 'integer', min: 1, max: 64, description: 'Gradient accumulation steps' },
      warmup_ratio: { type: 'float', min: 0, max: 1, description: 'Warmup ratio' },
      weight_decay: { type: 'float', min: 0, max: 1, description: 'Weight decay' },
      lr_scheduler_type: { type: 'select', options: ['linear', 'cosine', 'constant'], description: 'LR scheduler' },
      max_grad_norm: { type: 'float', min: 0, max: 10, description: 'Max gradient norm' },
      bf16: { type: 'boolean', description: 'Use BF16' },
      save_strategy: { type: 'select', options: ['no', 'steps', 'epoch'], description: 'Save strategy' },
      logging_steps: { type: 'integer', min: 1, description: 'Logging steps' },
    },
  },
}

/**
 * Get advanced config for a block type. Returns null if no advanced config exists.
 */
export function getAdvancedConfig(blockType: string): AdvancedConfig | null {
  return ADVANCED_CONFIGS[blockType] || null
}
