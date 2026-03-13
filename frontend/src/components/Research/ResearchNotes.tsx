import { useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { StickyNote, Plus, X } from 'lucide-react'

interface Note {
  id: string
  text: string
  createdAt: string
}

interface ResearchNotesProps {
  notes: Note[]
  onAdd: (text: string) => void
  onRemove: (id: string) => void
}

export default function ResearchNotes({ notes, onAdd, onRemove }: ResearchNotesProps) {
  const [draft, setDraft] = useState('')

  const handleAdd = () => {
    if (!draft.trim()) return
    onAdd(draft.trim())
    setDraft('')
  }

  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8,
      }}>
        <StickyNote size={10} color={T.amber} />
        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.sec, fontWeight: 600, letterSpacing: '0.08em' }}>
          RESEARCH NOTES
        </span>
      </div>

      {/* Notes list */}
      {notes.map((note) => (
        <div key={note.id} style={{
          padding: '6px 8px', marginBottom: 4,
          background: T.surface1, border: `1px solid ${T.border}`,
          display: 'flex', gap: 6,
        }}>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.text, flex: 1, whiteSpace: 'pre-wrap' }}>
            {note.text}
          </span>
          <button
            onClick={() => onRemove(note.id)}
            style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 0, flexShrink: 0 }}
          >
            <X size={8} />
          </button>
        </div>
      ))}

      {/* Add note */}
      <div style={{ display: 'flex', gap: 4, marginTop: 6 }}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
          placeholder="Add a note..."
          style={{
            flex: 1, padding: '4px 6px', background: T.surface3,
            border: `1px solid ${T.border}`, color: T.text,
            fontFamily: F, fontSize: FS.xxs, outline: 'none',
          }}
        />
        <button
          onClick={handleAdd}
          style={{
            padding: '4px 8px', background: `${T.cyan}14`,
            border: `1px solid ${T.cyan}33`, color: T.cyan,
            fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
          }}
        >
          <Plus size={8} />
        </button>
      </div>
    </div>
  )
}
