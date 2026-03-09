import { create } from 'zustand'
import { api } from '@/api/client'
import { useSettingsStore } from './settingsStore'
import { DEMO_PROJECTS } from '@/lib/demo-data'

export interface Project {
  id: string
  name: string
  paper_number: string | null
  description: string
  status: string
  github_repo: string | null
  notes: string
  tags: string[]
  created_at: string
  updated_at: string
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
        description: p.description,
        status: p.status,
        github_repo: null,
        notes: '',
        tags: [],
        created_at: p.created_at,
        updated_at: p.updated_at,
      }))
      set({ projects, loading: false })
      return
    }
    try {
      const projects = await api.get<Project[]>('/projects')
      set({ projects, loading: false })
    } catch (e: any) {
      set({ error: e.message, loading: false })
    }
  },

  createProject: async (data) => {
    if (isDemoMode()) {
      const project: Project = {
        id: `demo-new-${Date.now()}`,
        name: data.name || 'New Project',
        paper_number: data.paper_number ?? null,
        description: data.description || '',
        status: data.status || 'active',
        github_repo: null,
        notes: '',
        tags: [],
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
}))
