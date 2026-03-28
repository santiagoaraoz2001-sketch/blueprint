/**
 * Hand-maintained type declarations mirroring backend Pydantic schemas.
 *
 * This file is the TypeScript source of truth for API response shapes.
 * It replaces the missing OpenAPI-generated file that types.ts imports.
 *
 * To regenerate from OpenAPI: npm run generate:api
 * When the generator is unavailable, maintain this file manually.
 * Each interface maps 1:1 to a Pydantic model in backend/schemas/.
 */

export interface components {
  schemas: {
    // ═══════════════════════════════════════════════════
    //  PROJECTS  (backend/schemas/project.py)
    // ═══════════════════════════════════════════════════
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
      hypothesis: string | null
      key_result: string | null
      tags: string[]
      total_experiments: number
      completed_experiments: number
      current_phase: string | null
      completion_criteria: string | null
      estimated_compute_hours: number
      estimated_cost_usd: number
      actual_compute_hours: number
      started_at: string | null
      completed_at: string | null
      created_at: string
      updated_at: string
    }
    ProjectCreate: {
      name: string
      paper_number?: string | null
      paper_title?: string | null
      paper_subtitle?: string | null
      target_venue?: string | null
      description?: string
      status?: string
      blocked_by?: string | null
      priority?: number
      github_repo?: string | null
      notes?: string
      hypothesis?: string | null
      key_result?: string | null
      tags?: string[]
      total_experiments?: number
      completed_experiments?: number
      current_phase?: string | null
      completion_criteria?: string | null
      estimated_compute_hours?: number
      estimated_cost_usd?: number
    }
    ProjectUpdate: {
      name?: string | null
      paper_number?: string | null
      paper_title?: string | null
      paper_subtitle?: string | null
      target_venue?: string | null
      description?: string | null
      status?: string | null
      blocked_by?: string | null
      priority?: number | null
      github_repo?: string | null
      notes?: string | null
      hypothesis?: string | null
      key_result?: string | null
      tags?: string[] | null
      total_experiments?: number | null
      completed_experiments?: number | null
      current_phase?: string | null
      completion_criteria?: string | null
      estimated_compute_hours?: number | null
      estimated_cost_usd?: number | null
      actual_compute_hours?: number | null
      started_at?: string | null
      completed_at?: string | null
    }

    // ═══════════════════════════════════════════════════
    //  EXPERIMENT PHASES  (backend/schemas/experiment_phase.py)
    // ═══════════════════════════════════════════════════
    ExperimentPhaseResponse: {
      id: string
      project_id: string
      phase_id: string
      name: string
      description: string | null
      status: string
      blocked_by_phase: string | null
      total_runs: number
      completed_runs: number
      research_question: string | null
      finding: string | null
      sort_order: number
      created_at: string
    }
    ExperimentPhaseCreate: {
      phase_id: string
      name: string
      description?: string | null
      status?: string
      blocked_by_phase?: string | null
      total_runs?: number
      research_question?: string | null
      sort_order?: number
    }
    ExperimentPhaseUpdate: {
      phase_id?: string | null
      name?: string | null
      description?: string | null
      status?: string | null
      blocked_by_phase?: string | null
      total_runs?: number | null
      completed_runs?: number | null
      research_question?: string | null
      finding?: string | null
      sort_order?: number | null
    }
    QuickSetupPhase: {
      phase_id: string
      name: string
      total_runs?: number
      description?: string | null
      research_question?: string | null
    }
    QuickSetupRequest: {
      phases: components['schemas']['QuickSetupPhase'][]
    }

    // ═══════════════════════════════════════════════════
    //  PIPELINES  (backend/schemas/pipeline.py)
    // ═══════════════════════════════════════════════════
    PipelineResponse: {
      id: string
      name: string
      project_id: string | null
      experiment_id: string | null
      experiment_phase_id: string | null
      description: string
      definition: Record<string, any>
      history_json: string | null
      created_at: string
      updated_at: string
    }
    PipelineCreate: {
      name: string
      project_id?: string | null
      experiment_id?: string | null
      experiment_phase_id?: string | null
      description?: string
      definition?: Record<string, any>
    }
    PipelineUpdate: {
      name?: string | null
      description?: string | null
      experiment_phase_id?: string | null
      definition?: Record<string, any> | null
    }

    // ═══════════════════════════════════════════════════
    //  RUNS  (backend/schemas/run.py)
    // ═══════════════════════════════════════════════════
    RunResponse: {
      id: string
      pipeline_id: string
      project_id: string | null
      mlflow_run_id: string | null
      status: string
      started_at: string
      finished_at: string | null
      duration_seconds: number | null
      error_message: string | null
      config_snapshot: Record<string, any>
      metrics: Record<string, any>
      outputs_snapshot: Record<string, any> | null
      data_fingerprints: Record<string, any> | null
    }

