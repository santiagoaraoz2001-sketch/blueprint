import { useState, useRef, useEffect, useCallback } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { Pencil, Check } from 'lucide-react'

interface EditableFieldProps {
  value: string
  onSave: (value: string) => void
  type?: 'text' | 'textarea' | 'select'
  options?: { label: string; value: string }[]
  placeholder?: string
  label?: string
}

export default function EditableField({
  value,
  onSave,
  type = 'text',
  options,
  placeholder,
  label,
}: EditableFieldProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [hovered, setHovered] = useState(false)
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>(null)

  useEffect(() => {
    setDraft(value)
  }, [value])

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus()
      if (type !== 'select' && 'select' in inputRef.current) {
        (inputRef.current as HTMLInputElement).select()
      }
    }
  }, [editing, type])

  const handleSave = useCallback(() => {
    if (draft !== value) {
      setSaving(true)
      onSave(draft)
      setTimeout(() => {
        setSaving(false)
        setSaved(true)
        setTimeout(() => setSaved(false), 1000)
      }, 300)
    }
    setEditing(false)
  }, [draft, value, onSave])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && type !== 'textarea') {
        handleSave()
      }
      if (e.key === 'Escape') {
        setDraft(value)
        setEditing(false)
      }
    },
    [handleSave, type, value]
  )

  const sharedInputStyle: React.CSSProperties = {
    width: '100%',
    padding: '4px 6px',
    background: T.surface2,
    border: `1px solid ${T.cyan}55`,
    color: T.text,
    fontFamily: F,
    fontSize: FS.sm,
    outline: 'none',
    borderRadius: 2,
  }

  if (editing) {
    return (
      <div style={{ width: '100%' }}>
        {label && (
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 2, display: 'block' }}>
            {label}
          </span>
        )}
        {type === 'textarea' ? (
          <textarea
            ref={inputRef as React.RefObject<HTMLTextAreaElement>}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={handleSave}
            onKeyDown={handleKeyDown}
            rows={3}
            style={{ ...sharedInputStyle, resize: 'vertical', minHeight: 60 }}
          />
        ) : type === 'select' ? (
          <select
            ref={inputRef as React.RefObject<HTMLSelectElement>}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value)
              setTimeout(() => {
                onSave(e.target.value)
                setEditing(false)
              }, 0)
            }}
            onBlur={handleSave}
            onKeyDown={handleKeyDown}
            style={{ ...sharedInputStyle, cursor: 'pointer' }}
          >
            {options?.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        ) : (
          <input
            ref={inputRef as React.RefObject<HTMLInputElement>}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={handleSave}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            style={sharedInputStyle}
          />
        )}
      </div>
    )
  }

  return (
    <div
      style={{ width: '100%' }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {label && (
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 2, display: 'block' }}>
          {label}
        </span>
      )}
      <div
        onClick={() => setEditing(true)}
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 6,
          padding: '4px 6px',
          border: `1px solid ${hovered ? T.border : 'transparent'}`,
          borderRadius: 2,
          cursor: 'pointer',
          transition: 'border-color 0.15s',
          minHeight: 20,
        }}
      >
        <span
          style={{
            flex: 1,
            fontFamily: F,
            fontSize: FS.sm,
            color: value ? T.text : T.dim,
            whiteSpace: type === 'textarea' ? 'pre-wrap' : 'nowrap',
            overflow: type === 'textarea' ? 'visible' : 'hidden',
            textOverflow: type === 'textarea' ? 'clip' : 'ellipsis',
          }}
        >
          {saving ? 'Saving...' : saved ? '' : (type === 'select' ? (options?.find((o) => o.value === value)?.label || value) : (value || placeholder || 'Click to edit'))}
        </span>
        {saved && <Check size={10} color={T.green} />}
        {hovered && !saving && !saved && (
          <Pencil size={10} color={T.dim} style={{ flexShrink: 0, marginTop: 2 }} />
        )}
      </div>
    </div>
  )
}
