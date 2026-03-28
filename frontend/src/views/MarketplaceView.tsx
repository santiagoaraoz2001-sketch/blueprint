import { useState, useMemo, useEffect } from 'react'
import { T, F, FS, FD, CATEGORY_COLORS } from '@/lib/design-tokens'
import { getAllBlocks, getBlockDefinition, type BlockDefinition, getBlocksByCategory, getPortColor } from '@/lib/block-registry'
import { getIcon } from '@/lib/icon-utils'
import PanelCard from '@/components/shared/PanelCard'
import BlockDetailPage from '@/components/Marketplace/BlockDetailPage'
import RecipeDetailPage from '@/components/Marketplace/RecipeDetailPage'
import ItemCard from '@/components/Marketplace/ItemCard'
import ItemDetailModal from '@/components/Marketplace/ItemDetailModal'
import PublishForm from '@/components/Marketplace/PublishForm'
import {
  Search, Package, LayoutTemplate, Puzzle, Store, Download,
  ArrowRight, Bookmark, Trash2, PlusCircle, Upload, Star,
} from 'lucide-react'
import { COMMUNITY_RECIPES, type Recipe } from '@/lib/recipes'
import { usePresetStore } from '@/stores/presetStore'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useMarketplaceStore, type MarketplaceItem } from '@/stores/marketplaceStore'
import { AnimatePresence } from 'framer-motion'
import toast from 'react-hot-toast'

type Tab = 'browse' | 'library' | 'recipes' | 'my-items' | 'published' | 'presets'
type SubView = 'main' | 'block-detail' | 'recipe-detail' | 'item-detail'

const CATEGORY_ORDER = ['external', 'data', 'model', 'inference', 'training', 'metrics', 'embedding', 'utilities', 'agents', 'interventions', 'endpoints']
const CATEGORY_LABELS: Record<string, string> = {
  external: 'Sources', data: 'Transforms', model: 'Model Ops', inference: 'Inference', training: 'Training',
  metrics: 'Evaluation', embedding: 'Vectors', utilities: 'Flow Control', agents: 'Agents',
  interventions: 'Gates', endpoints: 'Endpoints',
}

