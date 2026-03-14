import { useState, useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useSweepStore } from '@/stores/sweepStore'
import { getBlockDefinition } from '@/lib/block-registry'
import { X, Play, Grid3X3, Shuffle, Plus, Minus } from 'lucide-react'
import toast from 'react-hot-toast'

interface RangeEntry {
  param: string
  type: 'grid' | 'uniform' | 'log_uniform' | 'choice' | 'int_range'
  values: string  // comma-separated for grid/choice
  min: string
  max: string
  step: string
}

interface SweepConfigPanelProps {
  nodeId: string
  onClose: () => void
}

export default function SweepConfigPanel({ nodeId, onClose }: SweepConfigPanelProps) {
  const nodes = usePipelineStore((s) => s.nodes)
  const pipelineId = usePipelineStore((s) => s.id)
  const node = nodes.find((n) => n.id === nodeId)
  const createSweep = useSweepStore((s) => s.createSweep)
  const startSweep = useSweepStore((s) => s.startSweep)

  const [searchType, setSearchType] = useState<'grid' | 'random'>('grid')
  const [metricName, setMetricName] = useState('')
  const [nSamples, setNSamples] = useState(10)
  const [ranges, setRanges] = useState<RangeEntry[]>([
    { param: '', type: 'grid', values: '', min: '', max: '', step: '' },
  ])
  const [submitting, setSubmitting] = useState(false)

  // Get config fields from block definition
  const blockDef = node ? getBlockDefinition(node.data.type) : null
  const configFields = useMemo(() => {
    if (!blockDef?.configFields) return []
    return blockDef.configFields.filter(
      (f: { type: string }) => f.type === 'integer' || f.type === 'float' || f.type === 'select' || f.type === 'string'
    )
  }, [blockDef])

  const addRange = () => {
    setRanges([...ranges, { param: '', type: 'grid', values: '', min: '', max: '', step: '' }])
  }

  const removeRange = (i: number) => {
    setRanges(ranges.filter((_, idx) => idx !== i))
  }

  const updateRange = (i: number, field: keyof RangeEntry, value: string) => {
    const updated = [...ranges]
    updated[i] = { ...updated[i], [field]: value }
    setRanges(updated)
  }

  const buildRanges = (): Record<string, any> | null => {
    if (!metricName.trim()) {
      toast.error('Metric name is required')
      return null
    }

    const result: Record<string, any> = {}
    const seenParams = new Set<string>()

    for (const r of ranges) {
      if (!r.param) continue

      // Check for duplicate parameter names
      if (seenParams.has(r.param)) {
        toast.error(`Duplicate parameter: "${r.param}"`)
        return null
      }
      seenParams.add(r.param)

      if (searchType === 'grid') {
        // Grid: parse comma-separated values
        const vals = r.values
          .split(',')
          .map((v) => v.trim())
          .filter(Boolean)
          .map((v) => (isNaN(Number(v)) ? v : Number(v)))
        if (vals.length === 0) {
          toast.error(`No values for parameter "${r.param}"`)
          return null
        }
        result[r.param] = vals
      } else {
        // Random: build distribution spec
        if (r.type === 'choice') {
          const vals = r.values
            .split(',')
            .map((v) => v.trim())
            .filter(Boolean)
            .map((v) => (isNaN(Number(v)) ? v : Number(v)))
          if (vals.length === 0) {
            toast.error(`No values for parameter "${r.param}"`)
            return null
          }
          result[r.param] = { type: 'choice', values: vals }
        } else if (r.type === 'uniform' || r.type === 'log_uniform' || r.type === 'int_range') {
          const minVal = Number(r.min)
          const maxVal = Number(r.max)
          if (isNaN(minVal) || isNaN(maxVal)) {
            toast.error(`Invalid min/max for parameter "${r.param}"`)
            return null
          }
          if (minVal > maxVal) {
            toast.error(`Min > max for parameter "${r.param}"`)
            return null
          }
          if (r.type === 'log_uniform' && minVal <= 0) {
            toast.error(`Log uniform min must be > 0 for "${r.param}"`)
            return null
          }
          result[r.param] = { type: r.type, min: minVal, max: maxVal }
        }
      }
    }

    if (Object.keys(result).length === 0) {
      toast.error('Add at least one parameter range')
      return null
    }

    return result
  }

  const handleSubmit = async () => {
    if (!pipelineId || !nodeId) return

    const rangesData = buildRanges()
    if (!rangesData) return

    setSubmitting(true)
    try {
      const sweepId = await createSweep({
        pipeline_id: pipelineId,
        target_node_id: nodeId,
        metric_name: metricName,
        search_type: searchType,
        ranges: rangesData,
        n_samples: nSamples,
      })

      if (sweepId) {
        await startSweep(sweepId)
        toast.success(`Sweep started with ${useSweepStore.getState().configs.length} configs`)
        onClose()
      }
    } catch {
      toast.error('Failed to start sweep')
    } finally {
      setSubmitting(false)
    }
  }

  if (!node) return null

  const s = styles

  return (
    <div style={s.container}>
      {/* Header */}
      <div style={s.header}>
        <Grid3X3 size={14} color={T.cyan} />
        <span style={s.headerTitle}>Parameter Sweep</span>
        <span style={s.headerSub}>{node.data.label || node.data.type}</span>
        <div style={{ flex: 1 }} />
        <button onClick={onClose} style={s.closeBtn}>
          <X size={12} />
        </button>
      </div>

      {/* Search Type Toggle */}
      <div style={s.section}>
        <label style={s.label}>SEARCH TYPE</label>
        <div style={s.toggleRow}>
          <button
            onClick={() => setSearchType('grid')}
            style={{
              ...s.toggleBtn,
              background: searchType === 'grid' ? `${T.cyan}20` : T.surface2,
              borderColor: searchType === 'grid' ? `${T.cyan}60` : T.border,
              color: searchType === 'grid' ? T.cyan : T.dim,
            }}
          >
            <Grid3X3 size={11} /> Grid
          </button>
          <button
            onClick={() => setSearchType('random')}
            style={{
              ...s.toggleBtn,
              background: searchType === 'random' ? `${T.cyan}20` : T.surface2,
              borderColor: searchType === 'random' ? `${T.cyan}60` : T.border,
              color: searchType === 'random' ? T.cyan : T.dim,
            }}
          >
            <Shuffle size={11} /> Random
          </button>
        </div>
      </div>

      {/* Metric */}
      <div style={s.section}>
        <label style={s.label}>METRIC TO TRACK</label>
        <input
          value={metricName}
          onChange={(e) => setMetricName(e.target.value)}
          placeholder="block_type.eval_loss"
          style={s.input}
        />
      </div>

      {/* Random: n_samples */}
      {searchType === 'random' && (
        <div style={s.section}>
          <label style={s.label}>NUMBER OF SAMPLES</label>
          <input
            type="number"
            value={nSamples}
            onChange={(e) => setNSamples(parseInt(e.target.value) || 10)}
            min={1}
            max={100}
            style={s.input}
          />
        </div>
      )}

      {/* Parameter Ranges */}
      <div style={s.section}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <label style={s.label}>PARAMETER RANGES</label>
          <button onClick={addRange} style={s.addBtn}>
            <Plus size={10} /> Add
          </button>
        </div>

        {ranges.map((r, i) => (
          <div key={i} style={s.rangeCard}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {/* Param name — either select from config fields or free-text */}
              {configFields.length > 0 ? (
                <select
                  value={r.param}
                  onChange={(e) => updateRange(i, 'param', e.target.value)}
                  style={{ ...s.input, flex: 1 }}
                >
                  <option value="">Select param...</option>
                  {configFields.map((f: { name: string; label?: string }) => (
                    <option key={f.name} value={f.name}>
                      {f.label || f.name}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  value={r.param}
                  onChange={(e) => updateRange(i, 'param', e.target.value)}
                  placeholder="param_name"
                  style={{ ...s.input, flex: 1 }}
                />
              )}
              <button onClick={() => removeRange(i)} style={s.removeBtn}>
                <Minus size={10} />
              </button>
            </div>

            {searchType === 'random' && (
              <select
                value={r.type}
                onChange={(e) => updateRange(i, 'type', e.target.value)}
                style={{ ...s.input, marginTop: 4 }}
              >
                <option value="uniform">Uniform</option>
                <option value="log_uniform">Log Uniform</option>
                <option value="choice">Choice</option>
                <option value="int_range">Int Range</option>
              </select>
            )}

            {(searchType === 'grid' || r.type === 'choice') ? (
              <input
                value={r.values}
                onChange={(e) => updateRange(i, 'values', e.target.value)}
                placeholder="1e-5, 5e-5, 1e-4"
                style={{ ...s.input, marginTop: 4 }}
              />
            ) : (
              <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
                <input
                  value={r.min}
                  onChange={(e) => updateRange(i, 'min', e.target.value)}
                  placeholder="min"
                  style={{ ...s.input, flex: 1 }}
                />
                <input
                  value={r.max}
                  onChange={(e) => updateRange(i, 'max', e.target.value)}
                  placeholder="max"
                  style={{ ...s.input, flex: 1 }}
                />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Preview */}
      {ranges.some((r) => r.param) && searchType === 'grid' && (
        <div style={s.section}>
          <label style={s.label}>PREVIEW</label>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
            {(() => {
              const counts = ranges
                .filter((r) => r.param && r.values)
                .map((r) => r.values.split(',').filter((v) => v.trim()).length)
              const total = counts.reduce((a, b) => a * b, 1)
              return `${total} combination${total !== 1 ? 's' : ''}`
            })()}
          </span>
        </div>
      )}

      {/* Submit */}
      <div style={{ padding: '8px 12px' }}>
        <button
          onClick={handleSubmit}
          disabled={submitting}
          style={{
            ...s.submitBtn,
            opacity: submitting ? 0.5 : 1,
            cursor: submitting ? 'not-allowed' : 'pointer',
          }}
        >
          <Play size={12} />
          {submitting ? 'Starting...' : 'Start Sweep'}
        </button>
      </div>
    </div>
  )
}

const styles = {
  container: {
    display: 'flex' as const,
    flexDirection: 'column' as const,
    background: T.surface,
    border: `1px solid ${T.border}`,
    width: 320,
    maxHeight: 520,
    overflowY: 'auto' as const,
  },
  header: {
    display: 'flex' as const,
    alignItems: 'center' as const,
    gap: 6,
    padding: '8px 12px',
    borderBottom: `1px solid ${T.border}`,
  },
  headerTitle: {
    fontFamily: F,
    fontSize: FS.sm,
    fontWeight: 700,
    color: T.text,
    letterSpacing: '0.04em',
  },
  headerSub: {
    fontFamily: F,
    fontSize: FS.xxs,
    color: T.dim,
  },
  closeBtn: {
    background: 'none' as const,
    border: 'none' as const,
    color: T.dim,
    cursor: 'pointer' as const,
    padding: 2,
  },
  section: {
    padding: '8px 12px',
    borderBottom: `1px solid ${T.border}`,
  },
  label: {
    fontFamily: F,
    fontSize: FS.xxs,
    fontWeight: 600,
    color: T.dim,
    letterSpacing: '0.08em',
    display: 'block' as const,
    marginBottom: 4,
  },
  input: {
    fontFamily: F,
    fontSize: FS.xs,
    color: T.text,
    background: T.surface2,
    border: `1px solid ${T.border}`,
    padding: '4px 8px',
    width: '100%',
    outline: 'none' as const,
  },
  toggleRow: {
    display: 'flex' as const,
    gap: 4,
  },
  toggleBtn: {
    display: 'flex' as const,
    alignItems: 'center' as const,
    gap: 4,
    padding: '4px 10px',
    fontFamily: F,
    fontSize: FS.xxs,
    border: '1px solid',
    cursor: 'pointer' as const,
    letterSpacing: '0.04em',
  },
  addBtn: {
    display: 'flex' as const,
    alignItems: 'center' as const,
    gap: 2,
    padding: '2px 6px',
    background: `${T.cyan}15`,
    border: `1px solid ${T.cyan}40`,
    color: T.cyan,
    fontFamily: F,
    fontSize: FS.xxs,
    cursor: 'pointer' as const,
  },
  removeBtn: {
    background: 'none' as const,
    border: `1px solid ${T.border}`,
    color: T.dim,
    cursor: 'pointer' as const,
    padding: 3,
    display: 'flex' as const,
    alignItems: 'center' as const,
  },
  rangeCard: {
    padding: 8,
    background: T.surface2,
    border: `1px solid ${T.border}`,
    marginTop: 6,
  },
  submitBtn: {
    display: 'flex' as const,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
    gap: 6,
    width: '100%',
    padding: '8px 0',
    background: `${T.cyan}20`,
    border: `1px solid ${T.cyan}60`,
    color: T.cyan,
    fontFamily: F,
    fontSize: FS.sm,
    fontWeight: 700,
    letterSpacing: '0.06em',
    cursor: 'pointer' as const,
  },
} as const
