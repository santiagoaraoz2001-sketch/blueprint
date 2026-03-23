import { useState, useMemo } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table'
import { T, F, FS } from '@/lib/design-tokens'
import { ChevronUp, ChevronDown } from 'lucide-react'
import type { DataColumn, DataSort } from '@/stores/dataStore'

interface DataGridProps {
  columns: DataColumn[]
  rows: Record<string, any>[]
  sort: DataSort | null
  onSort: (sort: DataSort) => void
  onRowClick?: (row: Record<string, any>, index: number) => void
}

const TYPE_INDICATORS: Record<string, string> = {
  number: '#',
  string: 'Aa',
  boolean: '\u2713',
  date: '\uD83D\uDCC5',
}

export default function DataGrid({ columns, rows, sort, onSort, onRowClick }: DataGridProps) {
  const [selectedRowIdx, setSelectedRowIdx] = useState<number | null>(null)

  const sortingState: SortingState = useMemo(() => {
    if (!sort) return []
    const col = columns.find((c) => c.id === sort.column)
    if (!col) return []
    return [{ id: sort.column, desc: sort.direction === 'desc' }]
  }, [sort, columns])

  const tableColumns: ColumnDef<Record<string, any>, any>[] = useMemo(() => {
    const cols: ColumnDef<Record<string, any>, any>[] = [
      {
        id: '_row_num',
        header: '#',
        size: 48,
        enableSorting: false,
        cell: ({ row }) => (
          <span style={{ color: T.dim, fontFamily: F, fontSize: FS.xxs }}>
            {row.index + 1}
          </span>
        ),
      },
      ...columns.map(
        (col): ColumnDef<Record<string, any>, any> => ({
          id: col.id,
          accessorKey: col.id,
          header: () => (
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 16,
                  height: 14,
                  borderRadius: 2,
                  background: `${T.cyan}18`,
                  color: T.cyan,
                  fontSize: FS.xxs,
                  fontWeight: 700,
                  flexShrink: 0,
                }}
              >
                {TYPE_INDICATORS[col.type] || '?'}
              </span>
              <span>{col.name}</span>
              {col.computed && (
                <span style={{ color: T.purple, fontSize: FS.xxs, fontStyle: 'italic' }}>fx</span>
              )}
            </div>
          ),
          cell: ({ getValue }) => {
            const value = getValue()
            if (value == null) return <span style={{ color: T.dim, fontStyle: 'italic' }}>null</span>
            if (col.type === 'boolean') {
              return (
                <span style={{ color: value ? T.green : T.red }}>
                  {value ? 'true' : 'false'}
                </span>
              )
            }
            if (col.type === 'number') {
              const num = Number(value)
              return (
                <span style={{ color: T.cyan }}>
                  {isNaN(num) ? String(value) : Number.isInteger(num) ? num.toLocaleString() : num.toFixed(4)}
                </span>
              )
            }
            return (
              <span
                style={{
                  maxWidth: 200,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  display: 'block',
                }}
                title={String(value)}
              >
                {String(value)}
              </span>
            )
          },
          meta: { type: col.type },
        })
      ),
    ]
    return cols
  }, [columns])

  const table = useReactTable({
    data: rows,
    columns: tableColumns,
    state: { sorting: sortingState },
    onSortingChange: (updater) => {
      const newSorting = typeof updater === 'function' ? updater(sortingState) : updater
      if (newSorting.length > 0) {
        onSort({ column: newSorting[0].id, direction: newSorting[0].desc ? 'desc' : 'asc' })
      } else {
        onSort({ column: '', direction: 'asc' })
      }
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 100 } },
    manualSorting: false,
  })

  const handleRowClick = (row: Record<string, any>, index: number) => {
    setSelectedRowIdx(index)
    onRowClick?.(row, index)
  }

  if (rows.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          color: T.dim,
          fontFamily: F,
          fontSize: FS.md,
        }}
      >
        No data to display
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ flex: 1, overflow: 'auto' }}>
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontFamily: F,
            fontSize: FS.xs,
          }}
        >
          <thead style={{ position: 'sticky', top: 0, zIndex: 2 }}>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((header) => {
                  const isSorted = header.column.getIsSorted()
                  const colMeta = header.column.columnDef.meta as { type?: string } | undefined
                  const isNumber = colMeta?.type === 'number'

                  return (
                    <th
                      key={header.id}
                      onClick={header.column.getCanSort() ? header.column.getToggleSortingHandler() : undefined}
                      style={{
                        padding: '6px 8px',
                        textAlign: isNumber ? 'right' : 'left',
                        background: T.surface2,
                        borderBottom: `1px solid ${T.border}`,
                        borderRight: `1px solid ${T.border}`,
                        color: isSorted ? T.text : T.dim,
                        fontSize: FS.xs,
                        fontWeight: 600,
                        letterSpacing: '0.1em',
                        textTransform: 'uppercase',
                        cursor: header.column.getCanSort() ? 'pointer' : 'default',
                        whiteSpace: 'nowrap',
                        userSelect: 'none',
                        transition: 'color 0.15s',
                        position: 'relative',
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 4,
                          justifyContent: isNumber ? 'flex-end' : 'flex-start',
                        }}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {isSorted === 'asc' && <ChevronUp size={10} strokeWidth={2.5} color={T.cyan} />}
                        {isSorted === 'desc' && <ChevronDown size={10} strokeWidth={2.5} color={T.cyan} />}
                      </div>
                    </th>
                  )
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row, i) => {
              const isSelected = selectedRowIdx === row.index
              return (
                <tr
                  key={row.id}
                  onClick={() => handleRowClick(row.original, row.index)}
                  style={{
                    background: isSelected
                      ? `${T.cyan}15`
                      : i % 2 === 0
                        ? 'transparent'
                        : T.surface1,
                    cursor: 'pointer',
                    transition: 'background 0.1s',
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected) e.currentTarget.style.background = T.surface2
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) {
                      e.currentTarget.style.background = i % 2 === 0 ? 'transparent' : T.surface1
                    }
                  }}
                >
                  {row.getVisibleCells().map((cell) => {
                    const colMeta = cell.column.columnDef.meta as { type?: string } | undefined
                    const isNumber = colMeta?.type === 'number'

                    return (
                      <td
                        key={cell.id}
                        style={{
                          padding: '4px 8px',
                          borderBottom: `1px solid ${T.border}`,
                          borderRight: `1px solid ${T.border}`,
                          color: T.sec,
                          whiteSpace: 'nowrap',
                          textAlign: isNumber ? 'right' : 'left',
                          maxWidth: 250,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {table.getPageCount() > 1 && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '4px 8px',
            borderTop: `1px solid ${T.border}`,
            gap: 6,
            flexShrink: 0,
          }}
        >
          <PaginationButton
            label="FIRST"
            onClick={() => table.setPageIndex(0)}
            disabled={!table.getCanPreviousPage()}
          />
          <PaginationButton
            label="PREV"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          />
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, padding: '2px 6px' }}>
            {table.getState().pagination.pageIndex + 1} / {table.getPageCount()}
          </span>
          <PaginationButton
            label="NEXT"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          />
          <PaginationButton
            label="LAST"
            onClick={() => table.setPageIndex(table.getPageCount() - 1)}
            disabled={!table.getCanNextPage()}
          />
        </div>
      )}
    </div>
  )
}

function PaginationButton({
  label,
  onClick,
  disabled,
}: {
  label: string
  onClick: () => void
  disabled: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      style={{
        padding: '2px 8px',
        background: T.surface3,
        border: `1px solid ${T.border}`,
        color: disabled ? T.dim : T.sec,
        fontFamily: F,
        fontSize: FS.xxs,
        letterSpacing: '0.08em',
        cursor: disabled ? 'default' : 'pointer',
        opacity: disabled ? 0.5 : 1,
        transition: 'all 0.15s',
      }}
    >
      {label}
    </button>
  )
}
