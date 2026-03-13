import { useState, useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'

interface Props {
  configs: { runId: string; runName: string; config: Record<string, any> }[]
}

/** Flatten nested object: { a: { b: 1 } } → { "a.b": 1 } */
function flattenObject(obj: any, prefix = ''): Record<string, any> {
  const result: Record<string, any> = {}
  for (const key in obj) {
    const fullKey = prefix ? `${prefix}.${key}` : key
    const value = obj[key]
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      Object.assign(result, flattenObject(value, fullKey))
    } else {
      result[fullKey] = value
    }
  }
  return result
}

export default function ConfigDiff({ configs }: Props) {
  const [showAll, setShowAll] = useState(false)

  const { diffKeys, allKeys, flatConfigs } = useMemo(() => {
    const flatConfigs = configs.map(c => ({
      ...c,
      flat: flattenObject(c.config),
    }))

    // Collect all keys
    const allKeysSet = new Set<string>()
    flatConfigs.forEach(c => Object.keys(c.flat).forEach(k => allKeysSet.add(k)))
    const allKeys = Array.from(allKeysSet).sort()

    // Find keys where values differ
    const diffKeys = allKeys.filter(key => {
      const values = flatConfigs.map(c => JSON.stringify(c.flat[key] ?? '—'))
      return new Set(values).size > 1
    })

    return { diffKeys, allKeys, flatConfigs }
  }, [configs])

  const displayKeys = showAll ? allKeys : diffKeys

  if (configs.length < 2) {
    return (
      <div style={{ padding: 16, fontFamily: F, fontSize: FS.xs, color: T.dim, textAlign: 'center' }}>
        Select at least 2 runs to compare configs
      </div>
    )
  }

  return (
    <div style={{ padding: 8 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8,
      }}>
        <span style={{
          fontFamily: F, fontSize: FS.xxs, fontWeight: 700,
          color: T.dim, letterSpacing: '0.06em',
        }}>
          CONFIG DIFF
        </span>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          ({diffKeys.length} differences)
        </span>
        <div style={{ flex: 1 }} />
        <button
          onClick={() => setShowAll(!showAll)}
          style={{
            padding: '2px 8px',
            background: showAll ? `${T.cyan}15` : T.surface2,
            border: `1px solid ${showAll ? `${T.cyan}40` : T.border}`,
            color: showAll ? T.cyan : T.dim,
            fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
          }}
        >
          {showAll ? 'DIFF ONLY' : 'SHOW ALL'}
        </button>
      </div>

      {displayKeys.length === 0 ? (
        <div style={{ padding: 16, fontFamily: F, fontSize: FS.xs, color: T.dim, textAlign: 'center' }}>
          {showAll ? 'No config keys found' : 'Configs are identical'}
        </div>
      ) : (
        <div style={{ overflow: 'auto', maxHeight: 400 }}>
          <table style={{
            width: '100%', borderCollapse: 'collapse',
            fontFamily: F, fontSize: FS.xxs,
          }}>
            <thead>
              <tr>
                <th style={{
                  padding: '4px 8px', textAlign: 'left',
                  borderBottom: `1px solid ${T.borderHi}`,
                  color: T.dim, fontWeight: 700, position: 'sticky', top: 0, background: T.bg,
                  letterSpacing: '0.06em',
                }}>
                  Key
                </th>
                {flatConfigs.map(c => (
                  <th key={c.runId} style={{
                    padding: '4px 8px', textAlign: 'left',
                    borderBottom: `1px solid ${T.borderHi}`,
                    color: T.dim, fontWeight: 700, position: 'sticky', top: 0, background: T.bg,
                    letterSpacing: '0.06em',
                  }}>
                    {c.runName}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {displayKeys.map(key => {
                const values = flatConfigs.map(c => c.flat[key])
                const isDiff = diffKeys.includes(key)

                return (
                  <tr key={key} style={{ borderBottom: `1px solid ${T.border}` }}>
                    <td style={{
                      padding: '3px 8px', color: isDiff ? T.text : T.dim,
                      fontWeight: isDiff ? 700 : 400,
                    }}>
                      {key}
                    </td>
                    {values.map((val, i) => {
                      // Highlight cells that differ from the first
                      const isHighlight = isDiff && JSON.stringify(val) !== JSON.stringify(values[0])
                      return (
                        <td key={i} style={{
                          padding: '3px 8px',
                          color: T.sec,
                          background: isHighlight ? `${T.amber}08` : 'transparent',
                          fontVariantNumeric: 'tabular-nums',
                        }}>
                          {val === undefined ? <span style={{ color: T.dim }}>—</span> : String(val)}
                        </td>
                      )
                    })}
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
