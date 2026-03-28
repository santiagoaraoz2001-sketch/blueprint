import { create } from 'zustand'
import { api } from '@/api/client'
import type { ProjectResponse, ExperimentPhaseResponse } from '@/api/types'
import { useSettingsStore } from './settingsStore'
import { DEMO_PROJECTS } from '@/lib/demo-data'

/** Re-export generated types for backward compatibility */
export type Project = ProjectResponse
export type ExperimentPhase = ExperimentPhaseResponse

export interface DashboardStats {
  total_papers: number
  by_status: Record<string, number>
  currently_running: { id: string; name: string }[]
  recently_completed: { id: string; name: string; completed_at: string | null }[]
  total_compute_hours: number
  blocked_papers: { id: string; name: string; blocked_by: string | null }[]
  unassigned_runs: number
  recent_unassigned: { run_id: string; pipeline_name: string; metrics: Record<string, number | string> }[]
}

export interface ProjectStats {
  total_runs: number
  completed_runs: number
  failed_runs: number
  running_runs: number
  total_compute_hours: number
  best_run: { run_id: string; metrics: Record<string, number | string> } | null
  latest_run: { run_id: string; status: string } | null
  phases: {
    id: string; phase_id: string; name: string
    status: string; total_runs: number; completed_runs: number
  }[]
  active_runs: { run_id: string; pipeline_id: string; status: string }[]
}

interface ProjectState {
  projects: Project[]
  loading: boolean
  error: string | null
  fetchProjects: () => Promise<void>
  createProject: (data: Partial<Project>) => Promise<Project>
  updateProject: (id: string, data: Partial<Project>) => Promise<void>
  deleteProject: (id: string) => Promise<void>
  setProjects: (projects: Project[]) => void
  fetchProject: (id: string) => Promise<Project>
  fetchPhases: (projectId: string) => Promise<ExperimentPhase[]>
  createPhase: (projectId: string, data: Partial<ExperimentPhase>) => Promise<ExperimentPhase>
  updatePhase: (projectId: string, phaseId: string, data: Partial<ExperimentPhase>) => Promise<ExperimentPhase>
  quickSetup: (projectId: string, phases: { phase_id: string; name: string; total_runs: number; description?: string; research_question?: string }[]) => Promise<Project>
  assignRun: (runId: string, experimentPhaseId: string) => Promise<void>
  fetchStats: (projectId: string) => Promise<ProjectStats>
  fetchDashboard: () => Promise<DashboardStats>
  clonePipeline: (pipelineId: string) => Promise<any>
  cloneFromRun: (runId: string) => Promise<any>
  cloneAsVariant: (pipelineId: string, data: { name?: string; project_id?: string; variant_notes?: string }) => Promise<any>
  updateRunMetadata: (runId: string, data: { notes?: string; tags?: string; starred?: boolean }) => Promise<any>
}

function isDemoMode() {
  return useSettingsStore.getState().demoMode
}