export default function MarketplaceView() {
  const [search, setSearch] = useState('')
  const [activeTab, setActiveTab] = useState<Tab>('browse')
  const [categoryFilter, setCategoryFilter] = useState<string>('')
  const [sortBy, setSortBy] = useState<string>('popular')
  const [marketplaceCategoryFilter, setMarketplaceCategoryFilter] = useState<string>('')

  // Sub-view navigation state
  const [subView, setSubView] = useState<SubView>('main')
  const [selectedBlock, setSelectedBlock] = useState<BlockDefinition | null>(null)
  const [selectedRecipe, setSelectedRecipe] = useState<Recipe | null>(null)
  const [showPublishForm, setShowPublishForm] = useState(false)
  const [actionLoading, setActionLoading] = useState<string | null>(null) // item_id being acted on
  const [confirmUninstall, setConfirmUninstall] = useState<MarketplaceItem | null>(null)

  const applyGeneratedWorkflow = usePipelineStore((s) => s.applyGeneratedWorkflow)

  // Marketplace store
  const {
    items: marketplaceItems, installedItems, publishedItems,
    loading, selectedItem,
    browse, fetchInstalled, fetchPublished,
    installItem, uninstallItem, publishItem, submitReview,
    setSelectedItem, seedMarketplace,
  } = useMarketplaceStore()

  // Load marketplace data on mount
  useEffect(() => {
    seedMarketplace().then(() => {
      browse({ sort: sortBy })
      fetchInstalled()
      fetchPublished()
    })
  }, [])

  // Re-browse when filters change
  useEffect(() => {
    browse({
      category: marketplaceCategoryFilter || undefined,
      search: search && activeTab === 'browse' ? search : undefined,
      sort: sortBy,
    })
  }, [marketplaceCategoryFilter, sortBy])

  // Search debounce for marketplace
  useEffect(() => {
    if (activeTab !== 'browse') return
    const timer = setTimeout(() => {
      browse({
        category: marketplaceCategoryFilter || undefined,
        search: search || undefined,
        sort: sortBy,
      })
    }, 300)
    return () => clearTimeout(timer)
  }, [search, activeTab])

  const filtered = useMemo(() => {
    return getAllBlocks().filter((b) => {
      const q = search.toLowerCase()
      const matchSearch =
        !search ||
        b.name.toLowerCase().includes(q) ||
        b.description.toLowerCase().includes(q) ||
        b.type.toLowerCase().includes(q) ||
        b.aliases?.some((a: string) => a.toLowerCase().includes(q)) ||
        b.tags?.some((t: string) => t.toLowerCase().includes(q))
      const matchCategory = !categoryFilter || b.category === categoryFilter
      return matchSearch && matchCategory
    })
  }, [search, categoryFilter])

  // Handle block detail navigation
  const handleBlockClick = (block: BlockDefinition) => {
    setSelectedBlock(block)
    setSubView('block-detail')
  }

  // Handle recipe detail navigation
  const handleRecipeClick = (recipe: Recipe) => {
    setSelectedRecipe(recipe)
    setSubView('recipe-detail')
  }

  const handleBackFromBlock = () => {
    setSubView('main')
    setSelectedBlock(null)
  }

  const handleBackFromRecipe = () => {
    setSubView('main')
    setSelectedRecipe(null)
  }

  const handleSelectBlockFromRecipe = (block: BlockDefinition) => {
    setSelectedBlock(block)
    setSubView('block-detail')
  }

  const handleItemClick = async (item: MarketplaceItem) => {
    setSelectedItem(item)
    setSubView('item-detail')
  }

  const handleInstallItem = async (itemId: string) => {
    if (actionLoading) return
    setActionLoading(itemId)
    try {
      const success = await installItem(itemId)
      if (success) {
        toast.success('Item installed successfully')
        fetchInstalled()
      } else {
        toast.error('Failed to install item')
      }
    } finally {
      setActionLoading(null)
    }
  }

  const handleUninstallItem = async (itemId: string) => {
    if (actionLoading) return
    setActionLoading(itemId)
    try {
      const success = await uninstallItem(itemId)
      if (success) {
        toast.success('Item uninstalled')
        fetchInstalled()
      } else {
        toast.error('Failed to uninstall item')
      }
    } finally {
      setActionLoading(null)
      setConfirmUninstall(null)
    }
  }

  const handleRequestUninstall = (item: MarketplaceItem) => {
    setConfirmUninstall(item)
  }

  const handlePublish = async (data: Parameters<typeof publishItem>[0]) => {
    const success = await publishItem(data)
    if (success) {
      toast.success('Published to marketplace!')
      setShowPublishForm(false)
      fetchPublished()
      browse({ sort: sortBy })
    } else {
      toast.error('Failed to publish')
    }
  }

  const handleSubmitReview = async (rating: number, text: string) => {
    if (!selectedItem) return
    const success = await submitReview(selectedItem.id, rating, text)
    if (success) {
      toast.success('Review submitted')
    }
  }

  // Sub-view routing
  if (subView === 'block-detail' && selectedBlock) {
    return (
      <AnimatePresence mode="wait">
        <BlockDetailPage
          key={`block-${selectedBlock.type}`}
          block={selectedBlock}
          onBack={handleBackFromBlock}
          onSelectBlock={handleBlockClick}
        />
      </AnimatePresence>
    )
  }

  if (subView === 'recipe-detail' && selectedRecipe) {
    return (
      <AnimatePresence mode="wait">
        <RecipeDetailPage
          key={`recipe-${selectedRecipe.id}`}
          recipe={selectedRecipe}
          onBack={handleBackFromRecipe}
          onSelectBlock={handleSelectBlockFromRecipe}
        />
      </AnimatePresence>
    )
  }

  const tabs: { id: Tab; label: string; icon: typeof Package }[] = [
    { id: 'browse', label: 'MARKETPLACE', icon: Store },
    { id: 'library', label: 'ALL BLOCKS', icon: Package },
    { id: 'recipes', label: 'RECIPES', icon: LayoutTemplate },
    { id: 'my-items', label: 'MY ITEMS', icon: Download },
    { id: 'published', label: 'PUBLISHED', icon: Upload },
    { id: 'presets', label: 'PRESETS', icon: Bookmark },
  ]

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Item Detail Modal */}
      <AnimatePresence>
        {subView === 'item-detail' && selectedItem && (
          <ItemDetailModal
            item={selectedItem}
            onClose={() => { setSubView('main'); setSelectedItem(null) }}
            onInstall={() => handleInstallItem(selectedItem.id)}
            onUninstall={() => handleRequestUninstall(selectedItem)}
            onSubmitReview={handleSubmitReview}
          />
        )}
      </AnimatePresence>

      {/* Uninstall confirmation dialog */}
      {confirmUninstall && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
          zIndex: 1100, display: 'flex', alignItems: 'center', justifyContent: 'center',
        }} onClick={() => setConfirmUninstall(null)}>
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: T.surface1, border: `1px solid ${T.border}`,
              borderTop: `3px solid ${T.red}`, borderRadius: 8,
              padding: 24, maxWidth: 400, width: '90%',
            }}
          >
            <h3 style={{ fontFamily: FD, fontSize: FS.lg, color: T.text, margin: '0 0 8px 0' }}>
              Confirm Uninstall
            </h3>
            <p style={{ fontFamily: F, fontSize: FS.sm, color: T.sec, margin: '0 0 20px 0', lineHeight: 1.5 }}>
              Are you sure you want to uninstall <strong>{confirmUninstall.name}</strong>? This will remove it from your environment.
            </p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button
                onClick={() => setConfirmUninstall(null)}
                style={{
                  padding: '8px 16px', background: T.surface3,
                  border: `1px solid ${T.border}`, borderRadius: 4,
                  color: T.sec, fontFamily: F, fontSize: FS.sm,
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={() => handleUninstallItem(confirmUninstall.id)}
                disabled={actionLoading === confirmUninstall.id}
                style={{
                  padding: '8px 16px', background: `${T.red}20`,
                  border: `1px solid ${T.red}50`, borderRadius: 4,
                  color: T.red, fontFamily: FD, fontSize: FS.sm,
                  fontWeight: 700, cursor: actionLoading ? 'wait' : 'pointer',
                  letterSpacing: '0.06em',
                }}
              >
                {actionLoading === confirmUninstall.id ? 'REMOVING...' : 'UNINSTALL'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div style={{
        padding: '12px 16px',
        display: 'flex', alignItems: 'center', gap: 12,
        borderBottom: `1px solid ${T.border}`, flexShrink: 0,
      }}>
        <h2 style={{
          fontFamily: FD, fontSize: FS.xl * 1.5, fontWeight: 600,
          color: T.text, margin: 0, letterSpacing: '0.04em',
        }}>
          MODULE LIBRARY
        </h2>
        <div style={{ flex: 1 }} />

        {/* Tabs */}
        {tabs.map((tab) => {
          const Icon = tab.icon
          const active = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => { setActiveTab(tab.id); setSearch('') }}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '6px 12px',
                background: active ? `${T.cyan}15` : 'transparent',
                border: active ? `1px solid ${T.cyan}40` : `1px solid ${T.border}`,
                borderRadius: 4,
                color: active ? T.cyan : T.dim,
                fontFamily: F, fontSize: FS.xs, letterSpacing: '0.08em',
                cursor: 'pointer',
              }}
            >
              <Icon size={10} />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex' }}>
        {/* ── Browse Marketplace ── */}
        {activeTab === 'browse' && (
          <>
            {/* Sidebar filters */}
            <div style={{
              width: 200, minWidth: 200, borderRight: `1px solid ${T.border}`,
              display: 'flex', flexDirection: 'column', overflow: 'auto',
              background: T.surface0, padding: '12px 0',
            }}>
              {/* Search */}
              <div style={{
                display: 'flex', alignItems: 'center', gap: 6,
                margin: '0 10px 12px', padding: '6px 10px',
                background: T.surface2, border: `1px solid ${T.border}`, borderRadius: 6,
              }}>
                <Search size={12} color={T.dim} />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search marketplace..."
                  style={{
                    flex: 1, background: 'none', border: 'none',
                    color: T.text, fontFamily: F, fontSize: FS.sm, outline: 'none',
                  }}
                />
              </div>

              {/* Sort */}
              <div style={{ padding: '0 10px', marginBottom: 12 }}>
                <div style={{
                  fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 700,
                  letterSpacing: '0.08em', marginBottom: 6,
                }}>
                  SORT BY
                </div>
                {[
                  { id: 'popular', label: 'Popular' },
                  { id: 'newest', label: 'Newest' },
                  { id: 'rating', label: 'Highest Rated' },
                ].map(s => (
                  <button
                    key={s.id}
                    onClick={() => setSortBy(s.id)}
                    style={{
                      display: 'block', width: '100%', padding: '5px 10px',
                      background: sortBy === s.id ? `${T.cyan}12` : 'transparent',
                      border: 'none', borderLeft: sortBy === s.id ? `3px solid ${T.cyan}` : '3px solid transparent',
                      color: sortBy === s.id ? T.text : T.sec,
                      fontFamily: F, fontSize: FS.sm, fontWeight: sortBy === s.id ? 700 : 500,
                      cursor: 'pointer', textAlign: 'left',
                    }}
                  >
                    {s.label}
                  </button>
                ))}
              </div>

              {/* Category filter */}
              <div style={{
                fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 700,
                letterSpacing: '0.08em', padding: '0 10px', marginBottom: 6,
              }}>
                CATEGORY
              </div>
              <MarketplaceCategoryButton
                label="All Items"
                color={T.cyan}
                active={marketplaceCategoryFilter === ''}
                onClick={() => setMarketplaceCategoryFilter('')}
              />
              {['block', 'template', 'plugin'].map(cat => (
                <MarketplaceCategoryButton
                  key={cat}
                  label={cat === 'block' ? 'Blocks' : cat === 'template' ? 'Templates' : 'Plugins'}
                  color={cat === 'block' ? '#22D3EE' : cat === 'template' ? '#A78BFA' : '#F97316'}
                  active={marketplaceCategoryFilter === cat}
                  onClick={() => setMarketplaceCategoryFilter(cat)}
                />
              ))}
            </div>

            {/* Items grid */}
            <div style={{ flex: 1, overflow: 'auto', padding: 20 }}>
              {loading ? (
                <div style={{ padding: 60, textAlign: 'center' }}>
                  <span style={{ fontFamily: F, fontSize: FS.md, color: T.dim }}>
                    Loading marketplace...
                  </span>
                </div>
              ) : marketplaceItems.length > 0 ? (
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
                  gap: 12,
                }}>
                  {marketplaceItems.map(item => (
                    <ItemCard
                      key={item.id}
                      item={item}
                      onClick={() => handleItemClick(item)}
                      onInstall={() => handleInstallItem(item.id)}
                      isInstalling={actionLoading === item.id}
                    />
                  ))}
                </div>
              ) : (
                <div style={{ padding: 60, textAlign: 'center' }}>
                  <Store size={32} color={T.dim} style={{ marginBottom: 12 }} />
                  <div style={{ fontFamily: F, fontSize: FS.md, color: T.dim }}>
                    No items found
                  </div>
                  <div style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, marginTop: 4 }}>
                    Try a different search or category filter
                  </div>
                </div>
              )}
            </div>
          </>
        )}

        {/* ── Block Library ── */}
        {activeTab === 'library' && (
          <>
            {/* Category sidebar */}
            <div style={{
              width: 200, minWidth: 200, borderRight: `1px solid ${T.border}`,
              display: 'flex', flexDirection: 'column', overflow: 'auto',
              background: T.surface0, padding: '12px 0',
            }}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 6,
                margin: '0 10px 12px', padding: '6px 10px',
                background: T.surface2, border: `1px solid ${T.border}`, borderRadius: 6,
              }}>
                <Search size={12} color={T.dim} />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search blocks..."
                  style={{
                    flex: 1, background: 'none', border: 'none',
                    color: T.text, fontFamily: F, fontSize: FS.sm, outline: 'none',
                  }}
                />
              </div>

              <CategoryButton
                label="All Blocks"
                color={T.cyan}
                count={getAllBlocks().length}
                active={categoryFilter === ''}
                onClick={() => setCategoryFilter('')}
              />

              {CATEGORY_ORDER.map(cat => {
                const blocks = getBlocksByCategory()[cat]
                if (!blocks) return null
                const color = CATEGORY_COLORS[cat] || T.dim
                return (
                  <CategoryButton
                    key={cat}
                    label={CATEGORY_LABELS[cat] || cat}
                    color={color}
                    count={blocks.length}
                    active={categoryFilter === cat}
                    onClick={() => setCategoryFilter(cat)}
                  />
                )
              })}
            </div>

            {/* Block grid */}
            <div style={{ flex: 1, overflow: 'auto', padding: 20 }}>
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
                gap: 12,
              }}>
                {filtered.map((block) => (
                  <BlockCard key={block.type} block={block} onClick={() => handleBlockClick(block)} />
                ))}
              </div>
              {filtered.length === 0 && (
                <div style={{ padding: 60, textAlign: 'center' }}>
                  <span style={{ fontFamily: F, fontSize: FS.md, color: T.dim }}>
                    No blocks match your search
                  </span>
                </div>
              )}
            </div>
          </>
        )}

        {/* ── Recipes ── */}
        {activeTab === 'recipes' && (
          <div style={{ flex: 1, padding: 24, overflow: 'auto' }}>
            <div style={{ maxWidth: 900, margin: '0 auto' }}>
              <h3 style={{ fontFamily: FD, fontSize: FS.xl, color: T.text, marginBottom: 8 }}>Community Recipes</h3>
              <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, marginBottom: 24 }}>
                Pre-built, peer-reviewed pipeline definitions that you can instantly drop into your canvas.
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16 }}>
                {COMMUNITY_RECIPES.map(recipe => (
                  <PanelCard key={recipe.id} accent={T.cyan} onClick={() => handleRecipeClick(recipe)}>
                    <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                          <h4 style={{ fontFamily: FD, fontSize: FS.lg, color: T.text, margin: '0 0 6px 0' }}>{recipe.name}</h4>
                          <div style={{ display: 'flex', gap: 6 }}>
                            {recipe.tags.map(tag => (
                              <span key={tag} style={{
                                padding: '2px 8px', background: T.surface3, borderRadius: 12,
                                fontSize: FS.xxs, fontFamily: F, color: T.sec, border: `1px solid ${T.border}`
                              }}>{tag}</span>
                            ))}
                          </div>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            const idSuffix = '_' + Date.now()
                            const newNodes = recipe.nodes.map(n => ({ ...n, id: n.id + idSuffix }))
                            const newEdges = recipe.edges.map(e => ({
                              ...e, id: e.id + idSuffix,
                              source: e.source + idSuffix, target: e.target + idSuffix
                            }))
                            applyGeneratedWorkflow(newNodes, newEdges)
                            toast.success(`Installed recipe: ${recipe.name}`)
                          }}
                          className="hover-glow"
                          style={{
                            background: `${T.cyan}1A`, color: T.cyan, border: `1px solid ${T.cyan}50`,
                            padding: '6px 14px', borderRadius: 4, fontFamily: FD, fontSize: FS.sm,
                            fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase',
                            display: 'flex', alignItems: 'center', cursor: 'pointer', gap: 6,
                          }}
                        >
                          <PlusCircle size={14} /> Install to Canvas
                        </button>
                      </div>
                      <p style={{ fontFamily: F, fontSize: FS.sm, color: T.sec, margin: 0, lineHeight: 1.5 }}>
                        {recipe.description}
                      </p>
                      <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, marginTop: 8 }}>
                        Includes: {recipe.nodes.map(n => n.data.label).join(' \u2192 ')}
                      </div>
                    </div>
                  </PanelCard>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── My Items (Installed) ── */}
        {activeTab === 'my-items' && (
          <div style={{ flex: 1, padding: 24, overflow: 'auto' }}>
            <div style={{ maxWidth: 900, margin: '0 auto' }}>
              <h3 style={{ fontFamily: FD, fontSize: FS.xl, color: T.text, marginBottom: 8 }}>Installed Items</h3>
              <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, marginBottom: 24 }}>
                Marketplace items currently installed in your environment.
              </p>

              {installedItems.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {installedItems.map(item => (
                    <InstalledItemRow
                      key={item.id}
                      item={item}
                      onUninstall={() => handleRequestUninstall(item)}
                      onClick={() => handleItemClick(item)}
                      isLoading={actionLoading === item.id}
                    />
                  ))}
                </div>
              ) : (
                <div style={{ textAlign: 'center', padding: 40 }}>
                  <Download size={32} color={T.dim} style={{ marginBottom: 12 }} />
                  <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim }}>
                    No marketplace items installed yet. Browse the marketplace to find items.
                  </p>
                </div>
              )}

              {/* Publish section */}
              <div style={{ marginTop: 32, paddingTop: 24, borderTop: `1px solid ${T.border}` }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                  <div>
                    <h3 style={{ fontFamily: FD, fontSize: FS.xl, color: T.text, margin: '0 0 4px 0' }}>Publish</h3>
                    <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, margin: 0 }}>
                      Share your blocks, templates, or plugins with the community.
                    </p>
                  </div>
                  {!showPublishForm && (
                    <button
                      onClick={() => setShowPublishForm(true)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        padding: '8px 16px', background: `${T.cyan}15`,
                        border: `1px solid ${T.cyan}40`, borderRadius: 4,
                        color: T.cyan, fontFamily: FD, fontSize: FS.sm,
                        fontWeight: 700, cursor: 'pointer', letterSpacing: '0.08em',
                      }}
                    >
                      <Upload size={12} /> PUBLISH ITEM
                    </button>
                  )}
                </div>

                {showPublishForm && (
                  <PublishForm
                    onPublish={handlePublish}
                    onCancel={() => setShowPublishForm(false)}
                  />
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── Published ── */}
        {activeTab === 'published' && (
          <div style={{ flex: 1, padding: 24, overflow: 'auto' }}>
            <div style={{ maxWidth: 900, margin: '0 auto' }}>
              <h3 style={{ fontFamily: FD, fontSize: FS.xl, color: T.text, marginBottom: 8 }}>Published Items</h3>
              <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, marginBottom: 24 }}>
                Items you&apos;ve published to the marketplace.
              </p>

              {publishedItems.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {publishedItems.map(item => (
                    <PublishedItemRow
                      key={item.id}
                      item={item}
                      onClick={() => handleItemClick(item)}
                    />
                  ))}
                </div>
              ) : (
                <div style={{ textAlign: 'center', padding: 40 }}>
                  <Upload size={32} color={T.dim} style={{ marginBottom: 12 }} />
                  <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim }}>
                    You haven&apos;t published any items yet. Go to My Items to publish.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Presets ── */}
        {activeTab === 'presets' && <PresetsTab />}
      </div>
    </div>
  )
}

