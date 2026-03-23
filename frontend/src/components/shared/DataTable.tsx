import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table'
import { useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { ChevronUp, ChevronDown } from 'lucide-react'

interface DataTableProps<TData> {
  data: TData[]
  columns: ColumnDef<TData, any>[]
  pageSize?: number
  onRowClick?: (row: TData) => void
}

export default function DataTable<TData>({
  data,
  columns,
  pageSize = 20,
  onRowClick,
}: DataTableProps<TData>) {
  const [sorting, setSorting] = useState<SortingState>([])
  const [globalFilter, setGlobalFilter] = useState('')

  const table = useReactTable({
    data,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize } },
  })

  return (
    <div style={{ overflow: 'auto' }}>
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontFamily: F,
          fontSize: FS.md,
        }}
      >
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  onClick={header.column.getToggleSortingHandler()}
                  style={{
                    padding: '6px 8px',
                    textAlign: 'left',
                    background: T.surface2,
                    borderBottom: `1px solid ${T.border}`,
                    color: T.dim,
                    fontSize: FS.xs,
                    fontWeight: 600,
                    letterSpacing: '0.12em',
                    textTransform: 'uppercase',
                    cursor: header.column.getCanSort() ? 'pointer' : 'default',
                    whiteSpace: 'nowrap',
                    userSelect: 'none',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {header.column.getIsSorted() === 'asc' && <ChevronUp size={10} />}
                    {header.column.getIsSorted() === 'desc' && <ChevronDown size={10} />}
                  </div>
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row, i) => (
            <tr
              key={row.id}
              onClick={() => onRowClick?.(row.original)}
              style={{
                background: i % 2 === 0 ? T.surface1 : T.surface0,
                cursor: onRowClick ? 'pointer' : 'default',
                transition: 'background 0.1s',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = T.surface3)}
              onMouseLeave={(e) =>
                (e.currentTarget.style.background = i % 2 === 0 ? T.surface1 : T.surface0)
              }
            >
              {row.getVisibleCells().map((cell) => (
                <td
                  key={cell.id}
                  style={{
                    padding: '5px 8px',
                    borderBottom: `1px solid ${T.border}`,
                    color: T.sec,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      {/* Pagination */}
      {table.getPageCount() > 1 && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '6px 8px',
            borderTop: `1px solid ${T.border}`,
          }}
        >
          <span style={{ fontSize: FS.xxs, color: T.dim }}>
            {table.getFilteredRowModel().rows.length} rows
          </span>
          <div style={{ display: 'flex', gap: 4 }}>
            <button
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
              style={{
                padding: '2px 8px',
                background: T.surface3,
                border: `1px solid ${T.border}`,
                color: table.getCanPreviousPage() ? T.sec : T.dim,
                fontFamily: F,
                fontSize: FS.xxs,
              }}
            >
              PREV
            </button>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, padding: '2px 4px' }}>
              {table.getState().pagination.pageIndex + 1}/{table.getPageCount()}
            </span>
            <button
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
              style={{
                padding: '2px 8px',
                background: T.surface3,
                border: `1px solid ${T.border}`,
                color: table.getCanNextPage() ? T.sec : T.dim,
                fontFamily: F,
                fontSize: FS.xxs,
              }}
            >
              NEXT
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
