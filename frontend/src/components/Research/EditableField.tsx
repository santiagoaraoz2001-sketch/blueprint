import { useState, useRef, useEffect } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { Pencil, Check, Loader2 } from 'lucide-react'

interface EditableFieldProps {
  value: string
  onSave: (value: string) => Promise<void> | void
  placeholder?: string
  multiline?: boolean
  fontSize?: number
  fontStyle?: 'normal' | 'italic'
  color?: string
}

export default function EditableField({
  value,
  onSave,
  placeholder = 'Click to edit...',
  multiline = false,
  fontSize = FS.sm,
  fontStyle = 'normal',
  color = T.text,
}: EditableFieldProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [hovered, setHovered] = useState(false)
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null)

  useEffect(() => {
    setDraft(value)
  }, [value])

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus()
      // Select all text
      if ('select' in inputRef.current) inputRef.current.select()
    }
  }, [editing])

  const handleSave = async () => {
    if (draft === value) {
      setEditing(false)
      return
    }
    setSaving(true)
    try {
      await onSave(draft)
      setSaving(false)
      setSaved(true)
      setEditing(false)
      // Show checkmark for 1 second
      setTimeout(() => setSaved(false), 1000)
    } catch {
      setSaving(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !multiline) {
      e.preventDefault()
      handleSave()
    }
    if (e.key === 'Escape') {
      setDraft(value)
      setEditing(false)
    }
  }

  if (editing) {
    const inputStyle: React.CSSProperties = {
      width: '100%',
      padding: '4px 6px',
      background: T.surface3,
      border: `1px solid ${T.cyan}`,
      color: T.text,
      fontFamily: F,
      fontSize,
      fontStyle,
      outline: 'none',
      resize: multiline ? 'vertical' : 'none',
    }

    return (
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
        {multiline ? (
          <textarea
            ref={inputRef as React.RefObject<HTMLTextAreaElement>}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={handleSave}
            rows={3}
            style={inputStyle}
          />
        ) : (
          <input
            ref={inputRef as React.RefObject<HTMLInputElement>}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={handleSave}
            style={inputStyle}
          />
        )}
        {saving && <Loader2 size={12} color={T.cyan} style={{ animation: 'spin 1s linear infinite', marginTop: 4 }} />}
      </div>
    )
  }

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => setEditing(true)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        cursor: 'pointer',
        padding: '2px 4px',
        border: `1px solid ${hovered ? T.borderHi : 'transparent'}`,
        transition: 'border-color 0.05s',
        minHeight: 20,
      }}
    >
      <span style={{
        fontFamily: F, fontSize, fontStyle, color: value ? color : T.dim,
        flex: 1,
      }}>
        {value || placeholder}
      </span>
      {hovered && !saved && <Pencil size={10} color={T.dim} />}
      {saved && <Check size={10} color={T.green} />}
      {saving && <Loader2 size={10} color={T.cyan} style={{ animation: 'spin 1s linear infinite' }} />}
    </div>
  )
}
