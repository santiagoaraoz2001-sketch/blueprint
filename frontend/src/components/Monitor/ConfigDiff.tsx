import { useState, useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { Download } from 'lucide-react'

interface ConfigDiffProps {
  runIds: string[]
  configs?: Record<string, Record<string, any>>
}

/** Flatten a nested object to dot-notation keys */
function flattenObject(obj: Record<string, any>, prefix = ''): Record<string, any> {
  const result: Record<string, any> = {}
  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      Object.assign(result, flattenObject(value, fullKey))
    } else {
      result[fullKey] = value
    }
  }
  return result
}

export default function ConfigDiff({ runIds, configs }: ConfigDiffProps) {
  const [showAll, setShowAll] = useState(false)

  // Use provided configs or stub empty objects
  const flatConfigs = useMemo(() => {
    const result: Record<string, Record<string, any>> = {}
    for (const id of runIds) {
      result[id] = flattenObject(configs?.[id] || {})
    }
    return result
  }, [runIds, configs])

  // Collect all keys
  const allKeys = useMemo(() => {
    const keys = new Set<string>()
    for (const flat of Object.values(flatConfigs)) {
      for (const key of Object.keys(flat)) keys.add(key)
    }
    return Array.from(keys).sort()
  }, [flatConfigs])

  // Find differing keys
  const diffKeys = useMemo(() => {
    return allKeys.filter((key) => {
      const values = runIds.map((id) => JSON.stringify(flatConfigs[id]?.[key]))
      return new Set(values).size > 1
    })
  }, [allKeys, runIds, flatConfigs])

  const displayKeys = showAll ? allKeys : diffKeys

  const exportDiff = () => {
    const headers = ['key', ...runIds]
    const rows = [headers.join(',')]
    for (const key of displayKeys) {
      const vals = runIds.map((id) => JSON.stringify(flatConfigs[id]?.[key] ?? '') )
      rows.push([key, ...vals].join(','))
    }
    const csv = rows.join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `config_diff_${new Date().toISOString().split('T')[0]}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div style={{ marginBottom: 16, padding: 12, background: T.surface1, border: `1px solid ${T.border}` }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.sec, fontWeight: 600 }}>
          CONFIG DIFF ({diffKeys.length} differences)
        </span>
        <div style={{ display: 'flex', gap: 6 }}>
          <button
            onClick={() => setShowAll(!showAll)}
            style={{
              padding: '2px 6px', background: 'transparent',
              border: `1px solid ${T.border}`, color: T.dim,
              fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
            }}
          >
            {showAll ? 'DIFF ONLY' : 'SHOW ALL'}
          </button>
          <button
            onClick={exportDiff}
            style={{
              display: 'flex', alignItems: 'center', gap: 3,
              padding: '2px 6px', background: 'transparent',
              border: `1px solid ${T.border}`, color: T.dim,
              fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
            }}
          >
            <Download size={8} /> EXPORT
          </button>
        </div>
      </div>

      {displayKeys.length === 0 ? (
        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, textAlign: 'center', padding: 12 }}>
          {allKeys.length === 0 ? 'No config data available' : 'All configs are identical'}
        </div>
      ) : (
        <div style={{ overflow: 'auto', maxHeight: 400 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: F, fontSize: FS.xxs }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                <th style={{ padding: '4px 8px', textAlign: 'left', color: T.dim, position: 'sticky', left: 0, background: T.surface1 }}>Key</th>
                {runIds.map((id) => (
                  <th key={id} style={{ padding: '4px 8px', textAlign: 'left', color: T.dim }}>{id.substring(0, 8)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {displayKeys.map((key) => {
                const isDiff = diffKeys.includes(key)
                return (
                  <tr key={key} style={{ borderBottom: `1px solid ${T.surface4}`, background: isDiff ? `${T.amber}06` : 'transparent' }}>
                    <td style={{ padding: '3px 8px', color: isDiff ? T.amber : T.sec, position: 'sticky', left: 0, background: isDiff ? `${T.amber}06` : T.surface1 }}>
                      {key}
                    </td>
                    {runIds.map((id) => (
                      <td key={id} style={{ padding: '3px 8px', color: T.text, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {JSON.stringify(flatConfigs[id]?.[key] ?? null)}
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
