import { useState, useEffect } from 'react'
import { T, F, FS, FCODE, DEPTH } from '@/lib/design-tokens'
import { usePipelineStore } from '@/stores/pipelineStore'
import { api } from '@/api/client'
import { X, Plus, Trash2, Eye, Save, Globe, FolderOpen } from 'lucide-react'
import toast from 'react-hot-toast'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ConfigEntry {
  key: string
  value: string
}

interface ImpactDiff {
  label: string
  changes: Record<string, { before: any; after: any }>
}

type Scope = 'global' | 'project'

interface Props {
  onClose: () => void
}

// ---------------------------------------------------------------------------
// WorkspaceConfig Component — supports global and project-scoped overrides
// ---------------------------------------------------------------------------

export default function WorkspaceConfig({ onClose }: Props) {
  const [scope, setScope] = useState<Scope>('global')
  const [entries, setEntries] = useState<ConfigEntry[]>([])
  const [affectsCounts, setAffectsCounts] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [impactDiffs, setImpactDiffs] = useState<Record<string, ImpactDiff> | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')

  const pipelineId = usePipelineStore((s) => s.tabs.find(t => t.id === s.activeTabId)?.id)

  // Try to detect the project_id from the active pipeline
  const [projectId, setProjectId] = useState<string | null>(null)
  const [projectName, setProjectName] = useState<string | null>(null)

  useEffect(() => {
    if (!pipelineId) return
    api
      .get<any>(`/pipelines/${pipelineId}`)
      .then((p) => {
        setProjectId(p?.project_id || null)
        if (p?.project_id) {
          api.get<any>(`/projects/${p.project_id}`).then((proj) => {
            setProjectName(proj?.name || null)
          }).catch(() => {})
        }
      })
      .catch(() => {})
  }, [pipelineId])

  // Load config for the current scope
  useEffect(() => {
    loadConfig()
  }, [scope, projectId])

  const loadConfig = () => {
    setLoading(true)
    setImpactDiffs(null)

    if (scope === 'global') {
      api
        .get<{ config: Record<string, any>; affects_counts: Record<string, number> }>('/workspace/config')
        .then((data) => {
          populateEntries(data?.config || {})
          setAffectsCounts(data?.affects_counts || {})
          setLoading(false)
        })
        .catch(() => {
          populateEntries({})
          setLoading(false)
        })
    } else if (projectId) {
      api
        .get<{ project_config: Record<string, any> }>(`/projects/${projectId}/config`)
        .then((data) => {
          populateEntries(data?.project_config || {})
          setAffectsCounts({})
          setLoading(false)
        })
        .catch(() => {
          populateEntries({})
          setLoading(false)
        })
    } else {
      populateEntries({})
      setLoading(false)
    }
  }

  const populateEntries = (config: Record<string, any>) => {
    const list: ConfigEntry[] = Object.entries(config).map(([key, value]) => ({
      key,
      value: typeof value === 'object' ? JSON.stringify(value) : String(value),
    }))
    setEntries(list)
  }

  const buildConfigDict = () => {
    const config: Record<string, any> = {}
    for (const e of entries) {
      if (!e.key.trim()) continue
      try {
        config[e.key] = JSON.parse(e.value)
      } catch {
        config[e.key] = e.value
      }
    }
    return config
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      if (scope === 'global') {
        await api.put('/workspace/config', { config: buildConfigDict() })
        toast.success('Global config saved')
        const data = await api.get<{ config: Record<string, any>; affects_counts: Record<string, number> }>('/workspace/config')
        setAffectsCounts(data?.affects_counts || {})
      } else if (projectId) {
        await api.put(`/projects/${projectId}/config`, { config: buildConfigDict() })
        toast.success(`Project config saved`)
      }
    } catch (err: any) {
      toast.error(err?.message || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const handlePreviewImpact = async () => {
    if (!pipelineId) {
      toast.error('Open a pipeline to preview impact')
      return
    }
    setPreviewLoading(true)
    try {
      const data = await api.post<{ diffs: Record<string, ImpactDiff> }>('/workspace/config/preview-impact', {
        pipeline_id: pipelineId,
        config: buildConfigDict(),
        scope,
      })
      setImpactDiffs(data?.diffs || {})
    } catch (err: any) {
      toast.error(err?.message || 'Failed to preview')
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleAdd = () => {
    if (!newKey.trim()) return
    setEntries([...entries, { key: newKey.trim(), value: newValue }])
    setNewKey('')
    setNewValue('')
  }

  const handleRemove = (idx: number) => {
    setEntries(entries.filter((_, i) => i !== idx))
  }

  const handleUpdate = (idx: number, field: 'key' | 'value', val: string) => {
    setEntries(entries.map((e, i) => (i === idx ? { ...e, [field]: val } : e)))
  }

  const hasProject = !!projectId

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        right: 0,
        width: 480,
        height: '100vh',
        background: T.surface,
        borderLeft: `1px solid ${T.border}`,
        boxShadow: DEPTH.float,
        zIndex: 1000,
        display: 'flex',
        flexDirection: 'column',
        fontFamily: F,
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '12px 16px',
          borderBottom: `1px solid ${T.border}`,
          gap: 8,
        }}
      >
        <span style={{ flex: 1, fontSize: FS.sm, fontWeight: 600, color: T.text }}>
          Pipeline Config Overrides
        </span>
        <button
          onClick={onClose}
          style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 4 }}
        >
          <X size={14} />
        </button>
      </div>

      {/* Scope selector */}
      <div style={{ display: 'flex', borderBottom: `1px solid ${T.border}` }}>
        <ScopeTab
          active={scope === 'global'}
          icon={<Globe size={10} />}
          label="Global"
          description="All pipelines"
          onClick={() => setScope('global')}
        />
        <ScopeTab
          active={scope === 'project'}
          icon={<FolderOpen size={10} />}
          label={projectName ? `Project: ${projectName}` : 'Project'}
          description={hasProject ? 'Overrides global' : 'No project'}
          onClick={() => setScope('project')}
          disabled={!hasProject}
        />
      </div>

      {/* Precedence hint */}
      <div
        style={{
          padding: '6px 16px',
          fontSize: 9,
          color: T.dim,
          background: T.surface1,
          borderBottom: `1px solid ${T.border}`,
          lineHeight: 1.6,
        }}
      >
        Precedence: Global → Project → Pipeline definition → User overrides
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
        {scope === 'project' && !hasProject ? (
          <div style={{ color: T.dim, fontSize: FS.xs, textAlign: 'center', padding: 32 }}>
            This pipeline is not attached to a project.
            <br />
            Assign it to a project to use project-scoped overrides.
          </div>
        ) : loading ? (
          <div style={{ color: T.dim, fontSize: FS.xs, textAlign: 'center', padding: 32 }}>
            Loading...
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {/* Existing entries */}
            {entries.map((entry, idx) => (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  gap: 6,
                  alignItems: 'center',
                  padding: '6px 8px',
                  background: T.surface2,
                  borderRadius: 4,
                  border: `1px solid ${T.border}`,
                }}
              >
                <input
                  value={entry.key}
                  onChange={(e) => handleUpdate(idx, 'key', e.target.value)}
                  placeholder="key"
                  style={inputStyle}
                />
                <input
                  value={entry.value}
                  onChange={(e) => handleUpdate(idx, 'value', e.target.value)}
                  placeholder="value"
                  style={inputStyle}
                />
                {scope === 'global' && affectsCounts[entry.key] != null && (
                  <span style={{ fontSize: 9, color: T.dim, whiteSpace: 'nowrap', minWidth: 50, textAlign: 'right' }}>
                    {affectsCounts[entry.key]} blocks
                  </span>
                )}
                <button
                  onClick={() => handleRemove(idx)}
                  style={{ background: 'none', border: 'none', color: T.red, cursor: 'pointer', padding: 2 }}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))}

            {entries.length === 0 && (
              <div style={{ color: T.dim, fontSize: FS.xs, textAlign: 'center', padding: 16 }}>
                No {scope} config overrides set
              </div>
            )}

            {/* Add new entry */}
            <div
              style={{
                display: 'flex',
                gap: 6,
                alignItems: 'center',
                padding: '6px 8px',
                background: T.surface3,
                borderRadius: 4,
                border: `1px dashed ${T.border}`,
              }}
            >
              <input
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                placeholder="new key"
                onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
                style={inputStyle}
              />
              <input
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                placeholder="value"
                onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
                style={inputStyle}
              />
              <button
                onClick={handleAdd}
                disabled={!newKey.trim()}
                style={{
                  background: T.cyan,
                  border: 'none',
                  borderRadius: 3,
                  padding: '4px 6px',
                  color: T.bg,
                  cursor: newKey.trim() ? 'pointer' : 'default',
                  opacity: newKey.trim() ? 1 : 0.3,
                }}
              >
                <Plus size={12} />
              </button>
            </div>

            {/* Impact preview */}
            {impactDiffs && (
              <ImpactPreview diffs={impactDiffs} />
            )}
          </div>
        )}
      </div>

      {/* Footer actions */}
      <div
        style={{
          display: 'flex',
          gap: 8,
          padding: '12px 16px',
          borderTop: `1px solid ${T.border}`,
        }}
      >
        <button
          onClick={handlePreviewImpact}
          disabled={previewLoading || !pipelineId || (scope === 'project' && !hasProject)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '6px 12px',
            background: T.surface3,
            border: `1px solid ${T.border}`,
            borderRadius: 4,
            color: T.sec,
            fontFamily: F,
            fontSize: FS.xs,
            cursor: 'pointer',
            opacity: pipelineId && (scope === 'global' || hasProject) ? 1 : 0.4,
          }}
        >
          <Eye size={12} />
          {previewLoading ? 'Loading...' : 'Preview Impact'}
        </button>
        <div style={{ flex: 1 }} />
        <button
          onClick={handleSave}
          disabled={saving || (scope === 'project' && !hasProject)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '6px 16px',
            background: T.cyan,
            border: 'none',
            borderRadius: 4,
            color: T.bg,
            fontFamily: F,
            fontSize: FS.xs,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          <Save size={12} />
          {saving ? 'Saving...' : 'Save'}
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const inputStyle: React.CSSProperties = {
  flex: 1,
  background: T.surface0,
  border: `1px solid ${T.border}`,
  borderRadius: 3,
  padding: '4px 8px',
  fontFamily: FCODE,
  fontSize: FS.xxs,
  color: T.text,
  outline: 'none',
}

function ScopeTab({
  active,
  icon,
  label,
  description,
  onClick,
  disabled,
}: {
  active: boolean
  icon: React.ReactNode
  label: string
  description: string
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <button
      onClick={disabled ? undefined : onClick}
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 2,
        padding: '8px 12px',
        background: active ? `${T.cyan}10` : 'none',
        border: 'none',
        borderBottom: active ? `2px solid ${T.cyan}` : '2px solid transparent',
        color: disabled ? T.dim : active ? T.text : T.sec,
        fontFamily: F,
        cursor: disabled ? 'default' : 'pointer',
        opacity: disabled ? 0.4 : 1,
      }}
    >
      <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: FS.xs, fontWeight: active ? 600 : 400 }}>
        {icon}
        {label}
      </span>
      <span style={{ fontSize: 9, color: T.dim }}>{description}</span>
    </button>
  )
}

