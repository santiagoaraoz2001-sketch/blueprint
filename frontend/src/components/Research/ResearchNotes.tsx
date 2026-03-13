import { T, F, FS } from '@/lib/design-tokens'

interface ResearchNotesProps {
  value: string
  onChange: (value: string) => void
}

export default function ResearchNotes({ value, onChange }: ResearchNotesProps) {
  return (
    <div style={{ width: '100%' }}>
      <span
        style={{
          fontFamily: F,
          fontSize: FS.xxs,
          color: T.dim,
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          marginBottom: 4,
          display: 'block',
        }}
      >
        Research Notes
      </span>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Lab notes, observations, next steps..."
        rows={8}
        style={{
          width: '100%',
          padding: '10px 12px',
          background: T.surface0,
          border: `1px solid ${T.border}`,
          color: T.text,
          fontFamily: F,
          fontSize: FS.sm,
          lineHeight: 1.6,
          outline: 'none',
          resize: 'vertical',
          minHeight: 120,
          borderRadius: 2,
        }}
        onFocus={(e) => { e.currentTarget.style.borderColor = T.borderHi }}
        onBlur={(e) => { e.currentTarget.style.borderColor = T.border }}
      />
    </div>
  )
}
