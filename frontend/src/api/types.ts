/**
 * Convenience re-exports of generated API types.
 *
 * Import from here instead of generated-types.ts directly.
 * This file maps OpenAPI component schemas to simple type aliases.
 *
 * AUTO-GENERATED UPSTREAM — regenerate with: npm run generate:api
 */

import type { components } from './generated-types'

// ═══════════════════════════════════════════════════
//  PROJECTS
// ═══════════════════════════════════════════════════
export type ProjectResponse = components['schemas']['ProjectResponse']
export type ProjectCreate = components['schemas']['ProjectCreate']
export type ProjectUpdate = components['schemas']['ProjectUpdate']

// ═══════════════════════════════════════════════════
//  EXPERIMENT PHASES
// ═══════════════════════════════════════════════════
export type ExperimentPhaseResponse = components['schemas']['ExperimentPhaseResponse']
export type ExperimentPhaseCreate = components['schemas']['ExperimentPhaseCreate']
export type ExperimentPhaseUpdate = components['schemas']['ExperimentPhaseUpdate']
export type QuickSetupRequest = components['schemas']['QuickSetupRequest']
export type QuickSetupPhase = components['schemas']['QuickSetupPhase']

// ═══════════════════════════════════════════════════
//  PIPELINES
// ═══════════════════════════════════════════════════
export type PipelineResponse = components['schemas']['PipelineResponse']
export type PipelineCreate = components['schemas']['PipelineCreate']
export type PipelineUpdate = components['schemas']['PipelineUpdate']

// ═══════════════════════════════════════════════════
//  RUNS
// ═══════════════════════════════════════════════════
export type RunResponse = components['schemas']['RunResponse']

// ═══════════════════════════════════════════════════
//  EXECUTION
// ═══════════════════════════════════════════════════
export type ExecuteResponse = { run_id: string; status?: string }
export type PartialExecuteResponse = components['schemas']['PartialExecuteResponse']
export type CancelResponse = components['schemas']['CancelResponse']
export type RunOutputsResponse = components['schemas']['RunOutputsResponse']
export type PipelineValidationResponse = components['schemas']['PipelineValidationResponse']
export type BlockConfigValidationResponse = components['schemas']['BlockConfigValidationResponse']
export type PipelineTestResponse = components['schemas']['PipelineTestResponse']

// ═══════════════════════════════════════════════════
//  DATASETS
// ═══════════════════════════════════════════════════
export type DatasetResponse = components['schemas']['DatasetResponse']
export type DatasetCreate = components['schemas']['DatasetCreate']

// ═══════════════════════════════════════════════════
//  PAPERS
// ═══════════════════════════════════════════════════
export type PaperResponse = components['schemas']['PaperResponse']
export type PaperCreate = components['schemas']['PaperCreate']
export type PaperUpdate = components['schemas']['PaperUpdate']

// ═══════════════════════════════════════════════════
//  SYSTEM
// ═══════════════════════════════════════════════════
export type FeatureFlagsResponse = components['schemas']['FeatureFlagsResponse']
export type SystemMetricsResponse = components['schemas']['SystemMetricsResponse']
export type CapabilitiesResponse = components['schemas']['CapabilitiesResponse']
export type BenchmarkRefreshResponse = components['schemas']['BenchmarkRefreshResponse']
export type ScheduleResponse = components['schemas']['ScheduleResponse']
export type DependencyCheckResponse = components['schemas']['DependencyCheckResponse']
export type InstallResponse = components['schemas']['InstallResponse']
export type DiagnosticsResponse = components['schemas']['DiagnosticsResponse']

// ═══════════════════════════════════════════════════
//  BLOCKS
// ═══════════════════════════════════════════════════
export type BlockSourceResponse = components['schemas']['BlockSourceResponse']

// ═══════════════════════════════════════════════════
//  SWEEPS
// ═══════════════════════════════════════════════════
export type CreateSweepRequest = components['schemas']['CreateSweepRequest']

// ═══════════════════════════════════════════════════
//  REGISTRY
// ═══════════════════════════════════════════════════
export type BlockSchema = components['schemas']['BlockSchema']
export type PortSchema = components['schemas']['PortSchema']
export type ConfigFieldSchema = components['schemas']['ConfigFieldSchema']
export type BlockDetailSchema = components['schemas']['BlockDetailSchema']
export type ValidateConnectionRequest = components['schemas']['ValidateConnectionRequest']
export type ValidateConnectionResponse = components['schemas']['ValidateConnectionResponse']
export type RegistryVersionResponse = components['schemas']['RegistryVersionResponse']
export type RegistryHealthResponse = components['schemas']['RegistryHealthResponse']

// ═══════════════════════════════════════════════════
//  MARKETPLACE
// ═══════════════════════════════════════════════════
// Note: PublishRequest and ReviewRequest are defined in-router (not in schemas/)
// and use Literal types that export correctly to OpenAPI. If they show up in
// generated-types.ts, re-export them here. Otherwise they're available via
// components['schemas'] directly.