function ImpactPreview({ diffs }: { diffs: Record<string, ImpactDiff> }) {
  return (
    <div
      style={{
        marginTop: 12,
        padding: 12,
        background: T.surface2,
        borderRadius: 4,
        border: `1px solid ${T.border}`,
      }}
    >
      <div style={{ fontSize: FS.xxs, color: T.dim, marginBottom: 8, fontWeight: 600 }}>
        Impact Preview
      </div>
      {Object.keys(diffs).length === 0 ? (
        <div style={{ fontSize: FS.xs, color: T.dim }}>No changes detected</div>
      ) : (
        Object.entries(diffs).map(([nodeId, diff]) => (
          <div key={nodeId} style={{ marginBottom: 8 }}>
            <div style={{ fontSize: FS.xs, color: T.sec, fontWeight: 500, marginBottom: 4 }}>
              {diff.label}
            </div>
            {Object.entries(diff.changes).map(([key, change]) => (
              <div
                key={key}
                style={{ display: 'flex', gap: 6, fontSize: FS.xxs, padding: '2px 0' }}
              >
                <span style={{ color: T.dim, minWidth: 80 }}>{key}:</span>
                <span style={{ color: T.red, fontFamily: FCODE, textDecoration: 'line-through' }}>
                  {String(change.before ?? 'null')}
                </span>
                <span style={{ color: T.dim }}>→</span>
                <span style={{ color: T.green, fontFamily: FCODE }}>
                  {String(change.after ?? 'null')}
                </span>
              </div>
            ))}
          </div>
        ))
      )}
    </div>
  )
}

interface ImpactDiff {
  label: string
  changes: Record<string, { before: any; after: any }>
}