// ── Marketplace Category sidebar button ──
function MarketplaceCategoryButton({ label, color, active, onClick }: {
  label: string; color: string; active: boolean; onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        width: '100%', padding: '7px 16px',
        background: active ? `${color}12` : 'transparent',
        border: 'none', borderLeft: active ? `3px solid ${color}` : '3px solid transparent',
        color: active ? T.text : T.sec,
        fontFamily: F, fontSize: FS.sm, fontWeight: active ? 700 : 500,
        cursor: 'pointer', textAlign: 'left', transition: 'all 0.15s',
      }}
    >
      <span style={{
        width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0,
        boxShadow: active ? `0 0 8px ${color}` : 'none',
      }} />
      {label}
    </button>
  )
}

// ── Category sidebar button ──
function CategoryButton({ label, color, count, active, onClick }: {
  label: string; color: string; count: number; active: boolean; onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        width: '100%', padding: '8px 16px',
        background: active ? `${color}12` : 'transparent',
        border: 'none', borderLeft: active ? `3px solid ${color}` : '3px solid transparent',
        color: active ? T.text : T.sec,
        fontFamily: F, fontSize: FS.sm, fontWeight: active ? 700 : 500,
        cursor: 'pointer', textAlign: 'left', transition: 'all 0.15s',
      }}
    >
      <span style={{
        width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0,
        boxShadow: active ? `0 0 8px ${color}` : 'none',
      }} />
      {label}
      <span style={{
        marginLeft: 'auto', fontFamily: F, fontSize: FS.xxs, color: T.dim,
        background: T.surface3, padding: '1px 6px', borderRadius: 4,
      }}>{count}</span>
    </button>
  )
}