export const useProjectStore = create<ProjectState>((set) => ({
  projects: [],
  loading: false,
  error: null,
  setProjects: (projects) => set({ projects }),

  fetchProjects: async () => {
    set({ loading: true, error: null })
    if (isDemoMode()) {
      const projects: Project[] = DEMO_PROJECTS.map((p) => ({
        id: p.id,
        name: p.name,
        paper_number: p.paper_number ?? null,
        paper_title: null,
        paper_subtitle: null,
        target_venue: null,
        description: p.description,
        status: p.status,
        blocked_by: null,
        priority: 5,
        github_repo: null,
        notes: '',
        hypothesis: null,
        key_result: null,
        tags: [],
        total_experiments: 0,
        completed_experiments: 0,
        current_phase: null,
        completion_criteria: null,
        estimated_compute_hours: 0,
        estimated_cost_usd: 0,
        actual_compute_hours: 0,
        started_at: null,
        completed_at: null,
        created_at: p.created_at,
        updated_at: p.updated_at,
      }))
      set({ projects, loading: false })
      return
    }
    try {
      const projects = await api.get<Project[]>('/projects')
      set({ projects, loading: false })
    } catch (e: unknown) {
      set({ error: e instanceof Error ? e.message : 'Failed to fetch projects', loading: false })
    }
  },

  fetchProject: async (id) => {
    return api.get<Project>(`/projects/${id}`)
  },

  createProject: async (data) => {
    if (isDemoMode()) {
      const project: Project = {
        id: `demo-new-${Date.now()}`,
        name: data.name || 'New Project',
        paper_number: data.paper_number ?? null,
        paper_title: null,
        paper_subtitle: null,
        target_venue: null,
        description: data.description || '',
        status: data.status || 'planned',
        blocked_by: null,
        priority: 5,
        github_repo: null,
        notes: '',
        hypothesis: null,
        key_result: null,
        tags: [],
        total_experiments: 0,
        completed_experiments: 0,
        current_phase: null,
        completion_criteria: null,
        estimated_compute_hours: 0,
        estimated_cost_usd: 0,
        actual_compute_hours: 0,
        started_at: null,
        completed_at: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }
      set((s) => ({ projects: [project, ...s.projects] }))
      return project
    }
    const project = await api.post<Project>('/projects', data)
    set((s) => ({ projects: [project, ...s.projects] }))
    return project
  },

  updateProject: async (id, data) => {
    if (isDemoMode()) {
      set((s) => ({
        projects: s.projects.map((p) =>
          p.id === id ? { ...p, ...data, updated_at: new Date().toISOString() } : p
        ),
      }))
      return
    }
    const updated = await api.put<Project>(`/projects/${id}`, data)
    set((s) => ({
      projects: s.projects.map((p) => (p.id === id ? updated : p)),
    }))
  },

  deleteProject: async (id) => {
    if (isDemoMode()) {
      set((s) => ({ projects: s.projects.filter((p) => p.id !== id) }))
      return
    }
    await api.delete(`/projects/${id}`)
    set((s) => ({ projects: s.projects.filter((p) => p.id !== id) }))
  },

  fetchPhases: async (projectId) => {
    return api.get<ExperimentPhase[]>(`/projects/${projectId}/phases`)
  },

  createPhase: async (projectId, data) => {
    return api.post<ExperimentPhase>(`/projects/${projectId}/phases`, data)
  },

  updatePhase: async (projectId, phaseId, data) => {
    return api.put<ExperimentPhase>(`/projects/${projectId}/phases/${phaseId}`, data)
  },

  quickSetup: async (projectId, phases) => {
    const result = await api.post<Project>(`/projects/${projectId}/quick-setup`, { phases })
    set((s) => ({
      projects: s.projects.map((p) => (p.id === projectId ? result : p)),
    }))
    return result
  },

  assignRun: async (runId, experimentPhaseId) => {
    await api.post(`/runs/${runId}/assign`, { experiment_phase_id: experimentPhaseId })
  },

  fetchStats: async (projectId) => {
    return api.get<ProjectStats>(`/projects/${projectId}/stats`)
  },

  fetchDashboard: async () => {
    return api.get<DashboardStats>('/projects/dashboard')
  },

  clonePipeline: async (pipelineId) => {
    return api.post(`/pipelines/${pipelineId}/clone`, {})
  },

  cloneFromRun: async (runId) => {
    return api.post(`/runs/${runId}/clone-pipeline`, {})
  },

  cloneAsVariant: async (pipelineId: string, data: { name?: string; project_id?: string; variant_notes?: string }) => {
    return api.post(`/pipelines/${pipelineId}/clone-variant`, data)
  },

  updateRunMetadata: async (runId: string, data: { notes?: string; tags?: string; starred?: boolean }) => {
    return api.put(`/runs/${runId}/metadata`, data)
  },
}))
