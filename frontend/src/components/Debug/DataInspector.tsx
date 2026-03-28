import { useState } from 'react'
import { T, F, FCODE, FS } from '@/lib/design-tokens'
import { useRunStore, type BreakpointState } from '@/stores/runStore'
import { X, Code, Eye } from 'lucide-react'

/**
 * DataInspector — opens automatically when a breakpoint is hit.
 *
 * Shows a tabbed interface with each completed node's output.
 * Content uses ArtifactPreview-style rendering for type-specific display
 * (text, dataset table, metrics chart) plus a Raw JSON fallback tab.
 */
export default function DataInspector() {
  const status = useRunStore((s) => s.status)
  const breakpoint = useRunStore((s) => s.breakpoint)
  const [selectedTab, setSelectedTab] = useState<string | null>(null)
  const [showRawJson, setShowRawJson] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  if (status !== 'paused' || !breakpoint || dismissed) return null

  const { completedNodes, outputsPreview } = breakpoint
  const activeTab = selectedTab ?? completedNodes[completedNodes.length - 1] ?? null
  const activeOutputs = activeTab ? outputsPreview[activeTab] ?? {} : {}

  return (
    <div
      style={{
        position: 'fixed',
        bottom: 12,
        right: 12,
        width: 420,
        maxHeight: 500,
        display: 'flex',
        flexDirection: 'column',
        background: T.surface2,
        border: `1px solid ${T.borderHi}`,
        borderRadius: 8,
        boxShadow: `0 12px 40px ${T.shadowHeavy}`,
        zIndex: 999,
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 12px',
          borderBottom: `1px solid ${T.border}`,
          background: T.surface3,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Eye size={12} color={T.cyan} />
          <span style={{
            fontFamily: F,
            fontSize: FS.sm,
            fontWeight: 700,
            color: T.text,
          }}>
            Data Inspector
          </span>
          <span style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.dim,
          }}>
            {completedNodes.length} node{completedNodes.length !== 1 ? 's' : ''}
          </span>
        </div>
        <button
          onClick={() => setDismissed(true)}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: T.dim,
            padding: 2,
          }}
        >
          <X size={14} />
        </button>
      </div>

      {/* Tabs */}
      {completedNodes.length > 0 && (
        <div
          style={{
            display: 'flex',
            overflowX: 'auto',
            borderBottom: `1px solid ${T.border}`,
            background: T.surface1,
          }}
        >
          {completedNodes.map((nodeId) => {
            const isActive = nodeId === activeTab
            return (
              <button
                key={nodeId}
                onClick={() => { setSelectedTab(nodeId); setShowRawJson(false) }}
                style={{
                  padding: '6px 12px',
                  fontFamily: F,
                  fontSize: FS.xxs,
                  fontWeight: isActive ? 700 : 400,
                  color: isActive ? T.cyan : T.sec,
                  background: isActive ? T.surface2 : 'transparent',
                  border: 'none',
                  borderBottom: isActive ? `2px solid ${T.cyan}` : '2px solid transparent',
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                  transition: 'all 0.1s',
                }}
              >
                {nodeId.length > 16 ? nodeId.slice(0, 14) + '...' : nodeId}
              </button>
            )
          })}

          {/* Raw JSON toggle */}
          {activeTab && (
            <button
              onClick={() => setShowRawJson(!showRawJson)}
              style={{
                padding: '6px 10px',
                fontFamily: F,
                fontSize: FS.xxs,
                fontWeight: showRawJson ? 700 : 400,
                color: showRawJson ? T.amber : T.dim,
                background: showRawJson ? T.surface2 : 'transparent',
                border: 'none',
                borderBottom: showRawJson ? `2px solid ${T.amber}` : '2px solid transparent',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                marginLeft: 'auto',
              }}
            >
              <Code size={10} />
              Raw JSON
            </button>
          )}
        </div>
      )}

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto', padding: '8px 12px' }}>
        {!activeTab ? (
          <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>
            No completed nodes to inspect.
          </span>
        ) : showRawJson ? (
          <RawJsonView data={activeOutputs} />
        ) : (
          <OutputPreview outputs={activeOutputs} />
        )}
      </div>
    </div>
  )
}

function RawJsonView({ data }: { data: Record<string, unknown> }) {
  let formatted: string
  try {
    formatted = JSON.stringify(data, null, 2)
  } catch {
    formatted = String(data)
  }

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
        maxHeight: 350,
        overflow: 'auto',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        lineHeight: 1.6,
      }}
    >
      {formatted}
    </pre>
  )
}

function OutputPreview({ outputs }: { outputs: Record<string, unknown> }) {
  const entries = Object.entries(outputs)

  if (entries.length === 0) {
    return (
      <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>
        No outputs recorded.
      </span>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {entries.map(([key, value]) => (
        <div key={key}>
          <div style={{
            fontFamily: F,
            fontSize: FS.xxs,
            fontWeight: 700,
            color: T.cyan,
            marginBottom: 4,
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
          }}>
            {key}
          </div>
          <OutputValue value={value} />
        </div>
      ))}
    </div>
  )
}

function OutputValue({ value }: { value: unknown }) {
  // Metrics — numeric values shown as key-value pairs
  if (typeof value === 'number') {
    return (
      <span style={{
        fontFamily: FCODE,
        fontSize: FS.sm,
        color: T.green,
        fontWeight: 600,
      }}>
        {value % 1 === 0 ? value : value.toFixed(6)}
      </span>
    )
  }

  // Text values
  if (typeof value === 'string') {
    return (
      <pre
        style={{
          fontFamily: FCODE,
          fontSize: FS.xxs,
          color: T.sec,
          background: T.surface0,
          border: `1px solid ${T.border}`,
          padding: '6px 8px',
          margin: 0,
          maxHeight: 150,
          overflow: 'auto',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          lineHeight: 1.5,
        }}
      >
        {value}
      </pre>
    )
  }

  // Dict/Object — render as mini table
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const obj = value as Record<string, unknown>
    const entries = Object.entries(obj).slice(0, 20)
    return (
      <div style={{
        maxHeight: 200,
        overflow: 'auto',
        border: `1px solid ${T.border}`,
      }}>
        <table style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontFamily: FCODE,
          fontSize: FS.xxs,
        }}>
          <tbody>
            {entries.map(([k, v]) => (
              <tr key={k} style={{ borderBottom: `1px solid ${T.border}08` }}>
                <td style={{
                  padding: '3px 8px',
                  color: T.dim,
                  fontWeight: 600,
                  whiteSpace: 'nowrap',
                  background: T.surface1,
                }}>
                  {k}
                </td>
                <td style={{
                  padding: '3px 8px',
                  color: typeof v === 'number' ? T.green : T.sec,
                  maxWidth: 200,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}>
                  {typeof v === 'number' ? (v % 1 === 0 ? v : (v as number).toFixed(4)) : String(v)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  // Arrays — show count and first few items
  if (Array.isArray(value)) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          Array [{value.length} items]
        </span>
        <pre
          style={{
            fontFamily: FCODE,
            fontSize: FS.xxs,
            color: T.sec,
            background: T.surface0,
            border: `1px solid ${T.border}`,
            padding: '6px 8px',
            margin: 0,
            maxHeight: 120,
            overflow: 'auto',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {JSON.stringify(value.slice(0, 5), null, 2)}
          {value.length > 5 ? '\n...' : ''}
        </pre>
      </div>
    )
  }

  // Fallback
  return (
    <span style={{ fontFamily: FCODE, fontSize: FS.xxs, color: T.dim }}>
      {String(value)}
    </span>
  )
}