// ── Block card ──
function BlockCard({ block, onClick }: { block: BlockDefinition; onClick: () => void }) {
  const IconComponent = getIcon(block.icon)
  const accent = block.accent || T.cyan
  const maturity = (block as any).maturity

  return (
    <PanelCard accent={accent} onClick={onClick}>
      <div style={{ padding: '14px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 36, height: 36, display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: `${accent}14`, border: `1px solid ${accent}33`, borderRadius: 8,
          }}>
            <IconComponent size={18} color={accent} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontFamily: F, fontSize: FS.md, fontWeight: 700, color: T.text }}>
                {block.name}
              </span>
              {maturity && maturity !== 'stable' && (
                <span style={{
                  fontFamily: F, fontSize: '7px', fontWeight: 700, padding: '1px 5px',
                  borderRadius: 3, letterSpacing: '0.06em', textTransform: 'uppercase' as const,
                  ...(maturity === 'beta'
                    ? { color: '#F59E0B', background: '#F59E0B15', border: '1px solid #F59E0B30' }
                    : { color: '#8B5CF6', background: '#8B5CF615', border: '1px solid #8B5CF630' }),
                }}>
                  {maturity === 'beta' ? 'BETA' : 'EXP'}
                </span>
              )}
            </div>
            <div style={{
              fontFamily: F, fontSize: FS.xxs, color: accent,
              textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600,
            }}>
              {block.category}
            </div>
          </div>
        </div>

        <p style={{
          fontFamily: F, fontSize: FS.sm, color: T.sec, margin: '8px 0',
          lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 3,
          WebkitBoxOrient: 'vertical', overflow: 'hidden',
        }}>
          {block.description}
        </p>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {block.inputs.map((p) => {
              const pc = getPortColor(p.dataType)
              return (
                <span key={`i-${p.id}`} title={`${p.label} (${p.dataType})`} style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: p.required ? pc : 'transparent',
                  border: p.required ? 'none' : `1.5px solid ${pc}`,
                  display: 'block',
                }} />
              )
            })}
            <ArrowRight size={8} color={T.dim} />
            {block.outputs.map((p) => {
              const pc = getPortColor(p.dataType)
              return (
                <span key={`o-${p.id}`} title={`${p.label} (${p.dataType})`} style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: p.required ? pc : 'transparent',
                  border: p.required ? 'none' : `1.5px solid ${pc}`,
                  display: 'block',
                }} />
              )
            })}
          </div>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
            {block.inputs.length} in / {block.outputs.length} out
          </span>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginLeft: 'auto' }}>
            {block.configFields.length} params
          </span>
        </div>
      </div>
    </PanelCard>
  )
}

