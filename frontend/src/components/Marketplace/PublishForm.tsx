import { useState } from 'react'
import { T, F, FS, FD } from '@/lib/design-tokens'
import { Upload, X, Plus } from 'lucide-react'

interface PublishFormProps {
  onPublish: (data: {
    type: string
    path: string
    name: string
    description: string
    tags: string[]
    license: string
    author: string
  }) => void | Promise<void>
  onCancel: () => void
}

export default function PublishForm({ onPublish, onCancel }: PublishFormProps) {
  const [type, setType] = useState('block')
  const [path, setPath] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [tagInput, setTagInput] = useState('')
  const [tags, setTags] = useState<string[]>([])
  const [license, setLicense] = useState('MIT')
  const [author, setAuthor] = useState('Local User')
  const [submitting, setSubmitting] = useState(false)

  const inputStyle = useInputStyle()

  const addTag = () => {
    const tag = tagInput.trim().toLowerCase()
    if (tag && !tags.includes(tag)) {
      setTags([...tags, tag])
      setTagInput('')
    }
  }

  const removeTag = (tag: string) => {
    setTags(tags.filter(t => t !== tag))
  }

  const handleSubmit = async () => {
    if (!name.trim() || !path.trim() || submitting) return
    setSubmitting(true)
    try {
      await onPublish({ type, path: path.trim(), name: name.trim(), description: description.trim(), tags, license, author })
    } finally {
      setSubmitting(false)
    }
  }

  const canSubmit = name.trim() && path.trim() && !submitting

  return (
    <div style={{
      background: T.surface1, border: `1px solid ${T.border}`, borderRadius: 8,
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px', borderBottom: `1px solid ${T.border}`,
        background: T.surface2, display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <Upload size={12} color={T.cyan} />
        <span style={{
          fontFamily: F, fontSize: FS.xs, color: T.dim, fontWeight: 700,
          letterSpacing: '0.1em', textTransform: 'uppercase',
        }}>
          PUBLISH TO MARKETPLACE
        </span>
        <div style={{ flex: 1 }} />
        <button
          onClick={onCancel}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.dim, padding: 2 }}
        >
          <X size={12} />
        </button>
      </div>

      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
        {/* Type selector */}
        <FormField label="Type">
          <div style={{ display: 'flex', gap: 6 }}>
            {(['block', 'template', 'plugin'] as const).map(t => (
              <button
                key={t}
                onClick={() => setType(t)}
                style={{
                  flex: 1, padding: '6px 12px', borderRadius: 4,
                  background: type === t ? `${T.cyan}15` : T.surface3,
                  border: `1px solid ${type === t ? T.cyan + '40' : T.border}`,
                  color: type === t ? T.cyan : T.dim,
                  fontFamily: F, fontSize: FS.xs, fontWeight: 700,
                  letterSpacing: '0.06em', textTransform: 'uppercase',
                  cursor: 'pointer', transition: 'all 0.15s',
                }}
              >
                {t}
              </button>
            ))}
          </div>
        </FormField>

        {/* Path */}
        <FormField label="Path" hint="Path to the local item directory">
          <input
            value={path}
            onChange={e => setPath(e.target.value)}
            placeholder={`e.g., blocks/data/my_${type}`}
            style={inputStyle}
          />
        </FormField>

        {/* Name */}
        <FormField label="Name">
          <input
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="My Custom Block"
            style={inputStyle}
          />
        </FormField>

        {/* Description */}
        <FormField label="Description">
          <textarea
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="What does this item do?"
            rows={3}
            style={{ ...inputStyle, resize: 'vertical' }}
          />
        </FormField>

        {/* Tags */}
        <FormField label="Tags">
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <input
              value={tagInput}
              onChange={e => setTagInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addTag() } }}
              placeholder="Add tag..."
              style={{ ...inputStyle, flex: 1 }}
            />
            <button onClick={addTag} style={{
              background: T.surface3, border: `1px solid ${T.border}`,
              borderRadius: 4, padding: '6px 8px', cursor: 'pointer', color: T.dim,
            }}>
              <Plus size={12} />
            </button>
          </div>
          {tags.length > 0 && (
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 6 }}>
              {tags.map(tag => (
                <span key={tag} style={{
                  display: 'flex', alignItems: 'center', gap: 4,
                  padding: '2px 8px', background: T.surface3, borderRadius: 10,
                  fontSize: FS.xxs, fontFamily: F, color: T.sec, border: `1px solid ${T.border}`,
                }}>
                  {tag}
                  <button onClick={() => removeTag(tag)} style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: T.dim, padding: 0, display: 'flex',
                  }}>
                    <X size={8} />
                  </button>
                </span>
              ))}
            </div>
          )}
        </FormField>

        {/* License & Author row */}
        <div style={{ display: 'flex', gap: 12 }}>
          <FormField label="License" style={{ flex: 1 }}>
            <select
              value={license}
              onChange={e => setLicense(e.target.value)}
              style={{
                ...inputStyle, cursor: 'pointer',
                WebkitAppearance: 'none', MozAppearance: 'none', appearance: 'none',
              }}
            >
              <option value="MIT">MIT</option>
              <option value="Apache-2.0">Apache 2.0</option>
              <option value="GPL-3.0">GPL 3.0</option>
              <option value="BSD-3-Clause">BSD 3-Clause</option>
              <option value="Proprietary">Proprietary</option>
            </select>
          </FormField>
          <FormField label="Author" style={{ flex: 1 }}>
            <input
              value={author}
              onChange={e => setAuthor(e.target.value)}
              placeholder="Your Name"
              style={inputStyle}
            />
          </FormField>
        </div>

        {/* Submit button */}
        <button
          onClick={handleSubmit}
          disabled={!canSubmit}
          style={{
            width: '100%', padding: '10px 20px',
            background: canSubmit ? T.cyan : T.surface3,
            border: 'none', borderRadius: 6,
            color: canSubmit ? '#000' : T.dim,
            fontFamily: FD, fontSize: FS.md, fontWeight: 700,
            cursor: canSubmit ? 'pointer' : 'default',
            letterSpacing: '0.08em', textTransform: 'uppercase',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            transition: 'all 0.15s',
          }}
        >
          <Upload size={14} /> {submitting ? 'PUBLISHING...' : 'PUBLISH TO MARKETPLACE'}
        </button>
      </div>
    </div>
  )
}

function useInputStyle(): React.CSSProperties {
  return {
    width: '100%', padding: '7px 10px',
    background: T.surface0, border: `1px solid ${T.border}`,
    borderRadius: 4, color: T.text, fontFamily: F, fontSize: FS.sm,
    outline: 'none', boxSizing: 'border-box',
  }
}

function FormField({ label, hint, children, style }: {
  label: string; hint?: string; children: React.ReactNode; style?: React.CSSProperties
}) {
  return (
    <div style={style}>
      <label style={{
        fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 700,
        letterSpacing: '0.06em', textTransform: 'uppercase', display: 'block',
        marginBottom: 4,
      }}>
        {label}
        {hint && (
          <span style={{ fontWeight: 400, textTransform: 'none', marginLeft: 6, color: T.dim }}>
            ({hint})
          </span>
        )}
      </label>
      {children}
    </div>
  )
}
