/**
 * Generated API types stub.
 *
 * This file provides type declarations for the Blueprint API schemas.
 * In production it is generated from the OpenAPI spec via: npm run generate:api
 *
 * If the backend API schema changes, regenerate this file.
 * Until then, this stub provides enough type safety for the frontend to compile.
 */

/* eslint-disable @typescript-eslint/no-empty-object-type */

export interface components {
  schemas: {
    // ── Projects ──
    ProjectResponse: {
      id: string
      name: string
      paper_number: string | null
      paper_title: string | null
      paper_subtitle: string | null
      target_venue: string | null
      description: string
      status: string
      blocked_by: string | null
      priority: number
      github_repo: string | null
      notes: string
      tags: string[]
      hypothesis: string | null
      key_result: string | null
      total_experiments: number
      completed_experiments: number
      current_phase: string | null
      completion_criteria: string | null
      estimated_compute_hours: number
      estimated_cost_usd: number
      actual_compute_hours: number
      started_at: string | null
      completed_at: string | null
      created_at: string | null
      updated_at: string | null
    }
    ProjectCreate: {
      name: string
      description?: string
      status?: string
      paper_number?: string | null
      paper_title?: string | null
      target_venue?: string | null
      hypothesis?: string | null
      estimated_compute_hours?: number
      tags?: string[]
    }
    ProjectUpdate: Partial<components['schemas']['ProjectCreate']>

    // ── Experiment Phases ──
    ExperimentPhaseResponse: {
      id: string
      phase_id: string
      project_id: string
      name: string
      description: string | null
      research_question: string | null
      status: string
      total_runs: number
      completed_runs: number
      order: number
      created_at: string | null
    }
    ExperimentPhaseCreate: {
      phase_id: string
      name: string
      description?: string
      research_question?: string
      total_runs?: number
    }
    ExperimentPhaseUpdate: Partial<components['schemas']['ExperimentPhaseCreate']>
    QuickSetupPhase: {
      phase_id: string
      name: string
      total_runs: number
      description?: string
      research_question?: string
    }
    QuickSetupRequest: {
      phases: components['schemas']['QuickSetupPhase'][]
    }

    // ── Pipelines ──
    PipelineResponse: {
      id: string
      name: string
      description: string
      project_id: string | null
      nodes: unknown[]
      edges: unknown[]
      definition: Record<string, unknown> | null
      created_at: string | null
      updated_at: string | null
    }
    PipelineCreate: {
      name: string
      description?: string
      project_id?: string | null
      nodes?: unknown[]
      edges?: unknown[]
    }
    PipelineUpdate: Partial<components['schemas']['PipelineCreate']>

    // ── Runs ──
    RunResponse: {
      id: string
      pipeline_id: string
      status: string
      error_message: string | null
      created_at: string | null
      started_at: string | null
      finished_at: string | null
      duration_seconds: number | null
      metrics: Record<string, number | string>
      config_snapshot: Record<string, unknown> | null
      experiment_phase_id: string | null
    }

    // ── Execution ──
    ExecuteResponse: { run_id: string; status: string }
    PartialExecuteResponse: { run_id: string; status: string }
    CancelResponse: { run_id: string; status: string }
    RunOutputsResponse: { run_id: string; outputs: Record<string, unknown> }
    PipelineValidationResponse: {
      valid: boolean
      errors: { node_id: string; message: string; severity: string }[]
      warnings: { node_id: string; message: string; severity: string }[]
    }
    BlockConfigValidationResponse: {
      valid: boolean
      errors: string[]
    }
    PipelineTestResponse: { success: boolean; message: string }

    // ── Datasets ──
    DatasetResponse: {
      id: string
      name: string
      description: string
      format: string
      size_bytes: number
      row_count: number | null
      created_at: string | null
    }
    DatasetCreate: {
      name: string
      description?: string
      format?: string
    }

    // ── Papers ──
    PaperResponse: {
      id: string
      project_id: string
      title: string
      content: string
      status: string
      created_at: string | null
      updated_at: string | null
    }
    PaperCreate: { project_id: string; title: string; content?: string }
    PaperUpdate: Partial<components['schemas']['PaperCreate']>

    // ── System ──
    FeatureFlagsResponse: { marketplace: boolean }
    SystemMetricsResponse: {
      cpu_percent: number
      memory_percent: number
      memory_gb: number
      memory_total_gb: number
      gpu_percent: number | null
    }
    CapabilitiesResponse: {
      gpu_available: boolean
      gpu_backend: string
      max_vram_gb: number
      usable_memory_gb: number
      max_model_size: string
      can_fine_tune: boolean
      can_run_local_llm: boolean
      disk_ok: boolean
      accelerators: Record<string, boolean>
    }
    BenchmarkRefreshResponse: { status: string }
    ScheduleResponse: { status: string }
    DependencyCheckResponse: { name: string; installed: boolean; version: string | null }
    InstallResponse: { success: boolean; message: string }
    DiagnosticsResponse: Record<string, unknown>

    // ── Blocks ──
    BlockSourceResponse: { block_yaml: string; run_py: string }

    // ── Sweeps ──
    CreateSweepRequest: {
      pipeline_id: string
      sweep_config: Record<string, unknown>
    }

    // ── Registry ──
    PortSchema: {
      id: string
      label: string
      data_type: string
      required: boolean
    }
    ConfigFieldSchema: {
      name: string
      label: string
      type: string
      default: unknown
      options?: string[]
      description?: string
    }
    BlockSchema: {
      type: string
      name: string
      description: string
      category: string
      version: string
      icon: string
      accent: string
      maturity: string
      inputs: components['schemas']['PortSchema'][]
      outputs: components['schemas']['PortSchema'][]
      config_fields: components['schemas']['ConfigFieldSchema'][]
      tags: string[]
    }
    BlockDetailSchema: components['schemas']['BlockSchema'] & {
      default_config: Record<string, unknown>
      source_available: boolean
    }
    ValidateConnectionRequest: {
      source_type: string
      target_type: string
    }
    ValidateConnectionResponse: {
      compatible: boolean
      reason?: string
    }
    RegistryVersionResponse: { version: number; block_count: number }
    RegistryHealthResponse: {
      total: number
      valid: number
      broken: number
      categories: Record<string, number>
    }
  }
}
