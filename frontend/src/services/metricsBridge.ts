import { useDataStore, type DataColumn } from '@/stores/dataStore'
import { useMetricsStore } from '@/stores/metricsStore'
import { api } from '@/api/client'

/**
 * Convert a single run's metrics log into a DataTable.
 * Each metric event becomes a row: timestamp, block, metric_name, value, step
 */
export async function runMetricsToTable(runId: string, runName?: string): Promise<string> {
  let events: { timestamp: string; block: string; metric: string; value: number | string; step: number | string }[] = []

  // Try metricsStore first (if run is loaded)
  const storeRun = useMetricsStore.getState().runs[runId]

  if (storeRun) {
    for (const [blockId, block] of Object.entries(storeRun.blocks)) {
      for (const [metricName, series] of Object.entries(block.metrics)) {
        for (const point of series) {
          events.push({
            timestamp: new Date(point.timestamp * 1000).toISOString(),
            block: block.label || blockId,
            metric: metricName,
            value: point.value,
            step: point.step ?? '',
          })
        }
      }
    }
  }

  // Fallback: fetch from API
  if (events.length === 0) {
    const data = await api.get<any[]>(`/runs/${runId}/metrics-log`)
    events = (data || []).map((e: any) => ({
      timestamp: e.timestamp ? new Date(e.timestamp * 1000).toISOString() : '',
      block: e.block_type || e.node_id || '',
      metric: e.name || '',
      value: e.value ?? '',
      step: e.step ?? '',
    }))
  }

  if (events.length === 0) {
    throw new Error(`No metrics found for run ${runId}`)
  }

  const columns: DataColumn[] = [
    { id: 'timestamp', name: 'Timestamp', type: 'string' },
    { id: 'block', name: 'Block', type: 'string' },
    { id: 'metric', name: 'Metric', type: 'string' },
    { id: 'value', name: 'Value', type: 'number' },
    { id: 'step', name: 'Step', type: 'number' },
  ]

  const tableName = runName || `Run ${runId.slice(0, 8)}`
  return useDataStore.getState().createTable(tableName, columns, events, 'pipeline')
}

/**
 * Convert multiple runs into a comparison table.
 * Pivot: rows = metric names, columns = run names, cells = final values.
 */
export async function comparisonToTable(runIds: string[], runNames?: string[]): Promise<string> {
  const runData: Record<string, Record<string, number>> = {}

  for (let i = 0; i < runIds.length; i++) {
    const id = runIds[i]
    const name = runNames?.[i] || `Run ${id.slice(0, 8)}`

    const run = await api.get<any>(`/runs/${id}`)
    const metrics = run.metrics || {}

    const flat: Record<string, number> = {}
    function flatten(obj: any, prefix = '') {
      for (const [k, v] of Object.entries(obj)) {
        const key = prefix ? `${prefix}.${k}` : k
        if (typeof v === 'number') flat[key] = v
        else if (typeof v === 'object' && v !== null) flatten(v, key)
      }
    }
    flatten(metrics)
    runData[name] = flat
  }

  // Collect all metric names across runs
  const allMetrics = new Set<string>()
  for (const metrics of Object.values(runData)) {
    for (const key of Object.keys(metrics)) allMetrics.add(key)
  }

  const runNamesList = Object.keys(runData)
  const columns: DataColumn[] = [
    { id: 'metric', name: 'Metric', type: 'string' },
    ...runNamesList.map(name => ({ id: name, name, type: 'number' as const })),
  ]

  const rows = Array.from(allMetrics).sort().map(metric => {
    const row: Record<string, any> = { metric }
    for (const name of runNamesList) {
      row[name] = runData[name][metric] ?? null
    }
    return row
  })

  return useDataStore.getState().createTable(
    `Comparison (${runNamesList.length} runs)`, columns, rows, 'pipeline'
  )
}

/**
 * Convert a run's metrics into a time-series table for charting.
 * Rows = steps, columns = metric names. Suitable for VisualizationView line charts.
 */
export async function runMetricsToTimeSeries(runId: string, blockId?: string): Promise<string> {
  const data = await api.get<any[]>(`/runs/${runId}/metrics-log`)

  // Filter to specific block if requested
  const filtered = blockId
    ? (data || []).filter((e: any) => e.node_id === blockId || e.block_type === blockId)
    : (data || []).filter((e: any) => e.name && e.value !== undefined)

  // Pivot: rows = steps, columns = metric names
  const metricNames = new Set(filtered.map((e: any) => e.name as string))
  const stepMap: Record<number, Record<string, number>> = {}

  for (const event of filtered) {
    const step = event.step ?? 0
    if (!stepMap[step]) stepMap[step] = { step }
    stepMap[step][event.name] = event.value
  }

  const columns: DataColumn[] = [
    { id: 'step', name: 'Step', type: 'number' },
    ...Array.from(metricNames).map(name => ({ id: name, name, type: 'number' as const })),
  ]

  const rows = Object.values(stepMap).sort((a, b) => a.step - b.step)

  return useDataStore.getState().createTable(
    `Time Series — Run ${runId.slice(0, 8)}`, columns, rows, 'pipeline'
  )
}

/**
 * Import a JSONL artifact file as a DataTable.
 * Fetches the file content, parses JSONL, and creates a table.
 */
export async function importArtifactAsTable(runId: string, filename: string): Promise<string> {
  const res = await fetch(`/api/runs/${runId}/artifacts/${filename}`)
  if (!res.ok) throw new Error(`Failed to fetch artifact: ${filename}`)
  const text = await res.text()

  const rows: Record<string, any>[] = []
  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue
    try {
      rows.push(JSON.parse(trimmed))
    } catch {
      continue
    }
  }

  if (rows.length === 0) throw new Error('No data found in artifact')

  // Detect columns from all rows
  const allKeys = new Set<string>()
  rows.forEach(row => Object.keys(row).forEach(k => allKeys.add(k)))

  const columns: DataColumn[] = Array.from(allKeys).map(key => {
    const values = rows.map(r => r[key]).filter(v => v != null && v !== '')
    const isNum = values.length > 0 && values.every(v => typeof v === 'number' || (!isNaN(Number(v)) && String(v).trim() !== ''))
    return { id: key, name: key, type: isNum ? 'number' as const : 'string' as const }
  })

  return useDataStore.getState().createTable(
    `${filename} — Run ${runId.slice(0, 8)}`, columns, rows, 'pipeline'
  )
}