// ── Installed Item Row ──
function InstalledItemRow({ item, onUninstall, onClick, isLoading }: {
  item: MarketplaceItem; onUninstall: () => void; onClick: () => void; isLoading?: boolean
}) {
  const typeColor = item.item_type === 'block' ? '#22D3EE'
    : item.item_type === 'template' ? '#A78BFA' : '#F97316'

  return (
    <div
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '12px 14px', background: T.surface2,
        border: `1px solid ${T.border}`, borderRadius: 6,
        cursor: 'pointer', transition: 'all 0.15s',
      }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = T.borderHi }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = T.border }}
    >
      <div style={{
        width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: `${typeColor}14`, border: `1px solid ${typeColor}33`, borderRadius: 6,
      }}>
        {item.item_type === 'block' ? <Package size={14} color={typeColor} />
          : item.item_type === 'template' ? <LayoutTemplate size={14} color={typeColor} />
          : <Puzzle size={14} color={typeColor} />}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 700 }}>{item.name}</div>
        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          v{item.version} &middot; {item.item_type} &middot; installed {item.installed_at ? new Date(item.installed_at).toLocaleDateString() : ''}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <Star size={10} color="#F59E0B" fill="#F59E0B" />
        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.sec }}>{item.avg_rating.toFixed(1)}</span>
      </div>
      <button
        onClick={(e) => { e.stopPropagation(); onUninstall() }}
        disabled={isLoading}
        style={{
          padding: '5px 10px', background: `${T.red}10`,
          border: `1px solid ${T.red}30`, borderRadius: 4,
          color: T.red, fontFamily: F, fontSize: FS.xxs,
          fontWeight: 700, cursor: isLoading ? 'wait' : 'pointer',
          letterSpacing: '0.06em', opacity: isLoading ? 0.6 : 1,
        }}
      >
        {isLoading ? 'REMOVING...' : 'UNINSTALL'}
      </button>
    </div>
  )
}