    // ═══════════════════════════════════════════════════
    //  EXECUTION  (backend/schemas/execution.py)
    // ═══════════════════════════════════════════════════
    ExecuteResponse: {
      status: string
      pipeline_id: string
      run_id: string
    }
    PartialExecuteResponse: {
      status: string
      pipeline_id: string
      run_id: string
      partial: boolean
      source_run_id: string
      start_node_id: string
    }
    CancelResponse: {
      status: string
      run_id: string | null
    }
    RunOutputsResponse: {
      run_id: string
      status: string
      outputs: Record<string, any>
    }
    PipelineValidationResponse: {
      valid: boolean
      errors: string[]
      warnings: string[]
      estimated_runtime_s: number
      block_count: number
      edge_count: number
    }
    BlockConfigValidationResponse: {
      valid: boolean
      errors: Record<string, any>[]
      validated_config: Record<string, any>
    }
    PipelineTestResponse: {
      mode: string
      validation: Record<string, any>
      estimated_runtime_s: number
      sample_size: number
      block_count: number
    }

    // ═══════════════════════════════════════════════════
    //  DATASETS  (backend/schemas/dataset.py)
    // ═══════════════════════════════════════════════════
    DatasetResponse: {
      id: string
      name: string
      source: string
      source_path: string
      description: string
      row_count: number | null
      size_bytes: number | null
      column_count: number | null
      columns: any[]
      tags: string[]
      created_at: string
      version: number
    }
    DatasetCreate: {
      name: string
      source?: string
      source_path?: string
      description?: string
      tags?: string[]
    }

    // ═══════════════════════════════════════════════════
    //  PAPERS  (backend/schemas/paper.py)
    // ═══════════════════════════════════════════════════
    PaperResponse: {
      id: string
      name: string
      project_id: string
      content: Record<string, any>
      created_at: string
      updated_at: string
    }
    PaperCreate: {
      name: string
      project_id: string
      content?: Record<string, any>
    }
    PaperUpdate: {
      name?: string | null
      content?: Record<string, any> | null
    }

    // ═══════════════════════════════════════════════════
    //  SYSTEM  (backend/schemas/system.py)
    // ═══════════════════════════════════════════════════
    FeatureFlagsResponse: {
      marketplace: boolean
    }
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
      accelerators: Record<string, any>
    }
    BenchmarkRefreshResponse: {
      status: string
      entries: number
    }
    ScheduleResponse: {
      stages: Record<string, any>[]
      total_stages: number
      max_parallelism: number
    }
    DependencyCheckResponse: {
      summary: {
        total_blocks: number
        ready_blocks: number
        missing_packages: string[]
        in_virtual_env: boolean
      }
      packages: Record<string, { package: string; installed: boolean; version: string | null }>
      blocks: Record<string, { ready: boolean; total_deps: number; missing: string[]; install_command: string | null }>
    }
    InstallResponse: {
      success: boolean
      stdout: string
      stderr: string
      installed: string[]
      error: string | null
    }
    DiagnosticsResponse: {
      run_id: string
      events: Record<string, any>[]
      event_count: number
      truncated: boolean
      max_events: number | null
    }

    // ═══════════════════════════════════════════════════
    //  BLOCKS  (backend/schemas/blocks.py)
    // ═══════════════════════════════════════════════════
    BlockSourceResponse: {
      block: string
      source: string
    }

    // ═══════════════════════════════════════════════════
    //  REGISTRY  (backend/routers/registry.py inline models)
    // ═══════════════════════════════════════════════════
    PortSchema: {
      id: string
      label: string
      data_type: string
      required: boolean
      default: any
      aliases: string[]
      description: string
      position: string | null
    }
    ConfigFieldSchema: {
      name: string
      label: string
      type: string
      default: any
      min: number | null
      max: number | null
      options: string[] | null
      description: string | null
      depends_on: Record<string, any> | null
      mandatory: boolean | null
    }
    BlockSchema: {
      type: string
      name: string
      category: string
      description: string
      icon: string
      accent: string
      version: string
      inputs: components['schemas']['PortSchema'][]
      outputs: components['schemas']['PortSchema'][]
      config: components['schemas']['ConfigFieldSchema'][]
      tags: string[]
      aliases: string[]
      deprecated: boolean
      maturity: string
      exportable: boolean
    }
    BlockDetailSchema: {
      format: string | null
      formatEditable: boolean | null
      codePreview: string | null
      tips: string[] | null
      useCases: string[] | null
      howItWorks: string | null
    }
    ValidateConnectionRequest: {
      src_type: string
      src_port: string
      dst_type: string
      dst_port: string
    }
    ValidateConnectionResponse: {
      valid: boolean
      error: string | null
    }
    RegistryVersionResponse: {
      version: number
    }
    RegistryHealthResponse: {
      total_blocks: number
      categories: Record<string, number>
      broken_blocks: string[]
    }

    // ═══════════════════════════════════════════════════
    //  SWEEPS  (backend/routers/sweeps.py inline model)
    // ═══════════════════════════════════════════════════
    CreateSweepRequest: {
      pipeline_id: string
      param_space: Record<string, any>
      metric_key: string
      strategy?: string
      max_runs?: number
    }
  }
}
