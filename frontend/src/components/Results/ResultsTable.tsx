import { type ColumnDef } from '@tanstack/react-table'
import { T, F, FS } from '@/lib/design-tokens'
import DataTable from '@/components/shared/DataTable'
import StatusBadge from '@/components/shared/StatusBadge'
import { runMetricsToTable } from '@/services/metricsBridge'
import { useUIStore } from '@/stores/uiStore'
import { TableProperties } from 'lucide-react'
import toast from 'react-hot-toast'

export interface RunRow {
  id: string
  pipeline_id: string
  status: string
  started_at: string
  finished_at: string | null
  duration_seconds: number | null
  error_message: string | null
  config_snapshot: Record<string, any>
  metrics: Record<string, any>
}

interface ResultsTableProps {
  runs: RunRow[]
  selectedIds: string[]
  onToggleSelect: (id: string) => void
  onRowClick: (run: RunRow) => void
}

function formatDuration(secs: number | null): string {
  if (secs == null) return '—'
  if (secs < 60) return `${secs.toFixed(1)}s`
  const m = Math.floor(secs / 60)
  const s = Math.round(secs % 60)
  return `${m}m ${s}s`
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function ResultsTable({ runs, selectedIds, onToggleSelect, onRowClick }: ResultsTableProps) {
  // Collect all unique metric keys across runs
  const metricKeys = new Set<string>()
  runs.forEach((r) => {
    if (r.metrics) {
      Object.keys(r.metrics).forEach((k) => metricKeys.add(k))
    }
  })

  const columns: ColumnDef<RunRow, any>[] = [
    {
      id: 'select',
      header: '',
      size: 30,
      cell: ({ row }) => (
        <input
          type="checkbox"
          checked={selectedIds.includes(row.original.id)}
          onChange={(e) => {
            e.stopPropagation()
            onToggleSelect(row.original.id)
          }}
          style={{ accentColor: T.cyan }}
        />
      ),
    },
    {
      accessorKey: 'status',
      header: 'Status',
      size: 80,
      cell: ({ getValue }) => <StatusBadge status={getValue() as any} />,
    },
    {
      accessorKey: 'started_at',
      header: 'Date',
      size: 130,
      cell: ({ getValue }) => (
        <span style={{ fontFamily: F, fontSize: FS.sm, color: T.sec }}>
          {formatDate(getValue() as string)}
        </span>
      ),
    },
    {
      accessorKey: 'duration_seconds',
      header: 'Duration',
      size: 80,
      cell: ({ getValue }) => (
        <span style={{ fontFamily: F, fontSize: FS.sm, color: T.sec }}>
          {formatDuration(getValue() as number | null)}
        </span>
      ),
    },
    // Dynamic metric columns
    ...Array.from(metricKeys).slice(0, 6).map(
      (key): ColumnDef<RunRow, any> => ({
        id: `metric_${key}`,
        header: key.split('.').pop() || key,
        size: 90,
        accessorFn: (row) => row.metrics?.[key],
        cell: ({ getValue }) => {
          const v = getValue()
          if (v == null) return <span style={{ color: T.dim }}>—</span>
          const num = typeof v === 'number' ? v : parseFloat(v)
          return (
            <span style={{ fontFamily: F, fontSize: FS.sm, color: T.cyan }}>
              {isNaN(num) ? String(v) : num.toFixed(4)}
            </span>
          )
        },
      })
    ),
    {
      id: 'actions',
      header: '',
      size: 80,
      cell: ({ row }) => (
        <button
          onClick={async (e) => {
            e.stopPropagation()
            try {
              await runMetricsToTable(row.original.id, row.original.pipeline_id)
              useUIStore.getState().setView('data')
            } catch (err: any) {
              toast.error(err.message || 'No metrics available')
            }
          }}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 3,
            padding: '2px 6px',
            background: `${T.cyan}14`,
            border: `1px solid ${T.cyan}33`,
            color: T.cyan,
            fontFamily: F,
            fontSize: FS.xxs,
            cursor: 'pointer',
          }}
        >
          <TableProperties size={9} />
          Analyze
        </button>
      ),
    },
  ]

  return <DataTable data={runs} columns={columns} onRowClick={onRowClick} pageSize={25} />
}
