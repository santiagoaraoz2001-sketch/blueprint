import { useState, useCallback, useRef, useEffect } from 'react'
import { T, F, FS, FD } from '@/lib/design-tokens'
import { useDataStore, type DataFilter, type DataSort, type DataColumn, type ColumnStats, type PivotConfig } from '@/stores/dataStore'
import { api } from '@/api/client'
import { runMetricsToTable } from '@/services/metricsBridge'
import DataGrid from '@/components/Data/DataGrid'
import EmptyState from '@/components/shared/EmptyState'
import { motion, AnimatePresence } from 'framer-motion'
import toast from 'react-hot-toast'
import {
  Table2,
  Plus,
  Download,
  Upload,
  Filter,
  ArrowUpDown,
  BarChart3,
  Columns,
  X,
  Trash2,
  ChevronDown,
  FileText,
  FileJson,
  PieChart,
  FlaskConical,
} from 'lucide-react'

type RightPanel = 'none' | 'profiler' | 'filter' | 'pivot' | 'formula'

export default function DataView() {
  const {
    tables,
    activeTableId,
    filters,
    sort,
    setActiveTable,
    importCSV,
    deleteTable,
    renameTable,
    addFilter,
    removeFilter,
    clearFilters,
    setSort,
    setPivot,
    pivotConfig,
    getFilteredRows,
    getActiveTable,
    addComputedColumn,
    deleteColumn,
    exportCSV,
    exportJSON,
    getColumnStats,
  } = useDataStore()

  const [rightPanel, setRightPanel] = useState<RightPanel>('none')
  const [showImportModal, setShowImportModal] = useState(false)
  const [showExportMenu, setShowExportMenu] = useState(false)
  const [pivotResult, setPivotResult] = useState<Record<string, any>[] | null>(null)
  const [showRunImport, setShowRunImport] = useState(false)
  const [recentRuns, setRecentRuns] = useState<any[]>([])
  const [runImportLoading, setRunImportLoading] = useState(false)

  // Auto-select table from URL param ?table={tableId}
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const tableParam = params.get('table')
    if (tableParam) {
      const exists = useDataStore.getState().tables.find((t) => t.id === tableParam)
      if (exists) setActiveTable(tableParam)
    }
  }, [setActiveTable])

  // Fetch recent runs when dropdown is opened
  useEffect(() => {
    if (!showRunImport) return
    api.get<any[]>('/runs?status=complete&limit=20')
      .then((runs) => setRecentRuns(runs || []))
      .catch(() => setRecentRuns([]))
  }, [showRunImport])

  const handleImportFromRun = useCallback(async (runId: string, runName?: string) => {
    setRunImportLoading(true)
    try {
      await runMetricsToTable(runId, runName)
      setShowRunImport(false)
    } catch (e: any) {
      toast.error(e.message || 'Failed to import run metrics')
    } finally {
      setRunImportLoading(false)
    }
  }, [])

  const activeTable = getActiveTable()
  const filteredRows = getFilteredRows()

  const togglePanel = useCallback(
    (panel: RightPanel) => {
      setRightPanel((prev) => (prev === panel ? 'none' : panel))
    },
    []
  )

  const handleSort = useCallback(
    (newSort: DataSort) => {
      if (!newSort.column) {
        setSort(null)
      } else {
        setSort(newSort)
      }
    },
    [setSort]
  )

  const handleExport = useCallback(
    (format: 'csv' | 'json') => {
      if (!activeTableId) return
      const content = format === 'csv' ? exportCSV(activeTableId) : exportJSON(activeTableId)
      const blob = new Blob([content], { type: format === 'csv' ? 'text/csv' : 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${activeTable?.name || 'data'}.${format}`
      a.click()
      URL.revokeObjectURL(url)
      setShowExportMenu(false)
    },
    [activeTableId, activeTable, exportCSV, exportJSON]
  )

  const handleApplyPivot = useCallback(
    (config: PivotConfig) => {
      if (!activeTable) return
      setPivot(config)

      // Compute pivot
      const rows = getFilteredRows()
      const grouped: Record<string, Record<string, number[]>> = {}

      rows.forEach((row) => {
        const rowKey = config.rowFields.map((f) => String(row[f] ?? '')).join(' | ')
        const colKey = String(row[config.columnField] ?? '')
        const val = Number(row[config.valueField]) || 0

        if (!grouped[rowKey]) grouped[rowKey] = {}
        if (!grouped[rowKey][colKey]) grouped[rowKey][colKey] = []
        grouped[rowKey][colKey].push(val)
      })

      const aggregate = (vals: number[]): number => {
        switch (config.aggregation) {
          case 'sum':
            return vals.reduce((a, b) => a + b, 0)
          case 'mean':
            return vals.reduce((a, b) => a + b, 0) / vals.length
          case 'count':
            return vals.length
          case 'min':
            return Math.min(...vals)
          case 'max':
            return Math.max(...vals)
          default:
            return vals.reduce((a, b) => a + b, 0)
        }
      }

      const colKeys = [...new Set(rows.map((r) => String(r[config.columnField] ?? '')))]
      const result = Object.entries(grouped).map(([rowKey, cols]) => {
        const row: Record<string, any> = { _rowKey: rowKey }
        colKeys.forEach((ck) => {
          row[ck] = cols[ck] ? aggregate(cols[ck]) : 0
        })
        return row
      })

      setPivotResult(result)
    },
    [activeTable, getFilteredRows, setPivot]
  )

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div
        style={{
          padding: '10px 16px',
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
          DATA MANAGER
        </h2>

        {/* Table tabs */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 2,
            marginLeft: 12,
            overflow: 'auto',
            flex: 1,
          }}
        >
          {tables.map((table) => (
            <TableTab
              key={table.id}
              name={table.name}
              active={table.id === activeTableId}
              onClick={() => setActiveTable(table.id)}
              onDelete={() => deleteTable(table.id)}
              onRename={(name) => renameTable(table.id, name)}
            />
          ))}
          <button
            onClick={() => setShowImportModal(true)}
            aria-label="Import new table"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 24,
              height: 24,
              background: 'transparent',
              border: `1px dashed ${T.border}`,
              color: T.dim,
              cursor: 'pointer',
              transition: 'all 0.15s',
              flexShrink: 0,
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = T.cyan
              e.currentTarget.style.color = T.cyan
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = T.border
              e.currentTarget.style.color = T.dim
            }}
          >
            <Plus size={12} />
          </button>
        </div>

        <div style={{ display: 'flex', gap: 4 }}>
          <ToolbarButton
            icon={Upload}
            label="Import"
            onClick={() => setShowImportModal(true)}
          />
          <div style={{ position: 'relative' }}>
            <ToolbarButton
              icon={FlaskConical}
              label="From Run"
              onClick={() => setShowRunImport((v) => !v)}
            />
            {showRunImport && (
              <div
                style={{
                  position: 'absolute',
                  top: '100%',
                  right: 0,
                  marginTop: 4,
                  background: T.surface2,
                  border: `1px solid ${T.border}`,
                  zIndex: 20,
                  minWidth: 240,
                  maxHeight: 320,
                  overflowY: 'auto',
                  boxShadow: `0 4px 12px ${T.shadow}`,
                }}
              >
                <div style={{ padding: '6px 10px', fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.1em', borderBottom: `1px solid ${T.border}` }}>
                  IMPORT FROM RUN
                </div>
                {recentRuns.length === 0 ? (
                  <div style={{ padding: '10px 12px', fontFamily: F, fontSize: FS.xs, color: T.dim }}>
                    No completed runs found
                  </div>
                ) : (
                  recentRuns.map((run: any) => (
                    <button
                      key={run.id}
                      onClick={() => handleImportFromRun(run.id, run.pipeline_name || run.id.slice(0, 8))}
                      disabled={runImportLoading}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        width: '100%',
                        padding: '6px 10px',
                        background: 'transparent',
                        border: 'none',
                        borderBottom: `1px solid ${T.border}`,
                        color: T.sec,
                        fontFamily: F,
                        fontSize: FS.xs,
                        cursor: runImportLoading ? 'wait' : 'pointer',
                        textAlign: 'left',
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.background = T.surface3 }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
                    >
                      <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#22c55e', flexShrink: 0 }} />
                      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {run.id.slice(0, 8)}
                      </span>
                      {run.started_at && (
                        <span style={{ fontSize: FS.xxs, color: T.dim }}>
                          {new Date(run.started_at).toLocaleDateString()}
                        </span>
                      )}
                    </button>
                  ))
                )}
              </div>
            )}
          </div>
          <div style={{ position: 'relative' }}>
            <ToolbarButton
              icon={Download}
              label="Export"
              onClick={() => setShowExportMenu((v) => !v)}
              disabled={!activeTable}
            />
            {showExportMenu && activeTable && (
              <div
                style={{
                  position: 'absolute',
                  top: '100%',
                  right: 0,
                  marginTop: 4,
                  background: T.surface2,
                  border: `1px solid ${T.border}`,
                  zIndex: 20,
                  minWidth: 120,
                  boxShadow: `0 4px 12px ${T.shadow}`,
                }}
              >
                <ExportMenuItem icon={FileText} label="CSV" onClick={() => handleExport('csv')} />
                <ExportMenuItem icon={FileJson} label="JSON" onClick={() => handleExport('json')} />
              </div>
            )}
          </div>
        </div>
      </div>

      {!activeTable ? (
        <EmptyState
          icon={Table2}
          title="No data tables yet"
          description="Import a CSV file or paste data to get started with data analysis"
          action={{ label: 'Import CSV', onClick: () => setShowImportModal(true) }}
        />
      ) : (
        <>
          {/* Toolbar */}
          <div
            style={{
              padding: '6px 16px',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              borderBottom: `1px solid ${T.border}`,
              flexShrink: 0,
            }}
          >
            <ToolbarButton
              icon={Columns}
              label="Add Column"
              onClick={() => togglePanel('formula')}
              active={rightPanel === 'formula'}
            />
            <ToolbarButton
              icon={Filter}
              label="Filter"
              onClick={() => togglePanel('filter')}
              active={rightPanel === 'filter'}
              badge={filters.length > 0 ? filters.length : undefined}
            />
            <ToolbarButton
              icon={ArrowUpDown}
              label="Sort"
              onClick={() => {
                if (sort) {
                  setSort(null)
                } else if (activeTable.columns.length > 0) {
                  setSort({ column: activeTable.columns[0].id, direction: 'asc' })
                }
              }}
              active={!!sort}
            />
            <ToolbarButton
              icon={PieChart}
              label="Pivot"
              onClick={() => togglePanel('pivot')}
              active={rightPanel === 'pivot'}
            />
            <ToolbarButton
              icon={BarChart3}
              label="Profile"
              onClick={() => togglePanel('profiler')}
              active={rightPanel === 'profiler'}
            />

            {filters.length > 0 && (
              <div style={{ marginLeft: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                  {filters.length} filter{filters.length > 1 ? 's' : ''} active
                </span>
                <button
                  onClick={clearFilters}
                  aria-label="Clear all filters"
                  style={{
                    background: 'none',
                    border: 'none',
                    color: T.red,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    padding: 2,
                  }}
                >
                  <X size={10} />
                </button>
              </div>
            )}

            <div style={{ flex: 1 }} />
          </div>

          {/* Main content area */}
          <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
            {/* Data Grid */}
            <div style={{ flex: 1, overflow: 'hidden' }}>
              {pivotResult && rightPanel === 'pivot' ? (
                <PivotResultView data={pivotResult} />
              ) : (
                <DataGrid
                  columns={activeTable.columns}
                  rows={filteredRows}
                  sort={sort}
                  onSort={handleSort}
                />
              )}
            </div>

            {/* Right Panel */}
            <AnimatePresence>
              {rightPanel !== 'none' && (
                <motion.div
                  initial={{ width: 0, opacity: 0 }}
                  animate={{ width: 280, opacity: 1 }}
                  exit={{ width: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  style={{
                    overflow: 'hidden',
                    borderLeft: `1px solid ${T.border}`,
                    flexShrink: 0,
                  }}
                >
                  <div
                    style={{
                      width: 280,
                      height: '100%',
                      display: 'flex',
                      flexDirection: 'column',
                      background: T.surface1,
                    }}
                  >
                    <PanelHeader
                      title={
                        rightPanel === 'profiler'
                          ? 'Column Profiler'
                          : rightPanel === 'filter'
                            ? 'Filter Manager'
                            : rightPanel === 'pivot'
                              ? 'Pivot Builder'
                              : 'Formula Editor'
                      }
                      onClose={() => setRightPanel('none')}
                    />
                    <div style={{ flex: 1, overflow: 'auto', padding: '8px 12px' }}>
                      {rightPanel === 'profiler' && (
                        <ProfilerPanel
                          columns={activeTable.columns}
                          getColumnStats={getColumnStats}
                        />
                      )}
                      {rightPanel === 'filter' && (
                        <FilterPanel
                          columns={activeTable.columns}
                          filters={filters}
                          onAdd={addFilter}
                          onRemove={removeFilter}
                          onClear={clearFilters}
                        />
                      )}
                      {rightPanel === 'pivot' && (
                        <PivotPanel
                          columns={activeTable.columns}
                          config={pivotConfig}
                          onApply={handleApplyPivot}
                          onClear={() => {
                            setPivot(null)
                            setPivotResult(null)
                          }}
                        />
                      )}
                      {rightPanel === 'formula' && (
                        <FormulaPanel
                          columns={activeTable.columns}
                          tableId={activeTable.id}
                          onAdd={addComputedColumn}
                          onDelete={(colId) => deleteColumn(activeTable.id, colId)}
                        />
                      )}
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Footer */}
          <div
            style={{
              padding: '4px 16px',
              borderTop: `1px solid ${T.border}`,
              display: 'flex',
              alignItems: 'center',
              gap: 16,
              flexShrink: 0,
            }}
          >
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
              {filteredRows.length.toLocaleString()} row{filteredRows.length !== 1 ? 's' : ''}
            </span>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
              {activeTable.columns.length} column{activeTable.columns.length !== 1 ? 's' : ''}
            </span>
            {filters.length > 0 && (
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.amber }}>
                filtered ({activeTable.rows.length.toLocaleString()} total)
              </span>
            )}
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
              Source: {activeTable.source}
            </span>
          </div>
        </>
      )}

      {/* Import Modal */}
      {showImportModal && (
        <ImportModal
          onClose={() => setShowImportModal(false)}
          onImport={(name, csv) => {
            importCSV(name, csv)
            setShowImportModal(false)
          }}
        />
      )}
    </div>
  )
}

/* ─── Sub-components ─────────────────────────────────────── */

function ToolbarButton({
  icon: Icon,
  label,
  onClick,
  active,
  disabled,
  badge,
}: {
  icon: any
  label: string
  onClick: () => void
  active?: boolean
  disabled?: boolean
  badge?: number
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        padding: '3px 8px',
        background: active ? `${T.cyan}14` : 'transparent',
        border: active ? `1px solid ${T.cyan}33` : `1px solid transparent`,
        color: active ? T.cyan : disabled ? T.dim : T.sec,
        fontFamily: F,
        fontSize: FS.xxs,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        cursor: disabled ? 'default' : 'pointer',
        opacity: disabled ? 0.5 : 1,
        transition: 'all 0.15s',
        position: 'relative',
      }}
      onMouseEnter={(e) => {
        if (!disabled && !active) {
          e.currentTarget.style.background = T.surface2
          e.currentTarget.style.color = T.text
        }
      }}
      onMouseLeave={(e) => {
        if (!disabled && !active) {
          e.currentTarget.style.background = 'transparent'
          e.currentTarget.style.color = T.sec
        }
      }}
    >
      <Icon size={11} />
      <span>{label}</span>
      {badge != null && badge > 0 && (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            minWidth: 14,
            height: 14,
            borderRadius: 7,
            background: T.cyan,
            color: T.bg,
            fontSize: FS.xxs,
            fontWeight: 700,
          }}
        >
          {badge}
        </span>
      )}
    </button>
  )
}

function TableTab({
  name,
  active,
  onClick,
  onDelete,
  onRename,
}: {
  name: string
  active: boolean
  onClick: () => void
  onDelete: () => void
  onRename: (name: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState(name)

  return (
    <div
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        padding: '4px 10px',
        background: active ? T.surface2 : 'transparent',
        borderBottom: active ? `2px solid ${T.cyan}` : '2px solid transparent',
        color: active ? T.text : T.dim,
        fontFamily: F,
        fontSize: FS.xs,
        cursor: 'pointer',
        transition: 'all 0.15s',
        whiteSpace: 'nowrap',
      }}
      onMouseEnter={(e) => {
        if (!active) e.currentTarget.style.background = T.surface1
      }}
      onMouseLeave={(e) => {
        if (!active) e.currentTarget.style.background = 'transparent'
      }}
    >
      <Table2 size={10} />
      {editing ? (
        <input
          autoFocus
          value={editName}
          onChange={(e) => setEditName(e.target.value)}
          onBlur={() => {
            if (editName.trim()) onRename(editName.trim())
            setEditing(false)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              if (editName.trim()) onRename(editName.trim())
              setEditing(false)
            }
            if (e.key === 'Escape') setEditing(false)
          }}
          onClick={(e) => e.stopPropagation()}
          style={{
            background: 'none',
            border: `1px solid ${T.cyan}`,
            color: T.text,
            fontFamily: F,
            fontSize: FS.xs,
            padding: '0 4px',
            width: 80,
            outline: 'none',
          }}
        />
      ) : (
        <span
          onDoubleClick={(e) => {
            e.stopPropagation()
            setEditName(name)
            setEditing(true)
          }}
        >
          {name}
        </span>
      )}
      {active && (
        <button
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
          aria-label="Delete table"
          style={{
            background: 'none',
            border: 'none',
            color: T.dim,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            padding: 1,
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = T.red)}
          onMouseLeave={(e) => (e.currentTarget.style.color = T.dim)}
        >
          <X size={10} />
        </button>
      )}
    </div>
  )
}

function ExportMenuItem({ icon: Icon, label, onClick }: { icon: any; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        width: '100%',
        padding: '6px 12px',
        background: 'transparent',
        border: 'none',
        color: T.sec,
        fontFamily: F,
        fontSize: FS.xs,
        cursor: 'pointer',
        textAlign: 'left',
        transition: 'background 0.1s',
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = T.surface3)}
      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
    >
      <Icon size={11} />
      <span>{label}</span>
    </button>
  )
}

function PanelHeader({ title, onClose }: { title: string; onClose: () => void }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '8px 12px',
        borderBottom: `1px solid ${T.border}`,
        flexShrink: 0,
      }}
    >
      <span
        style={{
          fontFamily: FD,
          fontSize: FS.md,
          fontWeight: 600,
          color: T.text,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
        }}
      >
        {title}
      </span>
      <button
        onClick={onClose}
        aria-label="Close panel"
        style={{
          background: 'none',
          border: 'none',
          color: T.dim,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          padding: 2,
        }}
        onMouseEnter={(e) => (e.currentTarget.style.color = T.text)}
        onMouseLeave={(e) => (e.currentTarget.style.color = T.dim)}
      >
        <X size={12} />
      </button>
    </div>
  )
}

/* ─── Import Modal ─────────────────────────────────────── */

function ImportModal({
  onClose,
  onImport,
}: {
  onClose: () => void
  onImport: (name: string, csv: string) => void
}) {
  const [name, setName] = useState('')
  const [csvText, setCsvText] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) {
      if (!name) setName(file.name.replace(/\.[^.]+$/, ''))
      const reader = new FileReader()
      reader.onload = (ev) => {
        setCsvText(ev.target?.result as string || '')
      }
      reader.readAsText(file)
    }
  }

  const canImport = name.trim() && csvText.trim()

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.6)',
        zIndex: 100,
      }}
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.15 }}
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 520,
          background: T.surface,
          border: `1px solid ${T.border}`,
          boxShadow: `0 8px 32px ${T.shadowHeavy}`,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <div
          style={{
            padding: '12px 16px',
            borderBottom: `1px solid ${T.border}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span
            style={{
              fontFamily: FD,
              fontSize: FS.lg,
              fontWeight: 600,
              color: T.text,
              letterSpacing: '0.04em',
            }}
          >
            IMPORT DATA
          </span>
          <button
            onClick={onClose}
            aria-label="Close import modal"
            style={{
              background: 'none',
              border: 'none',
              color: T.dim,
              cursor: 'pointer',
              display: 'flex',
            }}
          >
            <X size={14} />
          </button>
        </div>

        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label
              style={{
                fontFamily: F,
                fontSize: FS.xxs,
                color: T.dim,
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
                display: 'block',
                marginBottom: 4,
              }}
            >
              Table Name
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., sales_data"
              style={{
                width: '100%',
                padding: '6px 10px',
                background: T.surface1,
                border: `1px solid ${T.border}`,
                color: T.text,
                fontFamily: F,
                fontSize: FS.sm,
                outline: 'none',
                boxSizing: 'border-box',
              }}
              onFocus={(e) => (e.currentTarget.style.borderColor = T.cyan)}
              onBlur={(e) => (e.currentTarget.style.borderColor = T.border)}
            />
          </div>

          <div>
            <label
              style={{
                fontFamily: F,
                fontSize: FS.xxs,
                color: T.dim,
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
                display: 'block',
                marginBottom: 4,
              }}
            >
              CSV Data
            </label>
            <div
              onDragOver={(e) => {
                e.preventDefault()
                setDragOver(true)
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              style={{
                border: `2px dashed ${dragOver ? T.cyan : T.border}`,
                transition: 'border-color 0.15s',
                background: dragOver ? `${T.cyan}08` : 'transparent',
              }}
            >
              <textarea
                ref={textareaRef}
                value={csvText}
                onChange={(e) => setCsvText(e.target.value)}
                placeholder="Paste CSV data here or drag & drop a .csv file..."
                rows={10}
                style={{
                  width: '100%',
                  padding: 10,
                  background: T.surface1,
                  border: 'none',
                  color: T.text,
                  fontFamily: F,
                  fontSize: FS.xs,
                  outline: 'none',
                  resize: 'vertical',
                  boxSizing: 'border-box',
                }}
              />
            </div>
          </div>

          {csvText.trim() && (
            <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
              Preview: {csvText.trim().split('\n').length - 1} data rows detected
            </div>
          )}
        </div>

        <div
          style={{
            padding: '10px 16px',
            borderTop: `1px solid ${T.border}`,
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 8,
          }}
        >
          <button
            onClick={onClose}
            style={{
              padding: '5px 14px',
              background: 'transparent',
              border: `1px solid ${T.border}`,
              color: T.sec,
              fontFamily: F,
              fontSize: FS.xs,
              cursor: 'pointer',
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
            }}
          >
            Cancel
          </button>
          <button
            onClick={() => canImport && onImport(name.trim(), csvText)}
            disabled={!canImport}
            style={{
              padding: '5px 14px',
              background: canImport ? `${T.cyan}14` : T.surface2,
              border: `1px solid ${canImport ? `${T.cyan}33` : T.border}`,
              color: canImport ? T.cyan : T.dim,
              fontFamily: F,
              fontSize: FS.xs,
              cursor: canImport ? 'pointer' : 'default',
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              transition: 'all 0.15s',
            }}
          >
            Import
          </button>
        </div>
      </motion.div>
    </div>
  )
}

/* ─── Profiler Panel ─────────────────────────────────────── */

function ProfilerPanel({
  columns,
  getColumnStats,
}: {
  columns: DataColumn[]
  getColumnStats: (colId: string) => ColumnStats | null
}) {
  const [expandedCol, setExpandedCol] = useState<string | null>(null)

  if (columns.length === 0) {
    return (
      <div style={{ padding: 16, color: T.dim, fontFamily: F, fontSize: FS.sm, textAlign: 'center' }}>
        No columns to profile
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {columns.map((col) => {
        const stats = getColumnStats(col.id)
        const expanded = expandedCol === col.id

        return (
          <div
            key={col.id}
            style={{
              border: `1px solid ${T.border}`,
              background: expanded ? T.surface2 : 'transparent',
              transition: 'background 0.15s',
            }}
          >
            <button
              onClick={() => setExpandedCol(expanded ? null : col.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                width: '100%',
                padding: '6px 8px',
                background: 'none',
                border: 'none',
                color: T.text,
                fontFamily: F,
                fontSize: FS.xs,
                cursor: 'pointer',
                textAlign: 'left',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span
                  style={{
                    fontSize: FS.xxs,
                    color: T.cyan,
                    fontWeight: 700,
                    width: 18,
                    textAlign: 'center',
                  }}
                >
                  {col.type === 'number' ? '#' : col.type === 'boolean' ? '\u2713' : 'Aa'}
                </span>
                <span>{col.name}</span>
              </div>
              <ChevronDown
                size={10}
                style={{
                  transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
                  transition: 'transform 0.15s',
                  color: T.dim,
                }}
              />
            </button>

            {expanded && stats && (
              <div style={{ padding: '4px 8px 8px', display: 'flex', flexDirection: 'column', gap: 4 }}>
                <StatRow label="Type" value={stats.type} />
                <StatRow label="Count" value={stats.count.toLocaleString()} />
                <StatRow label="Null" value={stats.nullCount.toLocaleString()} />
                <StatRow label="Unique" value={stats.uniqueCount.toLocaleString()} />
                {stats.min != null && <StatRow label="Min" value={String(stats.min)} />}
                {stats.max != null && <StatRow label="Max" value={String(stats.max)} />}
                {stats.mean != null && <StatRow label="Mean" value={stats.mean.toFixed(4)} />}
                {stats.median != null && <StatRow label="Median" value={stats.median.toFixed(4)} />}
                {stats.stdDev != null && <StatRow label="Std Dev" value={stats.stdDev.toFixed(4)} />}

                {/* Mini histogram */}
                {stats.histogram && stats.histogram.length > 0 && (
                  <div style={{ marginTop: 4 }}>
                    <span
                      style={{
                        fontFamily: F,
                        fontSize: FS.xxs,
                        color: T.dim,
                        letterSpacing: '0.08em',
                        textTransform: 'uppercase',
                      }}
                    >
                      Distribution
                    </span>
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'flex-end',
                        gap: 1,
                        height: 40,
                        marginTop: 4,
                      }}
                    >
                      {(() => {
                        const maxCount = Math.max(...stats.histogram!.map((b) => b.count))
                        return stats.histogram!.map((bin, i) => (
                          <div
                            key={i}
                            title={`${bin.label}: ${bin.count}`}
                            style={{
                              flex: 1,
                              height: maxCount > 0 ? `${(bin.count / maxCount) * 100}%` : '0%',
                              background: T.cyan,
                              opacity: 0.6,
                              minHeight: bin.count > 0 ? 2 : 0,
                              transition: 'height 0.2s',
                            }}
                          />
                        ))
                      })()}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 2 }}>
                      <span style={{ fontFamily: F, fontSize: 5, color: T.dim }}>
                        {stats.histogram![0].label}
                      </span>
                      <span style={{ fontFamily: F, fontSize: 5, color: T.dim }}>
                        {stats.histogram![stats.histogram!.length - 1].label}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>
        {label}
      </span>
      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
        {value}
      </span>
    </div>
  )
}

/* ─── Filter Panel ─────────────────────────────────────── */

const FILTER_OPERATORS = [
  { value: 'eq', label: '= equals' },
  { value: 'neq', label: '!= not equals' },
  { value: 'gt', label: '> greater than' },
  { value: 'lt', label: '< less than' },
  { value: 'gte', label: '>= greater or equal' },
  { value: 'lte', label: '<= less or equal' },
  { value: 'contains', label: 'contains' },
  { value: 'not_contains', label: 'not contains' },
  { value: 'is_null', label: 'is null' },
  { value: 'not_null', label: 'is not null' },
]

function FilterPanel({
  columns,
  filters,
  onAdd,
  onRemove,
  onClear,
}: {
  columns: DataColumn[]
  filters: DataFilter[]
  onAdd: (filter: DataFilter) => void
  onRemove: (index: number) => void
  onClear: () => void
}) {
  const [newCol, setNewCol] = useState(columns[0]?.id ?? '')
  const [newOp, setNewOp] = useState<DataFilter['operator']>('eq')
  const [newVal, setNewVal] = useState('')

  const needsValue = !['is_null', 'not_null'].includes(newOp)

  const handleAdd = () => {
    if (!newCol) return
    if (needsValue && !newVal.trim()) return
    onAdd({ column: newCol, operator: newOp, value: needsValue ? newVal : null })
    setNewVal('')
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Active filters */}
      {filters.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span
              style={{
                fontFamily: F,
                fontSize: FS.xxs,
                color: T.dim,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
              }}
            >
              Active Filters
            </span>
            <button
              onClick={onClear}
              aria-label="Clear all filters"
              style={{
                background: 'none',
                border: 'none',
                color: T.red,
                fontFamily: F,
                fontSize: FS.xxs,
                cursor: 'pointer',
              }}
            >
              Clear All
            </button>
          </div>
          {filters.map((f, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '4px 6px',
                background: T.surface2,
                border: `1px solid ${T.border}`,
              }}
            >
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
                {f.column} {FILTER_OPERATORS.find((o) => o.value === f.operator)?.label || f.operator}{' '}
                {f.value != null ? `"${f.value}"` : ''}
              </span>
              <button
                onClick={() => onRemove(i)}
                aria-label={`Remove filter ${i + 1}`}
                style={{
                  background: 'none',
                  border: 'none',
                  color: T.dim,
                  cursor: 'pointer',
                  display: 'flex',
                  padding: 1,
                }}
              >
                <X size={10} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Add filter form */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.dim,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}
        >
          Add Filter
        </span>

        <SelectInput
          label="Column"
          value={newCol}
          onChange={setNewCol}
          options={columns.map((c) => ({ value: c.id, label: c.name }))}
        />

        <SelectInput
          label="Operator"
          value={newOp}
          onChange={(v) => setNewOp(v as DataFilter['operator'])}
          options={FILTER_OPERATORS}
        />

        {needsValue && (
          <div>
            <label style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, display: 'block', marginBottom: 2 }}>
              Value
            </label>
            <input
              value={newVal}
              onChange={(e) => setNewVal(e.target.value)}
              placeholder="Filter value..."
              style={{
                width: '100%',
                padding: '4px 8px',
                background: T.surface2,
                border: `1px solid ${T.border}`,
                color: T.text,
                fontFamily: F,
                fontSize: FS.xs,
                outline: 'none',
                boxSizing: 'border-box',
              }}
              onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
              onFocus={(e) => (e.currentTarget.style.borderColor = T.cyan)}
              onBlur={(e) => (e.currentTarget.style.borderColor = T.border)}
            />
          </div>
        )}

        <button
          onClick={handleAdd}
          aria-label="Apply filter"
          style={{
            padding: '4px 10px',
            background: `${T.cyan}14`,
            border: `1px solid ${T.cyan}33`,
            color: T.cyan,
            fontFamily: F,
            fontSize: FS.xxs,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            cursor: 'pointer',
            transition: 'all 0.15s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = `${T.cyan}22`
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = `${T.cyan}14`
          }}
        >
          Apply Filter
        </button>
      </div>
    </div>
  )
}

/* ─── Pivot Panel ─────────────────────────────────────── */

function PivotPanel({
  columns,
  config,
  onApply,
  onClear,
}: {
  columns: DataColumn[]
  config: PivotConfig | null
  onApply: (config: PivotConfig) => void
  onClear: () => void
}) {
  const [rowFields, setRowFields] = useState<string[]>(config?.rowFields ?? [])
  const [columnField, setColumnField] = useState(config?.columnField ?? '')
  const [valueField, setValueField] = useState(config?.valueField ?? '')
  const [aggregation, setAggregation] = useState<PivotConfig['aggregation']>(config?.aggregation ?? 'sum')

  const toggleRowField = (field: string) => {
    setRowFields((prev) => (prev.includes(field) ? prev.filter((f) => f !== field) : [...prev, field]))
  }

  const canApply = rowFields.length > 0 && columnField && valueField

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Row fields (multi-select) */}
      <div>
        <label
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.dim,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            display: 'block',
            marginBottom: 4,
          }}
        >
          Row Fields
        </label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {columns.map((col) => (
            <label
              key={col.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '3px 6px',
                background: rowFields.includes(col.id) ? `${T.cyan}12` : 'transparent',
                cursor: 'pointer',
                transition: 'background 0.1s',
              }}
            >
              <input
                type="checkbox"
                checked={rowFields.includes(col.id)}
                onChange={() => toggleRowField(col.id)}
                style={{ accentColor: T.cyan }}
              />
              <span style={{ fontFamily: F, fontSize: FS.xs, color: T.sec }}>{col.name}</span>
            </label>
          ))}
        </div>
      </div>

      <SelectInput
        label="Column Field"
        value={columnField}
        onChange={setColumnField}
        options={[{ value: '', label: 'Select...' }, ...columns.map((c) => ({ value: c.id, label: c.name }))]}
      />

      <SelectInput
        label="Value Field"
        value={valueField}
        onChange={setValueField}
        options={[
          { value: '', label: 'Select...' },
          ...columns.filter((c) => c.type === 'number').map((c) => ({ value: c.id, label: c.name })),
        ]}
      />

      <SelectInput
        label="Aggregation"
        value={aggregation}
        onChange={(v) => setAggregation(v as PivotConfig['aggregation'])}
        options={[
          { value: 'sum', label: 'Sum' },
          { value: 'mean', label: 'Mean' },
          { value: 'count', label: 'Count' },
          { value: 'min', label: 'Min' },
          { value: 'max', label: 'Max' },
        ]}
      />

      <div style={{ display: 'flex', gap: 6 }}>
        <button
          onClick={() => canApply && onApply({ rowFields, columnField, valueField, aggregation })}
          disabled={!canApply}
          aria-label="Apply pivot"
          style={{
            flex: 1,
            padding: '5px 10px',
            background: canApply ? `${T.cyan}14` : T.surface2,
            border: `1px solid ${canApply ? `${T.cyan}33` : T.border}`,
            color: canApply ? T.cyan : T.dim,
            fontFamily: F,
            fontSize: FS.xxs,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            cursor: canApply ? 'pointer' : 'default',
            transition: 'all 0.15s',
          }}
        >
          Apply
        </button>
        {config && (
          <button
            onClick={onClear}
            aria-label="Clear pivot"
            style={{
              padding: '5px 10px',
              background: 'transparent',
              border: `1px solid ${T.border}`,
              color: T.sec,
              fontFamily: F,
              fontSize: FS.xxs,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              cursor: 'pointer',
            }}
          >
            Clear
          </button>
        )}
      </div>
    </div>
  )
}

/* ─── Formula Panel ─────────────────────────────────────── */

function FormulaPanel({
  columns,
  tableId,
  onAdd,
  onDelete,
}: {
  columns: DataColumn[]
  tableId: string
  onAdd: (tableId: string, name: string, formula: string) => void
  onDelete: (columnId: string) => void
}) {
  const [colName, setColName] = useState('')
  const [formula, setFormula] = useState('')

  const computedCols = columns.filter((c) => c.computed)

  const handleAdd = () => {
    if (!colName.trim() || !formula.trim()) return
    onAdd(tableId, colName.trim(), formula.trim())
    setColName('')
    setFormula('')
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Existing computed columns */}
      {computedCols.length > 0 && (
        <div>
          <span
            style={{
              fontFamily: F,
              fontSize: FS.xxs,
              color: T.dim,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              display: 'block',
              marginBottom: 4,
            }}
          >
            Computed Columns
          </span>
          {computedCols.map((col) => (
            <div
              key={col.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '4px 6px',
                background: T.surface2,
                border: `1px solid ${T.border}`,
                marginBottom: 2,
              }}
            >
              <div>
                <div style={{ fontFamily: F, fontSize: FS.xs, color: T.sec }}>{col.name}</div>
                <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, fontStyle: 'italic' }}>
                  = {col.computed}
                </div>
              </div>
              <button
                onClick={() => onDelete(col.id)}
                aria-label={`Delete computed column ${col.name}`}
                style={{
                  background: 'none',
                  border: 'none',
                  color: T.dim,
                  cursor: 'pointer',
                  display: 'flex',
                  padding: 2,
                }}
                onMouseEnter={(e) => (e.currentTarget.style.color = T.red)}
                onMouseLeave={(e) => (e.currentTarget.style.color = T.dim)}
              >
                <Trash2 size={10} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* New computed column form */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.dim,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}
        >
          New Computed Column
        </span>

        <div>
          <label style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, display: 'block', marginBottom: 2 }}>
            Column Name
          </label>
          <input
            value={colName}
            onChange={(e) => setColName(e.target.value)}
            placeholder="e.g., total_price"
            style={{
              width: '100%',
              padding: '4px 8px',
              background: T.surface2,
              border: `1px solid ${T.border}`,
              color: T.text,
              fontFamily: F,
              fontSize: FS.xs,
              outline: 'none',
              boxSizing: 'border-box',
            }}
            onFocus={(e) => (e.currentTarget.style.borderColor = T.cyan)}
            onBlur={(e) => (e.currentTarget.style.borderColor = T.border)}
          />
        </div>

        <div>
          <label style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, display: 'block', marginBottom: 2 }}>
            Formula
          </label>
          <textarea
            value={formula}
            onChange={(e) => setFormula(e.target.value)}
            placeholder="e.g., price * quantity"
            rows={3}
            style={{
              width: '100%',
              padding: '6px 8px',
              background: T.surface2,
              border: `1px solid ${T.border}`,
              color: T.text,
              fontFamily: F,
              fontSize: FS.xs,
              outline: 'none',
              resize: 'vertical',
              boxSizing: 'border-box',
            }}
            onFocus={(e) => (e.currentTarget.style.borderColor = T.cyan)}
            onBlur={(e) => (e.currentTarget.style.borderColor = T.border)}
          />
        </div>

        {/* Available columns hint */}
        <div>
          <span
            style={{
              fontFamily: F,
              fontSize: FS.xxs,
              color: T.dim,
              display: 'block',
              marginBottom: 3,
            }}
          >
            Available columns:
          </span>
          <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
            {columns.filter((c) => !c.computed).map((col) => (
              <span
                key={col.id}
                onClick={() => setFormula((prev) => prev + col.name)}
                style={{
                  padding: '1px 5px',
                  background: T.surface3,
                  border: `1px solid ${T.border}`,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  color: T.cyan,
                  cursor: 'pointer',
                  transition: 'all 0.1s',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = T.cyan
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = T.border
                }}
              >
                {col.name}
              </span>
            ))}
          </div>
        </div>

        <button
          onClick={handleAdd}
          disabled={!colName.trim() || !formula.trim()}
          aria-label="Add computed column"
          style={{
            padding: '5px 10px',
            background: colName.trim() && formula.trim() ? `${T.cyan}14` : T.surface2,
            border: `1px solid ${colName.trim() && formula.trim() ? `${T.cyan}33` : T.border}`,
            color: colName.trim() && formula.trim() ? T.cyan : T.dim,
            fontFamily: F,
            fontSize: FS.xxs,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            cursor: colName.trim() && formula.trim() ? 'pointer' : 'default',
            transition: 'all 0.15s',
          }}
        >
          Add Column
        </button>
      </div>
    </div>
  )
}