// ── Published Item Row ──
function PublishedItemRow({ item, onClick }: {
  item: MarketplaceItem; onClick: () => void
}) {
  const typeColor = item.item_type === 'block' ? '#22D3EE'
    : item.item_type === 'template' ? '#A78BFA' : '#F97316'

  return (
    <div
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '12px 14px', background: T.surface2,
        border: `1px solid ${T.border}`, borderRadius: 6,
        cursor: 'pointer', transition: 'all 0.15s',
      }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = T.borderHi }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = T.border }}
    >
      <div style={{
        width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: `${typeColor}14`, border: `1px solid ${typeColor}33`, borderRadius: 6,
      }}>
        {item.item_type === 'block' ? <Package size={14} color={typeColor} />
          : item.item_type === 'template' ? <LayoutTemplate size={14} color={typeColor} />
          : <Puzzle size={14} color={typeColor} />}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 700 }}>{item.name}</div>
        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          v{item.version} &middot; {item.item_type} &middot; published {new Date(item.published_at).toLocaleDateString()}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
          <Download size={10} color={T.dim} />
          <span style={{ fontFamily: F, fontSize: FS.xs, color: T.sec }}>{item.downloads.toLocaleString()}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
          <Star size={10} color="#F59E0B" fill="#F59E0B" />
          <span style={{ fontFamily: F, fontSize: FS.xs, color: T.sec }}>{item.avg_rating.toFixed(1)}</span>
        </div>
      </div>
    </div>
  )
}

