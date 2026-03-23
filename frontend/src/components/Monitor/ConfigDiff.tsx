import { useEffect, useState, useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { api } from '@/api/client'

interface ConfigDiffProps {
  runIds: string[]
}

function flatten(obj: any, prefix = ''): Record<string, any> {
  const result: Record<string, any> = {}
  if (!obj || typeof obj !== 'object') return result
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      Object.assign(result, flatten(value, path))
    } else {
      result[path] = value
    }
  }
  return result
}

function formatValue(val: any): string {
  if (val === null || val === undefined) return '—'
  if (Array.isArray(val)) return JSON.stringify(val)
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

export default function ConfigDiff({ runIds }: ConfigDiffProps) {
  const [configs, setConfigs] = useState<Record<string, any>>({})

  useEffect(() => {
    runIds.forEach(async (id) => {
      if (configs[id]) return
      try {
        const run = await api.get<any>(`/runs/${id}`)
        if (run) {
          setConfigs((prev) => ({
            ...prev,
            [id]: run.config_snapshot || {},
          }))
        }
      } catch {
        // Ignore
      }
    })
  }, [runIds])

  const { allKeys, flatConfigs } = useMemo(() => {
    const flatConfigs: Record<string, Record<string, any>> = {}
    const keySet = new Set<string>()
    for (const [runId, config] of Object.entries(configs)) {
      const flat = flatten(config)
      flatConfigs[runId] = flat
      Object.keys(flat).forEach((k) => keySet.add(k))
    }
    return { allKeys: [...keySet].sort(), flatConfigs }
  }, [configs])

  // Find keys where values differ
  const diffKeys = useMemo(() => {
    return allKeys.filter((key) => {
      const values = runIds.map((id) => formatValue(flatConfigs[id]?.[key]))
      return new Set(values).size > 1
    })
  }, [allKeys, runIds, flatConfigs])

  if (Object.keys(configs).length < 2) {
    return (
      <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, padding: 12 }}>
        Loading config snapshots...
      </div>
    )
  }

  if (diffKeys.length === 0) {
    return (
      <div style={{ padding: '12px 0' }}>
        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.08em', marginBottom: 8 }}>
          CONFIG DIFF
        </div>
        <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>
          All configurations are identical
        </div>
      </div>
    )
  }

  return (
    <div style={{ padding: '12px 0' }}>
      <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.08em', marginBottom: 8 }}>
        CONFIG DIFF ({diffKeys.length} differences)
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: runIds.length * 120 + 200 }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${T.borderHi}` }}>
              <th style={{ padding: '4px 8px', textAlign: 'left', fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 600, position: 'sticky', left: 0, background: T.bg }}>
                KEY
              </th>
              {runIds.map((id, i) => (
                <th key={id} style={{ padding: '4px 8px', textAlign: 'left', fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 600 }}>
                  Run {i + 1}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {diffKeys.map((key) => (
              <tr key={key} style={{ borderBottom: `1px solid ${T.border}` }}>
                <td style={{ padding: '4px 8px', fontFamily: F, fontSize: FS.xxs, color: T.sec, position: 'sticky', left: 0, background: T.bg }}>
                  {key}
                </td>
                {runIds.map((id) => {
                  const val = formatValue(flatConfigs[id]?.[key])
                  return (
                    <td
                      key={id}
                      style={{
                        padding: '4px 8px',
                        fontFamily: F,
                        fontSize: FS.xxs,
                        color: T.text,
                        maxWidth: 200,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                      title={val}
                    >
                      {val}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