/* ─── Pivot Result View ─────────────────────────────────── */

function PivotResultView({ data }: { data: Record<string, any>[] }) {
  if (data.length === 0) {
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
        No pivot results
      </div>
    )
  }

  const allKeys = Object.keys(data[0])

  return (
    <div style={{ overflow: 'auto', height: '100%' }}>
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontFamily: F,
          fontSize: FS.xs,
        }}
      >
        <thead style={{ position: 'sticky', top: 0, zIndex: 2 }}>
          <tr>
            {allKeys.map((key) => (
              <th
                key={key}
                style={{
                  padding: '6px 8px',
                  textAlign: key === '_rowKey' ? 'left' : 'right',
                  background: T.surface2,
                  borderBottom: `1px solid ${T.border}`,
                  borderRight: `1px solid ${T.border}`,
                  color: T.dim,
                  fontSize: FS.xs,
                  fontWeight: 600,
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  whiteSpace: 'nowrap',
                }}
              >
                {key === '_rowKey' ? 'Row' : key}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr
              key={i}
              style={{
                background: i % 2 === 0 ? 'transparent' : T.surface1,
              }}
            >
              {allKeys.map((key) => (
                <td
                  key={key}
                  style={{
                    padding: '4px 8px',
                    borderBottom: `1px solid ${T.border}`,
                    borderRight: `1px solid ${T.border}`,
                    color: key === '_rowKey' ? T.sec : T.cyan,
                    textAlign: key === '_rowKey' ? 'left' : 'right',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {key === '_rowKey'
                    ? String(row[key])
                    : typeof row[key] === 'number'
                      ? row[key].toFixed(2)
                      : String(row[key] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ─── Shared Components ──────────────────────────────── */

function SelectInput({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <div>
      <label
        style={{
          fontFamily: F,
          fontSize: FS.xxs,
          color: T.dim,
          display: 'block',
          marginBottom: 2,
          letterSpacing: '0.06em',
        }}
      >
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width: '100%',
          padding: '4px 8px',
          background: T.surface2,
          border: `1px solid ${T.border}`,
          color: T.text,
          fontFamily: F,
          fontSize: FS.xs,
          outline: 'none',
          boxSizing: 'border-box',
        }}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  )
}
