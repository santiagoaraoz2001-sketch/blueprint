import { useState } from 'react'
import { T, F, FS, FD } from '@/lib/design-tokens'
import { useDatasetStore } from '@/stores/datasetStore'
import { X } from 'lucide-react'
import toast from 'react-hot-toast'

interface Props {
  onClose: () => void
}

export default function RegisterDatasetModal({ onClose }: Props) {
  const { registerDataset } = useDatasetStore()
  const [name, setName] = useState('')
  const [source, setSource] = useState('local')
  const [sourcePath, setSourcePath] = useState('')
  const [description, setDescription] = useState('')
  const [tags, setTags] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSubmit = async () => {
    if (!name.trim()) return
    setSaving(true)
    try {
      await registerDataset({
        name: name.trim(),
        source,
        source_path: sourcePath,
        description,
        tags: tags
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
      })
      toast.success('Dataset registered')
      onClose()
    } catch {
      toast.error('Failed to register dataset')
    } finally {
      setSaving(false)
    }
  }

  const inputStyle: React.CSSProperties = {
    width: '100%',
    background: T.surface1,
    border: `1px solid ${T.border}`,
    color: T.text,
    fontFamily: F,
    fontSize: FS.md,
    padding: '6px 8px',
    outline: 'none',
  }

  const labelStyle: React.CSSProperties = {
    fontFamily: F,
    fontSize: FS.xxs,
    color: T.dim,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    marginBottom: 4,
    display: 'block',
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: T.shadowHeavy,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: 420,
          background: T.raised,
          border: `1px solid ${T.border}`,
          padding: 0,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '10px 14px',
            borderBottom: `1px solid ${T.border}`,
          }}
        >
          <span style={{ fontFamily: FD, fontSize: FS.lg, fontWeight: 600, color: T.text }}>
            Register Dataset
          </span>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: T.dim, padding: 2 }}
          >
            <X size={14} />
          </button>
        </div>

        {/* Form */}
        <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label style={labelStyle}>NAME</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My Dataset"
              style={inputStyle}
            />
          </div>
          <div>
            <label style={labelStyle}>SOURCE</label>
            <select
              value={source}
              onChange={(e) => setSource(e.target.value)}
              style={inputStyle}
            >
              <option value="local">Local File</option>
              <option value="huggingface">HuggingFace</option>
              <option value="url">URL</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>SOURCE PATH</label>
            <input
              value={sourcePath}
              onChange={(e) => setSourcePath(e.target.value)}
              placeholder={source === 'huggingface' ? 'username/dataset' : '/path/to/file.csv'}
              style={inputStyle}
            />
          </div>
          <div>
            <label style={labelStyle}>DESCRIPTION</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              style={{ ...inputStyle, resize: 'vertical' }}
            />
          </div>
          <div>
            <label style={labelStyle}>TAGS (comma-separated)</label>
            <input
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="nlp, classification"
              style={inputStyle}
            />
          </div>
        </div>

        {/* Actions */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 8,
            padding: '10px 14px',
            borderTop: `1px solid ${T.border}`,
          }}
        >
          <button
            onClick={onClose}
            style={{
              padding: '5px 14px',
              background: T.surface3,
              border: `1px solid ${T.border}`,
              color: T.sec,
              fontFamily: F,
              fontSize: FS.xs,
            }}
          >
            CANCEL
          </button>
          <button
            onClick={handleSubmit}
            disabled={!name.trim() || saving}
            style={{
              padding: '5px 14px',
              background: `${T.cyan}18`,
              border: `1px solid ${T.cyan}44`,
              color: T.cyan,
              fontFamily: F,
              fontSize: FS.xs,
              opacity: !name.trim() || saving ? 0.5 : 1,
            }}
          >
            {saving ? 'REGISTERING...' : 'REGISTER'}
          </button>
        </div>
      </div>
    </div>
  )
}
