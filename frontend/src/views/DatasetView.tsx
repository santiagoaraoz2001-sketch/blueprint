import { useEffect, useState } from 'react'
import { T, F, FS, FD } from '@/lib/design-tokens'
import { useDatasetStore, type DatasetItem } from '@/stores/datasetStore'
import DatasetPreview from '@/components/Datasets/DatasetPreview'
import RegisterDatasetModal from '@/components/Datasets/RegisterDatasetModal'
import EmptyState from '@/components/shared/EmptyState'
import { Database, Plus, HardDrive, Search } from 'lucide-react'

export default function DatasetView() {
  const { datasets, loading, selectedId, fetchDatasets, selectDataset } = useDatasetStore()
  const [showRegister, setShowRegister] = useState(false)
  const [search, setSearch] = useState('')

  useEffect(() => {
    fetchDatasets()
  }, [fetchDatasets])

  const filtered = datasets.filter(
    (d) =>
      d.name.toLowerCase().includes(search.toLowerCase()) ||
      (d.tags || []).some((t) => t.toLowerCase().includes(search.toLowerCase()))
  )

  const selected = datasets.find((d) => d.id === selectedId)

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div
        style={{
          padding: '12px 16px',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          borderBottom: `1px solid ${T.border}`,
          flexShrink: 0,
        }}
      >
        <h2
          style={{
            fontFamily: FD,
            fontSize: FS.h2,
            fontWeight: 600,
            color: T.text,
            margin: 0,
            letterSpacing: '0.04em',
          }}
        >
          DATASETS
        </h2>

        <div style={{ flex: 1 }} />

        <button
          onClick={() => setShowRegister(true)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            padding: '4px 12px',
            background: `${T.cyan}14`,
            border: `1px solid ${T.cyan}33`,
            color: T.cyan,
            fontFamily: F,
            fontSize: FS.xs,
            letterSpacing: '0.06em',
          }}
        >
          <Plus size={10} />
          REGISTER
        </button>
      </div>

      {loading ? (
        <div style={{ padding: 40, textAlign: 'center' }}>
          <span style={{ fontFamily: F, fontSize: FS.md, color: T.dim }}>Loading...</span>
        </div>
      ) : datasets.length === 0 ? (
        <EmptyState
          icon={Database}
          title="No datasets registered"
          description="Register a dataset to use in your pipelines"
          action={{ label: 'Register Dataset', onClick: () => setShowRegister(true) }}
        />
      ) : (
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          {/* Left: dataset list */}
          <div
            style={{
              width: 280,
              borderRight: `1px solid ${T.border}`,
              display: 'flex',
              flexDirection: 'column',
              flexShrink: 0,
            }}
          >
            {/* Search */}
            <div style={{ padding: 8 }}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  background: T.surface1,
                  border: `1px solid ${T.border}`,
                  padding: '4px 8px',
                }}
              >
                <Search size={10} color={T.dim} />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search datasets..."
                  style={{
                    flex: 1,
                    background: 'none',
                    border: 'none',
                    color: T.text,
                    fontFamily: F,
                    fontSize: FS.sm,
                    outline: 'none',
                  }}
                />
              </div>
            </div>

            {/* List */}
            <div style={{ flex: 1, overflow: 'auto' }}>
              {filtered.map((ds) => (
                <DatasetListItem
                  key={ds.id}
                  dataset={ds}
                  selected={ds.id === selectedId}
                  onClick={() => selectDataset(ds.id)}
                />
              ))}
            </div>
          </div>

          {/* Right: preview */}
          <div style={{ flex: 1, overflow: 'hidden' }}>
            {selected ? (
              <DatasetPreview dataset={selected} />
            ) : (
              <div
                style={{
                  height: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <span style={{ fontFamily: F, fontSize: FS.md, color: T.dim }}>
                  Select a dataset to preview
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {showRegister && <RegisterDatasetModal onClose={() => setShowRegister(false)} />}
    </div>
  )
}

function DatasetListItem({
  dataset,
  selected,
  onClick,
}: {
  dataset: DatasetItem
  selected: boolean
  onClick: () => void
}) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: '8px 12px',
        cursor: 'pointer',
        background: selected ? T.surface2 : 'transparent',
        borderBottom: `1px solid ${T.border}`,
        borderLeft: selected ? `2px solid ${T.cyan}` : '2px solid transparent',
        transition: 'background 0.1s',
      }}
      onMouseEnter={(e) => {
        if (!selected) e.currentTarget.style.background = T.surface1
      }}
      onMouseLeave={(e) => {
        if (!selected) e.currentTarget.style.background = 'transparent'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <HardDrive size={10} color={selected ? T.cyan : T.dim} />
        <span
          style={{
            fontFamily: F,
            fontSize: FS.md,
            fontWeight: 600,
            color: selected ? T.text : T.sec,
          }}
        >
          {dataset.name}
        </span>
      </div>
      <div
        style={{
          fontFamily: F,
          fontSize: FS.xxs,
          color: T.dim,
          marginTop: 3,
          display: 'flex',
          gap: 8,
        }}
      >
        <span>{dataset.source}</span>
        {dataset.row_count != null && <span>{dataset.row_count.toLocaleString()} rows</span>}
      </div>
      {dataset.tags.length > 0 && (
        <div style={{ display: 'flex', gap: 3, marginTop: 4, flexWrap: 'wrap' }}>
          {dataset.tags.slice(0, 3).map((tag) => (
            <span
              key={tag}
              style={{
                padding: '0 4px',
                background: T.surface3,
                fontFamily: F,
                fontSize: FS.xxs,
                color: T.dim,
              }}
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
