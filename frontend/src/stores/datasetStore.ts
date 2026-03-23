import { create } from 'zustand'
import { api } from '@/api/client'
import { useSettingsStore } from './settingsStore'
import { DEMO_DATASETS } from '@/lib/demo-data'

export interface DatasetItem {
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

export interface SnapshotItem {
  id: string
  dataset_id: string
  timestamp: number
  size_bytes: number
}

interface DatasetState {
  datasets: DatasetItem[]
  loading: boolean
  selectedId: string | null

  fetchDatasets: () => Promise<void>
  registerDataset: (data: { name: string; source: string; source_path: string; description?: string; tags?: string[] }) => Promise<void>
  deleteDataset: (id: string) => Promise<void>
  selectDataset: (id: string | null) => void

  // Snapshot (Time Machine) APIs
  fetchSnapshots: (datasetId: string) => Promise<SnapshotItem[]>
  createSnapshot: (datasetId: string) => Promise<void>
  restoreSnapshot: (datasetId: string, snapshotId: string) => Promise<void>
}

function isDemoMode() {
  return useSettingsStore.getState().demoMode
}

export const useDatasetStore = create<DatasetState>((set) => ({
  datasets: [],
  loading: false,
  selectedId: null,

  fetchDatasets: async () => {
    set({ loading: true })
    if (isDemoMode()) {
      const datasets: DatasetItem[] = DEMO_DATASETS.map((d) => ({
        id: d.id,
        name: d.name,
        source: d.source,
        source_path: d.source === 'HuggingFace' ? `hf://${d.name}` : `/data/${d.name}`,
        description: `${d.format.toUpperCase()} dataset with ${d.rows.toLocaleString()} rows`,
        row_count: d.rows,
        size_bytes: Math.round(d.size_mb * 1024 * 1024),
        column_count: d.columns,
        columns: [],
        tags: [d.format, d.source.toLowerCase()],
        created_at: '2025-12-01T10:00:00Z',
        version: 1,
      }))
      set({ datasets, loading: false })
      return
    }
    try {
      const data = await api.get<DatasetItem[]>('/datasets')
      set({ datasets: data })
    } finally {
      set({ loading: false })
    }
  },

  registerDataset: async (data) => {
    if (isDemoMode()) {
      const ds: DatasetItem = {
        id: `demo-ds-${Date.now()}`,
        name: data.name,
        source: data.source,
        source_path: data.source_path,
        description: data.description || '',
        row_count: null,
        size_bytes: null,
        column_count: null,
        columns: [],
        tags: data.tags || [],
        created_at: new Date().toISOString(),
        version: 1,
      }
      set((s) => ({ datasets: [ds, ...s.datasets] }))
      return
    }
    await api.post('/datasets', data)
    const datasets = await api.get<DatasetItem[]>('/datasets')
    set({ datasets })
  },

  deleteDataset: async (id) => {
    if (isDemoMode()) {
      set((s) => ({
        datasets: s.datasets.filter((d) => d.id !== id),
        selectedId: s.selectedId === id ? null : s.selectedId,
      }))
      return
    }
    await api.delete(`/datasets/${id}`)
    set((s) => ({
      datasets: s.datasets.filter((d) => d.id !== id),
      selectedId: s.selectedId === id ? null : s.selectedId,
    }))
  },

  selectDataset: (id) => set({ selectedId: id }),

  fetchSnapshots: async (datasetId) => {
    if (isDemoMode()) return []
    return api.get<SnapshotItem[]>(`/datasets/${datasetId}/snapshots`)
  },

  createSnapshot: async (datasetId) => {
    if (isDemoMode()) return
    await api.post(`/datasets/${datasetId}/snapshots`)
  },

  restoreSnapshot: async (datasetId, snapshotId) => {
    if (isDemoMode()) return
    await api.post(`/datasets/${datasetId}/snapshots/${snapshotId}/restore`)
    // Refresh datasets to get new version
    await useDatasetStore.getState().fetchDatasets()
  },
}))
