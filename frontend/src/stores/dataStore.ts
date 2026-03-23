import { create } from 'zustand'

export interface DataColumn {
  id: string
  name: string
  type: 'string' | 'number' | 'boolean' | 'date'
  computed?: string
}

export interface DataFilter {
  column: string
  operator: 'eq' | 'neq' | 'gt' | 'lt' | 'gte' | 'lte' | 'contains' | 'not_contains' | 'is_null' | 'not_null'
  value: any
}

export interface DataSort {
  column: string
  direction: 'asc' | 'desc'
}

export interface PivotConfig {
  rowFields: string[]
  columnField: string
  valueField: string
  aggregation: 'sum' | 'mean' | 'count' | 'min' | 'max'
}

export interface DataTable {
  id: string
  name: string
  projectId: string
  source: 'pipeline' | 'upload' | 'computed'
  sourceRef?: string
  columns: DataColumn[]
  rows: Record<string, any>[]
  createdAt: string
  updatedAt: string
}

export interface ColumnStats {
  type: string
  count: number
  nullCount: number
  uniqueCount: number
  min?: number | string
  max?: number | string
  mean?: number
  median?: number
  stdDev?: number
  histogram?: { label: string; count: number }[]
}

interface DataState {
  tables: DataTable[]
  activeTableId: string | null
  filters: DataFilter[]
  sort: DataSort | null
  pivotConfig: PivotConfig | null
  showProfiler: boolean

  setActiveTable: (id: string | null) => void
  createTable: (name: string, columns: DataColumn[], rows: Record<string, any>[], source?: string) => string
  deleteTable: (id: string) => void
  renameTable: (id: string, name: string) => void
  importCSV: (name: string, csvText: string) => string
  addComputedColumn: (tableId: string, name: string, formula: string) => void
  deleteColumn: (tableId: string, columnId: string) => void
  addFilter: (filter: DataFilter) => void
  removeFilter: (index: number) => void
  clearFilters: () => void
  setSort: (sort: DataSort | null) => void
  setPivot: (config: PivotConfig | null) => void
  toggleProfiler: () => void
  getFilteredRows: () => Record<string, any>[]
  getActiveTable: () => DataTable | null
  getColumnStats: (columnId: string) => ColumnStats | null
  exportCSV: (tableId: string) => string
  exportJSON: (tableId: string) => string
}

