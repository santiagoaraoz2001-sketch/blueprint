import { useState, useEffect } from 'react'
import { T, F, FS, FD } from '@/lib/design-tokens'
import { api } from '@/api/client'
import type { DatasetItem, SnapshotItem } from '@/stores/datasetStore'
import { useDatasetStore } from '@/stores/datasetStore'
import { Trash2, Tag, HardDrive, Rows3, Columns3, Clock, RotateCcw, Camera } from 'lucide-react'
import toast from 'react-hot-toast'

interface Props {
  dataset: DatasetItem
}

interface PreviewData {
  dataset_id: string
  rows: Record<string, any>[]
  total_rows: number
}

function formatBytes(bytes: number | null): string {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function DatasetPreview({ dataset }: Props) {
  const { deleteDataset, fetchSnapshots, createSnapshot, restoreSnapshot } = useDatasetStore()
  const [preview, setPreview] = useState<PreviewData | null>(null)

  const [showHistory, setShowHistory] = useState(false)
  const [snapshots, setSnapshots] = useState<SnapshotItem[]>([])

  const loadSnapshots = () => {
    fetchSnapshots(dataset.id).then(setSnapshots).catch(() => { })
  }

  useEffect(() => {
    api
      .get<PreviewData>(`/datasets/${dataset.id}/preview?rows=20`)
      .then(setPreview)
      .catch(() => setPreview(null))
  }, [dataset.id])

  const handleDelete = async () => {
    try {
      await deleteDataset(dataset.id)
      toast.success('Dataset deleted')
    } catch {
      toast.error('Failed to delete')
    }
  }

  const handleCreateSnapshot = async () => {
    try {
      await createSnapshot(dataset.id)
      toast.success('Snapshot saved')
      loadSnapshots()
    } catch {
      toast.error('Failed to save snapshot')
    }
  }

  const handleRestore = async (snapId: string) => {
    try {
      await restoreSnapshot(dataset.id, snapId)
      toast.success('Restored to snapshot')
      loadSnapshots()
      // Reload preview
      api
        .get<PreviewData>(`/datasets/${dataset.id}/preview?rows=20`)
        .then(setPreview)
        .catch(() => setPreview(null))
    } catch {
      toast.error('Failed to restore snapshot')
    }
  }

  const statStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    fontFamily: F,
    fontSize: FS.sm,
    color: T.sec,
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div
        style={{
          padding: '12px 14px',
          borderBottom: `1px solid ${T.border}`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h3
            style={{
              fontFamily: FD,
              fontSize: FS.xl,
              fontWeight: 600,
              color: T.text,
              margin: 0,
            }}
          >
            {dataset.name} <span style={{ fontSize: FS.sm, color: T.dim, marginLeft: 6 }}>v{dataset.version || 1}</span>
          </h3>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => {
                setShowHistory(!showHistory)
                if (!showHistory) loadSnapshots()
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: '3px 8px',
                background: showHistory ? `${T.cyan}14` : 'transparent',
                border: `1px solid ${showHistory ? `${T.cyan}33` : T.border}`,
                color: showHistory ? T.cyan : T.dim,
                fontFamily: F,
                fontSize: FS.xxs,
              }}
            >
              <Clock size={9} />
              HISTORY
            </button>
            <button
              onClick={handleDelete}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: '3px 8px',
                background: `${T.red}14`,
                border: `1px solid ${T.red}33`,
                color: T.red,
                fontFamily: F,
                fontSize: FS.xxs,
              }}
            >
              <Trash2 size={9} />
              DELETE
            </button>
          </div>
        </div>

        {dataset.description && (
          <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, margin: '6px 0 0' }}>
            {dataset.description}
          </p>
        )}

        {/* Stats */}
        <div style={{ display: 'flex', gap: 16, marginTop: 10 }}>
          <div style={statStyle}>
            <HardDrive size={9} color={T.dim} />
            {formatBytes(dataset.size_bytes)}
          </div>
          <div style={statStyle}>
            <Rows3 size={9} color={T.dim} />
            {dataset.row_count?.toLocaleString() ?? '—'} rows
          </div>
          <div style={statStyle}>
            <Columns3 size={9} color={T.dim} />
            {dataset.column_count ?? dataset.columns?.length ?? '—'} cols
          </div>
        </div>

        {/* Tags */}
        {dataset.tags.length > 0 && (
          <div style={{ display: 'flex', gap: 4, marginTop: 8, flexWrap: 'wrap' }}>
            {dataset.tags.map((tag) => (
              <span
                key={tag}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 3,
                  padding: '1px 6px',
                  background: T.surface3,
                  border: `1px solid ${T.border}`,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  color: T.sec,
                }}
              >
                <Tag size={7} />
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>

      {showHistory && (
        <div style={{
          padding: '12px 14px',
          borderBottom: `1px solid ${T.border}`,
          background: T.surface0,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span style={{ fontFamily: FD, fontSize: FS.sm, fontWeight: 600, color: T.text }}>Time Machine (Last 24h)</span>
            <button
              onClick={handleCreateSnapshot}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '3px 8px', background: T.surface2,
                border: `1px solid ${T.border}`, color: T.sec,
                fontFamily: F, fontSize: FS.xxs,
              }}
            >
              <Camera size={9} />
              SNAPSHOT NOW
            </button>
          </div>
          {snapshots.length === 0 ? (
            <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>No snapshots found. Edit data or snapshot now to enable Time Machine.</div>
          ) : (
            <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 6 }}>
              {snapshots.map(s => (
                <div key={s.id} style={{
                  padding: '6px 10px',
                  background: T.surface1, border: `1px solid ${T.border}`,
                  minWidth: 160, display: 'flex', flexDirection: 'column', gap: 4
                }}>
                  <div style={{ fontFamily: F, fontSize: FS.xs, color: T.text }}>
                    {new Date(s.timestamp * 1000).toLocaleTimeString()}
                  </div>
                  <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                    {formatBytes(s.size_bytes)}
                  </div>
                  <button
                    onClick={() => handleRestore(s.id)}
                    style={{
                      marginTop: 4, display: 'flex', alignItems: 'center', gap: 4,
                      padding: '3px 6px', background: `${T.amber}14`, border: `1px solid ${T.amber}33`, color: T.amber,
                      fontFamily: F, fontSize: FS.xxs,
                    }}
                  >
                    <RotateCcw size={9} />
                    RESTORE
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Preview table */}
      <div style={{ flex: 1, overflow: 'auto', padding: 0 }}>
        {preview && preview.rows.length > 0 ? (
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontFamily: F,
              fontSize: FS.sm,
            }}
          >
            <thead>
              <tr>
                {Object.keys(preview.rows[0]).map((col) => (
                  <th
                    key={col}
                    style={{
                      padding: '5px 8px',
                      textAlign: 'left',
                      background: T.surface2,
                      borderBottom: `1px solid ${T.border}`,
                      color: T.dim,
                      fontSize: FS.xxs,
                      fontWeight: 600,
                      letterSpacing: '0.08em',
                      textTransform: 'uppercase',
                      whiteSpace: 'nowrap',
                      position: 'sticky',
                      top: 0,
                    }}
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.rows.map((row, i) => (
                <tr key={i}>
                  {Object.values(row).map((val, j) => (
                    <td
                      key={j}
                      style={{
                        padding: '4px 8px',
                        borderBottom: `1px solid ${T.border}`,
                        color: T.sec,
                        maxWidth: 200,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {String(val ?? '')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ padding: 30, textAlign: 'center' }}>
            <span style={{ fontFamily: F, fontSize: FS.md, color: T.dim }}>
              {dataset.source_path
                ? 'No preview data available'
                : 'Set a source path to preview data'}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
