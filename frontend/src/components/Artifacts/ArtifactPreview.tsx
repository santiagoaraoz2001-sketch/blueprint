import { T, F, FCODE, FS } from '@/lib/design-tokens'
import { Download, Loader2 } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import type { ArtifactItem } from '@/hooks/useOutputs'
import { useArtifactPreview } from '@/hooks/useOutputs'

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(i > 1 ? 1 : 0)} ${sizes[i]}`
}

type PreviewType = 'text' | 'dataset' | 'metrics' | 'model' | 'figure'

function inferPreviewType(artifact: ArtifactItem): PreviewType {
  const aType = artifact.artifact_type
  if (aType === 'metrics' || aType === 'checkpoint') return 'metrics'
  if (aType === 'model' || aType === 'adapter') return 'model'
  if (aType === 'figure') return 'figure'
  if (aType === 'dataset' || aType === 'data') return 'dataset'
  return 'text'
}

const CHART_COLORS = [T.cyan, T.green, T.amber, T.blue, T.purple, T.pink, T.orange, T.teal]

function MetricsPreview({ metrics }: { metrics: Record<string, number> }) {
  const data = Object.entries(metrics).map(([key, value]) => ({
    name: key.length > 20 ? key.slice(0, 18) + '...' : key,
    fullName: key,
    value,
  }))

  if (data.length === 0) {
    return (
      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
        No metrics data available.
      </span>
    )
  }

  return (
    <div style={{ width: '100%', height: Math.min(200, data.length * 32 + 40) }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ left: 10, right: 10, top: 5, bottom: 5 }}>
          <XAxis
            type="number"
            tick={{ fontFamily: F, fontSize: 9, fill: T.dim }}
            axisLine={{ stroke: T.border }}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={100}
            tick={{ fontFamily: FCODE, fontSize: 9, fill: T.sec }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: T.surface3,
              border: `1px solid ${T.border}`,
              fontFamily: F,
              fontSize: 10,
              color: T.text,
            }}
            formatter={(value: unknown, _name: unknown, props: unknown) => {
              const v = value as number
              const p = props as { payload: { fullName: string } }
              return [
                typeof v === 'number' ? (v % 1 === 0 ? v : v.toFixed(4)) : v,
                p.payload.fullName,
              ]
            }}
          />
          <Bar dataKey="value" radius={[0, 3, 3, 0]}>
            {data.map((_entry, i) => (
              <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} fillOpacity={0.8} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function TextPreview({ rows }: { rows: Record<string, unknown>[] }) {
  return (
    <pre
      style={{
        fontFamily: FCODE,
        fontSize: FS.xxs,
        color: T.sec,
        background: T.surface0,
        border: `1px solid ${T.border}`,
        padding: '8px 10px',
        margin: 0,
        maxHeight: 300,
        overflow: 'auto',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        lineHeight: 1.6,
      }}
    >
      {rows.map((row, i) => (
        <div key={i} style={{ display: 'flex' }}>
          <span style={{
            color: T.muted,
            minWidth: 32,
            textAlign: 'right',
            paddingRight: 10,
            userSelect: 'none',
            opacity: 0.6,
          }}>
            {String(row.line ?? i + 1)}
          </span>
          <span>{String(row.text ?? '')}</span>
        </div>
      ))}
    </pre>
  )
}

function DatasetPreview({ rows, columns }: { rows: Record<string, unknown>[]; columns: string[] }) {
  if (!rows.length) {
    return (
      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
        No rows to preview.
      </span>
    )
  }

  return (
    <div style={{ maxHeight: 300, overflow: 'auto', border: `1px solid ${T.border}` }}>
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontFamily: FCODE,
          fontSize: FS.xxs,
        }}
      >
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col}
                style={{
                  padding: '4px 8px',
                  textAlign: 'left',
                  color: T.cyan,
                  background: T.surface2,
                  borderBottom: `1px solid ${T.border}`,
                  fontWeight: 600,
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
          {rows.map((row, i) => (
            <tr key={i} style={{ background: i % 2 === 0 ? 'transparent' : T.surface1 }}>
              {columns.map((col) => (
                <td
                  key={col}
                  style={{
                    padding: '3px 8px',
                    color: T.sec,
                    borderBottom: `1px solid ${T.border}08`,
                    maxWidth: 200,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {String(row[col] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ModelInfoPreview({ artifact }: { artifact: ArtifactItem }) {
  const ext = artifact.name.split('.').pop() || 'unknown'
  return (
    <div
      style={{
        background: T.surface1,
        border: `1px solid ${T.border}`,
        padding: '10px 14px',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}
    >
      {[
        { label: 'Format', value: ext.toUpperCase(), mono: false },
        { label: 'Size', value: formatBytes(artifact.size_bytes), mono: false },
        { label: 'Path', value: artifact.file_path, mono: true },
      ].map(({ label, value, mono }) => (
        <div key={label} style={{ display: 'flex', gap: 12, alignItems: 'baseline' }}>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, minWidth: 50, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            {label}
          </span>
          <span style={{
            fontFamily: mono ? FCODE : F,
            fontSize: FS.xs,
            color: T.text,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {value}
          </span>
        </div>
      ))}
    </div>
  )
}

/**
 * Server-side content preview for text/dataset types.
 * Uses the /api/outputs/artifacts/{id}/preview endpoint which handles
 * CSV, JSONL, JSON, Parquet, SQLite, text, Excel, and YAML.
 */
function ServerPreview({ artifact, previewType }: { artifact: ArtifactItem; previewType: PreviewType }) {
  const { data, isLoading, error } = useArtifactPreview(artifact.id, { rows: 20 })

  if (isLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: T.dim, padding: 4 }}>
        <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} />
        <span style={{ fontFamily: F, fontSize: FS.xxs }}>Loading preview...</span>
      </div>
    )
  }

  if (error || !data || data.error) {
    return (
      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
        {data?.error || 'Could not load preview.'}
      </span>
    )
  }

  if (!data.rows.length) {
    return (
      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
        Empty file.
      </span>
    )
  }

  // Text/log files come back with {line, text} rows
  const isTextFormat = data.columns.length === 2
    && data.columns.includes('line')
    && data.columns.includes('text')

  if (isTextFormat || previewType === 'text') {
    return <TextPreview rows={data.rows} />
  }

  // Metrics files (JSON) — try to render as chart if data looks like key-value
  if (previewType === 'metrics' && data.rows.length === 1) {
    const row = data.rows[0]
    const numericEntries = Object.entries(row).filter(([, v]) => typeof v === 'number')
    if (numericEntries.length > 0) {
      return <MetricsPreview metrics={Object.fromEntries(numericEntries) as Record<string, number>} />
    }
  }

  // Dataset / structured data — render as table
  return <DatasetPreview rows={data.rows} columns={data.columns} />
}

export default function ArtifactPreview({ artifact }: { artifact: ArtifactItem }) {
  const previewType = inferPreviewType(artifact)

  const handleDownload = () => {
    window.open(`/api/outputs/artifacts/${artifact.id}/download`, '_blank')
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {/* Type-specific preview */}
      {previewType === 'model' && (
        <ModelInfoPreview artifact={artifact} />
      )}

      {previewType === 'figure' && (
        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          Figure preview — download to view.
        </div>
      )}

      {(previewType === 'text' || previewType === 'dataset' || previewType === 'metrics') && (
        <ServerPreview artifact={artifact} previewType={previewType} />
      )}

      {/* Download button */}
      <button
        onClick={handleDownload}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 5,
          padding: '4px 10px',
          background: `${T.cyan}14`,
          border: `1px solid ${T.cyan}33`,
          color: T.cyan,
          fontFamily: F,
          fontSize: FS.xxs,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          cursor: 'pointer',
          transition: 'all 0.15s',
          alignSelf: 'flex-start',
        }}
        onMouseEnter={(e) => { e.currentTarget.style.background = `${T.cyan}22`; e.currentTarget.style.borderColor = `${T.cyan}55` }}
        onMouseLeave={(e) => { e.currentTarget.style.background = `${T.cyan}14`; e.currentTarget.style.borderColor = `${T.cyan}33` }}
      >
        <Download size={10} />
        Download
      </button>
    </div>
  )
}
