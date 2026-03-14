import { create } from 'zustand'
import { api } from '@/api/client'

export interface MarketplaceItem {
  id: string
  item_type: 'block' | 'template' | 'plugin'
  name: string
  description: string
  author: string
  version: string
  tags: string[]
  license: string
  downloads: number
  avg_rating: number
  rating_count: number
  reviews: Review[]
  installed: boolean
  installed_at?: string
  published: boolean
  published_at: string
  last_updated: string
  source_path?: string
  is_seed?: boolean
}

export interface Review {
  id: string
  rating: number
  text: string
  author: string
  created_at: string
}

interface BrowseResult {
  items: MarketplaceItem[]
  total: number
  page: number
  per_page: number
  total_pages: number
}

interface MarketplaceState {
  items: MarketplaceItem[]
  installedItems: MarketplaceItem[]
  publishedItems: MarketplaceItem[]
  total: number
  page: number
  totalPages: number
  loading: boolean
  error: string | null
  selectedItem: MarketplaceItem | null

  browse: (params?: {
    category?: string
    search?: string
    sort?: string
    page?: number
    per_page?: number
  }) => Promise<void>
  fetchInstalled: () => Promise<void>
  fetchPublished: () => Promise<void>
  fetchItemDetail: (itemId: string) => Promise<MarketplaceItem | null>
  installItem: (itemId: string) => Promise<boolean>
  uninstallItem: (itemId: string) => Promise<boolean>
  publishItem: (body: {
    type: string
    path: string
    name: string
    description?: string
    tags?: string[]
    license?: string
    author?: string
  }) => Promise<boolean>
  submitReview: (itemId: string, rating: number, text: string) => Promise<boolean>
  setSelectedItem: (item: MarketplaceItem | null) => void
  seedMarketplace: () => Promise<void>
}

export const useMarketplaceStore = create<MarketplaceState>((set, get) => ({
  items: [],
  installedItems: [],
  publishedItems: [],
  total: 0,
  page: 1,
  totalPages: 1,
  loading: false,
  error: null,
  selectedItem: null,

  browse: async (params = {}) => {
    set({ loading: true, error: null })
    try {
      const query = new URLSearchParams()
      if (params.category) query.set('category', params.category)
      if (params.search) query.set('search', params.search)
      if (params.sort) query.set('sort', params.sort)
      if (params.page) query.set('page', String(params.page))
      if (params.per_page) query.set('per_page', String(params.per_page))

      const qs = query.toString()
      const result = await api.get<BrowseResult>(`/marketplace/browse${qs ? `?${qs}` : ''}`)
      set({
        items: result.items,
        total: result.total,
        page: result.page,
        totalPages: result.total_pages,
        loading: false,
      })
    } catch (e: any) {
      set({ loading: false, error: e.message || 'Failed to browse marketplace' })
    }
  },

  fetchInstalled: async () => {
    try {
      const result = await api.get<{ items: MarketplaceItem[] }>('/marketplace/installed')
      set({ installedItems: result.items })
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  fetchPublished: async () => {
    try {
      const result = await api.get<{ items: MarketplaceItem[] }>('/marketplace/published')
      set({ publishedItems: result.items })
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  fetchItemDetail: async (itemId) => {
    try {
      const item = await api.get<MarketplaceItem>(`/marketplace/items/${itemId}`)
      set({ selectedItem: item })
      return item
    } catch {
      return null
    }
  },

  installItem: async (itemId) => {
    try {
      await api.post(`/marketplace/items/${itemId}/install`)
      // Update local state
      const { items, installedItems } = get()
      const updated = items.map(i => i.id === itemId ? { ...i, installed: true, downloads: i.downloads + 1 } : i)
      const installedItem = updated.find(i => i.id === itemId)
      set({
        items: updated,
        installedItems: installedItem
          ? [...installedItems.filter(i => i.id !== itemId), { ...installedItem, installed: true }]
          : installedItems,
      })
      return true
    } catch {
      return false
    }
  },

  uninstallItem: async (itemId) => {
    try {
      await api.post(`/marketplace/items/${itemId}/uninstall`)
      const { items, installedItems } = get()
      set({
        items: items.map(i => i.id === itemId ? { ...i, installed: false } : i),
        installedItems: installedItems.filter(i => i.id !== itemId),
      })
      return true
    } catch {
      return false
    }
  },

  publishItem: async (body) => {
    try {
      const result = await api.post<{ status: string; item_id: string; item: MarketplaceItem }>('/marketplace/publish', body)
      if (result.item) {
        set(s => ({ publishedItems: [...s.publishedItems, result.item] }))
      }
      return true
    } catch {
      return false
    }
  },

  submitReview: async (itemId, rating, text) => {
    try {
      await api.post(`/marketplace/items/${itemId}/review`, { rating, text })
      // Refresh item detail
      await get().fetchItemDetail(itemId)
      return true
    } catch {
      return false
    }
  },

  setSelectedItem: (item) => set({ selectedItem: item }),

  seedMarketplace: async () => {
    try {
      await api.post('/marketplace/seed')
    } catch {
      // Non-critical
    }
  },
}))