// ── Presets Tab ──
function PresetsTab() {
  const presets = usePresetStore((s) => s.presets)
  const { deletePreset, publishPreset, unpublishPreset } = usePresetStore()
  const [searchFilter, setSearchFilter] = useState('')

  const grouped = presets.reduce<Record<string, typeof presets>>((acc, p) => {
    if (!acc[p.blockType]) acc[p.blockType] = []
    acc[p.blockType].push(p)
    return acc
  }, {})

  const filteredTypes = Object.keys(grouped).filter(bt => {
    if (!searchFilter) return true
    const q = searchFilter.toLowerCase()
    return bt.toLowerCase().includes(q) || grouped[bt].some(p => p.name.toLowerCase().includes(q))
  })

  return (
    <div style={{ flex: 1, padding: 24, overflow: 'auto' }}>
      <div style={{ maxWidth: 900, margin: '0 auto' }}>
        <h3 style={{ fontFamily: FD, fontSize: FS.xl, color: T.text, marginBottom: 8 }}>Config Presets</h3>
        <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, marginBottom: 16 }}>
          Saved block configurations that you can reuse across pipelines. Save presets from any block&apos;s config panel.
        </p>

        <input
          value={searchFilter}
          onChange={(e) => setSearchFilter(e.target.value)}
          placeholder="Search presets..."
          style={{
            width: '100%', padding: '8px 12px',
            background: T.surface3, border: `1px solid ${T.border}`,
            borderRadius: 4, color: T.text, fontFamily: F, fontSize: FS.sm,
            marginBottom: 20, outline: 'none',
          }}
        />

        {filteredTypes.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Bookmark size={32} color={T.dim} style={{ marginBottom: 12 }} />
            <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim }}>
              {presets.length === 0
                ? 'No presets saved yet. Select a block in the pipeline editor and save its config as a preset.'
                : 'No presets match your search.'}
            </p>
          </div>
        ) : (
          filteredTypes.map(blockType => {
            const blockDef = getBlockDefinition(blockType)
            const blockName = blockDef?.name || blockType
            const accent = blockDef?.accent || T.dim
            return (
              <div key={blockType} style={{ marginBottom: 20 }}>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8,
                  padding: '6px 0', borderBottom: `1px solid ${T.border}`,
                }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: accent }} />
                  <span style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                    {blockName}
                  </span>
                  <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                    ({grouped[blockType].length})
                  </span>
                </div>
                {grouped[blockType].map(preset => (
                  <div
                    key={preset.id}
                    style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '10px 12px', background: T.surface2,
                      border: `1px solid ${T.border}`, borderRadius: 6, marginBottom: 6,
                    }}
                  >
                    <div style={{ flex: 1 }}>
                      <div style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 600 }}>{preset.name}</div>
                      {preset.description && (
                        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 2 }}>{preset.description}</div>
                      )}
                      <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 4 }}>
                        {Object.keys(preset.config).length} config fields &middot; {new Date(preset.createdAt).toLocaleDateString()}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button
                        onClick={() => preset.isPublished ? unpublishPreset(preset.id) : publishPreset(preset.id)}
                        style={{
                          padding: '4px 8px',
                          background: preset.isPublished ? `${T.green}20` : 'transparent',
                          border: `1px solid ${preset.isPublished ? T.green + '50' : T.border}`,
                          borderRadius: 4,
                          color: preset.isPublished ? T.green : T.dim,
                          fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
                        }}
                      >
                        {preset.isPublished ? 'PUBLISHED' : 'PUBLISH'}
                      </button>
                      <button
                        onClick={() => deletePreset(preset.id)}
                        style={{
                          padding: '4px 6px', background: 'none',
                          border: `1px solid ${T.border}`, borderRadius: 4,
                          color: T.dim, cursor: 'pointer',
                        }}
                      >
                        <Trash2 size={10} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