function generateId(): string {
  return `dt_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

function detectColumnType(values: any[]): 'string' | 'number' | 'boolean' | 'date' {
  const nonNull = values.filter((v) => v != null && v !== '')
  if (nonNull.length === 0) return 'string'

  // Check boolean
  const boolVals = new Set(['true', 'false', '0', '1', 'yes', 'no'])
  if (nonNull.every((v) => boolVals.has(String(v).toLowerCase()))) return 'boolean'

  // Check number
  if (nonNull.every((v) => !isNaN(Number(v)) && String(v).trim() !== '')) return 'number'

  // Check date
  if (nonNull.slice(0, 10).every((v) => !isNaN(Date.parse(String(v))) && String(v).length > 4)) return 'date'

  return 'string'
}

function parseCSV(csvText: string): { headers: string[]; rows: Record<string, any>[] } {
  const lines = csvText.trim().split('\n')
  if (lines.length === 0) return { headers: [], rows: [] }

  // Detect delimiter
  const firstLine = lines[0]
  const tabCount = (firstLine.match(/\t/g) || []).length
  const commaCount = (firstLine.match(/,/g) || []).length
  const delimiter = tabCount > commaCount ? '\t' : ','

  function parseLine(line: string): string[] {
    const fields: string[] = []
    let current = ''
    let inQuotes = false

    for (let i = 0; i < line.length; i++) {
      const char = line[i]
      if (inQuotes) {
        if (char === '"' && line[i + 1] === '"') {
          current += '"'
          i++
        } else if (char === '"') {
          inQuotes = false
        } else {
          current += char
        }
      } else {
        if (char === '"') {
          inQuotes = true
        } else if (char === delimiter) {
          fields.push(current.trim())
          current = ''
        } else {
          current += char
        }
      }
    }
    fields.push(current.trim())
    return fields
  }

  const headers = parseLine(lines[0])
  const rows: Record<string, any>[] = []

  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trim() === '') continue
    const values = parseLine(lines[i])
    const row: Record<string, any> = {}
    headers.forEach((h, j) => {
      row[h] = values[j] ?? null
    })
    rows.push(row)
  }

  return { headers, rows }
}

function coerceValue(value: any, type: 'string' | 'number' | 'boolean' | 'date'): any {
  if (value == null || value === '') return null
  switch (type) {
    case 'number': {
      const n = Number(value)
      return isNaN(n) ? null : n
    }
    case 'boolean': {
      const s = String(value).toLowerCase()
      return s === 'true' || s === '1' || s === 'yes'
    }
    case 'date':
      return String(value)
    default:
      return String(value)
  }
}

function evaluateFormula(formula: string, row: Record<string, any>, columns: DataColumn[]): any {
  try {
    // Build a safe context with column values
    const context: Record<string, any> = {}
    columns.forEach((col) => {
      // Allow access by column name (sanitized for JS identifiers)
      const safeName = col.name.replace(/[^a-zA-Z0-9_]/g, '_')
      context[safeName] = row[col.id] ?? row[col.name] ?? null
    })

    // Replace column references in formula with context values
    let expr = formula
    columns.forEach((col) => {
      const safeName = col.name.replace(/[^a-zA-Z0-9_]/g, '_')
      // Replace exact column name matches
      const escaped = col.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      expr = expr.replace(new RegExp(`\\b${escaped}\\b`, 'g'), safeName)
    })

    // Build function from expression
    const paramNames = Object.keys(context)
    const paramValues = Object.values(context)
    const fn = new Function(...paramNames, `"use strict"; return (${expr});`)
    return fn(...paramValues)
  } catch {
    return null
  }
}

function applyFilter(row: Record<string, any>, filter: DataFilter): boolean {
  const value = row[filter.column]

  switch (filter.operator) {
    case 'eq':
      return value == filter.value
    case 'neq':
      return value != filter.value
    case 'gt':
      return Number(value) > Number(filter.value)
    case 'lt':
      return Number(value) < Number(filter.value)
    case 'gte':
      return Number(value) >= Number(filter.value)
    case 'lte':
      return Number(value) <= Number(filter.value)
    case 'contains':
      return String(value ?? '').toLowerCase().includes(String(filter.value).toLowerCase())
    case 'not_contains':
      return !String(value ?? '').toLowerCase().includes(String(filter.value).toLowerCase())
    case 'is_null':
      return value == null || value === ''
    case 'not_null':
      return value != null && value !== ''
    default:
      return true
  }
}

function compareValues(a: any, b: any, direction: 'asc' | 'desc'): number {
  const mult = direction === 'asc' ? 1 : -1
  if (a == null && b == null) return 0
  if (a == null) return mult
  if (b == null) return -mult
  if (typeof a === 'number' && typeof b === 'number') return (a - b) * mult
  return String(a).localeCompare(String(b)) * mult
}

export const useDataStore = create<DataState>((set, get) => ({
  tables: [],
  activeTableId: null,
  filters: [],
  sort: null,
  pivotConfig: null,
  showProfiler: false,

  setActiveTable: (id) => set({ activeTableId: id, filters: [], sort: null, pivotConfig: null }),

  createTable: (name, columns, rows, source) => {
    const id = generateId()
    const now = new Date().toISOString()
    const table: DataTable = {
      id,
      name,
      projectId: '',
      source: (source as DataTable['source']) || 'upload',
      columns,
      rows,
      createdAt: now,
      updatedAt: now,
    }
    set((s) => ({
      tables: [...s.tables, table],
      activeTableId: id,
    }))
    return id
  },

  deleteTable: (id) =>
    set((s) => ({
      tables: s.tables.filter((t) => t.id !== id),
      activeTableId: s.activeTableId === id ? (s.tables.length > 1 ? s.tables.find((t) => t.id !== id)?.id ?? null : null) : s.activeTableId,
    })),

  renameTable: (id, name) =>
    set((s) => ({
      tables: s.tables.map((t) => (t.id === id ? { ...t, name, updatedAt: new Date().toISOString() } : t)),
    })),

  importCSV: (name, csvText) => {
    const { headers, rows: rawRows } = parseCSV(csvText)
    if (headers.length === 0) return ''

    // Detect types for each column
    const columns: DataColumn[] = headers.map((h) => {
      const values = rawRows.map((r) => r[h])
      const type = detectColumnType(values)
      return { id: h, name: h, type }
    })

    // Coerce values to detected types
    const rows = rawRows.map((raw) => {
      const row: Record<string, any> = {}
      columns.forEach((col) => {
        row[col.id] = coerceValue(raw[col.id], col.type)
      })
      return row
    })

    return get().createTable(name, columns, rows, 'upload')
  },

  addComputedColumn: (tableId, name, formula) =>
    set((s) => ({
      tables: s.tables.map((t) => {
        if (t.id !== tableId) return t
        const colId = name.replace(/[^a-zA-Z0-9_]/g, '_').toLowerCase()
        const newCol: DataColumn = { id: colId, name, type: 'number', computed: formula }
        const newRows = t.rows.map((row) => ({
          ...row,
          [colId]: evaluateFormula(formula, row, t.columns),
        }))

        // Detect type from computed values
        const values = newRows.map((r) => r[colId])
        const detectedType = detectColumnType(values)
        newCol.type = detectedType

        return {
          ...t,
          columns: [...t.columns, newCol],
          rows: newRows,
          updatedAt: new Date().toISOString(),
        }
      }),
    })),

  deleteColumn: (tableId, columnId) =>
    set((s) => ({
      tables: s.tables.map((t) => {
        if (t.id !== tableId) return t
        return {
          ...t,
          columns: t.columns.filter((c) => c.id !== columnId),
          rows: t.rows.map((row) => {
            const newRow = { ...row }
            delete newRow[columnId]
            return newRow
          }),
          updatedAt: new Date().toISOString(),
        }
      }),
    })),

  addFilter: (filter) => set((s) => ({ filters: [...s.filters, filter] })),

  removeFilter: (index) =>
    set((s) => ({ filters: s.filters.filter((_, i) => i !== index) })),

  clearFilters: () => set({ filters: [] }),

  setSort: (sort) => set({ sort }),

  setPivot: (config) => set({ pivotConfig: config }),

  toggleProfiler: () => set((s) => ({ showProfiler: !s.showProfiler })),

  getFilteredRows: () => {
    const { activeTableId, tables, filters, sort } = get()
    const table = tables.find((t) => t.id === activeTableId)
    if (!table) return []

    let rows = [...table.rows]

    // Apply filters
    if (filters.length > 0) {
      rows = rows.filter((row) => filters.every((f) => applyFilter(row, f)))
    }

    // Apply sort
    if (sort) {
      rows.sort((a, b) => compareValues(a[sort.column], b[sort.column], sort.direction))
    }

    return rows
  },

  getActiveTable: () => {
    const { activeTableId, tables } = get()
    return tables.find((t) => t.id === activeTableId) ?? null
  },

  getColumnStats: (columnId) => {
    const table = get().getActiveTable()
    if (!table) return null

    const col = table.columns.find((c) => c.id === columnId)
    if (!col) return null

    const values = table.rows.map((r) => r[columnId])
    const nonNull = values.filter((v) => v != null && v !== '')
    const nullCount = values.length - nonNull.length
    const uniqueCount = new Set(nonNull.map(String)).size

    const stats: ColumnStats = {
      type: col.type,
      count: values.length,
      nullCount,
      uniqueCount,
    }

    if (col.type === 'number') {
      const nums = nonNull.map(Number).filter((n) => !isNaN(n))
      if (nums.length > 0) {
        nums.sort((a, b) => a - b)
        stats.min = nums[0]
        stats.max = nums[nums.length - 1]
        stats.mean = nums.reduce((a, b) => a + b, 0) / nums.length
        const mid = Math.floor(nums.length / 2)
        stats.median = nums.length % 2 === 0 ? (nums[mid - 1] + nums[mid]) / 2 : nums[mid]
        const variance = nums.reduce((sum, n) => sum + Math.pow(n - stats.mean!, 2), 0) / nums.length
        stats.stdDev = Math.sqrt(variance)

        // Build histogram (10 bins)
        const range = (stats.max as number) - (stats.min as number)
        if (range > 0) {
          const binCount = 10
          const binSize = range / binCount
          const bins = Array.from({ length: binCount }, (_, i) => ({
            label: `${((stats.min as number) + i * binSize).toFixed(1)}`,
            count: 0,
          }))
          nums.forEach((n) => {
            const binIdx = Math.min(Math.floor((n - (stats.min as number)) / binSize), binCount - 1)
            bins[binIdx].count++
          })
          stats.histogram = bins
        }
      }
    } else if (col.type === 'string') {
      const sorted = nonNull.map(String).sort()
      if (sorted.length > 0) {
        stats.min = sorted[0]
        stats.max = sorted[sorted.length - 1]
      }

      // Build frequency histogram for top 10 values
      const freq: Record<string, number> = {}
      nonNull.forEach((v) => {
        const s = String(v)
        freq[s] = (freq[s] || 0) + 1
      })
      stats.histogram = Object.entries(freq)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 10)
        .map(([label, count]) => ({ label, count }))
    }

    return stats
  },

  exportCSV: (tableId) => {
    const table = get().tables.find((t) => t.id === tableId)
    if (!table) return ''

    const headers = table.columns.map((c) => c.name)
    const lines = [headers.join(',')]

    table.rows.forEach((row) => {
      const values = table.columns.map((col) => {
        const val = row[col.id]
        if (val == null) return ''
        const str = String(val)
        // Quote if contains comma, newline, or quotes
        if (str.includes(',') || str.includes('\n') || str.includes('"')) {
          return `"${str.replace(/"/g, '""')}"`
        }
        return str
      })
      lines.push(values.join(','))
    })

    return lines.join('\n')
  },

  exportJSON: (tableId) => {
    const table = get().tables.find((t) => t.id === tableId)
    if (!table) return '[]'
    return JSON.stringify(table.rows, null, 2)
  },
}))
