import { useState } from 'react'
import { T, F, FD, FS } from '@/lib/design-tokens'
import { usePaperStore } from '@/stores/paperStore'
import { Plus, X, BookOpen, Copy } from 'lucide-react'

const labelStyle: React.CSSProperties = {
  fontFamily: F, fontSize: FS.xxs, fontWeight: 900,
  letterSpacing: '0.12em', textTransform: 'uppercase',
  color: T.dim, display: 'block', marginBottom: 3,
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '4px 8px', background: T.surface4,
  border: `1px solid ${T.border}`, color: T.text, fontFamily: F,
  fontSize: FS.sm, outline: 'none', borderRadius: 0, boxSizing: 'border-box',
}

type FormatStyle = 'apa' | 'ieee' | 'chicago'

function formatCitation(c: { authors: string; title: string; journal: string; year: string; doi: string }, style: FormatStyle): string {
  switch (style) {
    case 'apa': return `${c.authors} (${c.year}). ${c.title}. ${c.journal}.${c.doi ? ` https://doi.org/${c.doi}` : ''}`
    case 'ieee': return `${c.authors}, "${c.title}," ${c.journal}, ${c.year}.${c.doi ? ` DOI: ${c.doi}` : ''}`
    case 'chicago': return `${c.authors}. "${c.title}." ${c.journal} (${c.year}).${c.doi ? ` https://doi.org/${c.doi}` : ''}`
  }
}

export default function CitationManager() {
  const { citations, addCitation, updateCitation, removeCitation } = usePaperStore()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [formatStyle, setFormatStyle] = useState<FormatStyle>('apa')
  const [bibtexInput, setBibtexInput] = useState('')
  const [showImport, setShowImport] = useState(false)

  const handleAdd = () => {
    addCitation({ key: `ref${citations.length + 1}`, authors: '', title: '', journal: '', year: '', doi: '', url: '' })
  }

  const handleParseBibtex = () => {
    const entries = bibtexInput.split('@').filter((e) => e.trim())
    for (const entry of entries) {
      const authorMatch = entry.match(/author\s*=\s*\{([^}]*)\}/i)
      const titleMatch = entry.match(/title\s*=\s*\{([^}]*)\}/i)
      const journalMatch = entry.match(/(?:journal|booktitle)\s*=\s*\{([^}]*)\}/i)
      const yearMatch = entry.match(/year\s*=\s*\{?(\d{4})\}?/i)
      const doiMatch = entry.match(/doi\s*=\s*\{([^}]*)\}/i)
      if (titleMatch) {
        addCitation({
          key: `ref${citations.length + 1}`, authors: authorMatch?.[1] || '',
          title: titleMatch[1], journal: journalMatch?.[1] || '',
          year: yearMatch?.[1] || '', doi: doiMatch?.[1] || '', url: '',
        })
      }
    }
    setBibtexInput('')
    setShowImport(false)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontFamily: FD, fontSize: FS.xl, fontWeight: 700, color: T.text, letterSpacing: '0.06em' }}>CITATIONS</span>
        <div style={{ display: 'flex', gap: 4 }}>
          <button onClick={() => setShowImport(!showImport)} style={{ display: 'flex', alignItems: 'center', gap: 3, background: 'transparent', border: `1px solid ${T.border}`, color: T.dim, fontFamily: F, fontSize: FS.xxs, fontWeight: 900, padding: '3px 8px', cursor: 'pointer' }}>
            <BookOpen size={8} /> BIBTEX
          </button>
          <button onClick={handleAdd} style={{ display: 'flex', alignItems: 'center', gap: 3, background: `${T.cyan}14`, border: `1px solid ${T.cyan}30`, color: T.cyan, fontFamily: F, fontSize: FS.xxs, fontWeight: 900, padding: '3px 8px', cursor: 'pointer' }}>
            <Plus size={8} /> ADD
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 4 }}>
        {(['apa', 'ieee', 'chicago'] as FormatStyle[]).map((style) => (
          <button key={style} onClick={() => setFormatStyle(style)} style={{ padding: '3px 8px', background: formatStyle === style ? `${T.cyan}20` : T.surface4, border: `1px solid ${formatStyle === style ? T.cyan + '50' : T.border}`, color: formatStyle === style ? T.cyan : T.dim, fontFamily: F, fontSize: FS.xxs, fontWeight: 900, cursor: 'pointer', textTransform: 'uppercase' }}>
            {style}
          </button>
        ))}
      </div>

      {showImport && (
        <div style={{ background: T.surface2, border: `1px solid ${T.border}`, padding: 8 }}>
          <label style={labelStyle}>PASTE BIBTEX</label>
          <textarea value={bibtexInput} onChange={(e) => setBibtexInput(e.target.value)} placeholder='@article{key, author={...}, title={...}, ...}' style={{ ...inputStyle, height: 80, resize: 'vertical', fontFamily: F }} />
          <button onClick={handleParseBibtex} style={{ marginTop: 4, padding: '4px 10px', background: `${T.cyan}14`, border: `1px solid ${T.cyan}30`, color: T.cyan, fontFamily: F, fontSize: FS.xxs, fontWeight: 900, cursor: 'pointer' }}>IMPORT</button>
        </div>
      )}

      {citations.map((citation, index) => (
        <div key={citation.id} style={{ background: editingId === citation.id ? T.surface3 : T.surface2, border: `1px solid ${editingId === citation.id ? T.cyan + '40' : T.border}` }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6, padding: '6px 8px', cursor: 'pointer' }} onClick={() => setEditingId(editingId === citation.id ? null : citation.id)}>
            <span style={{ fontFamily: F, fontSize: FS.xs, color: T.cyan, fontWeight: 900, flexShrink: 0, minWidth: 18 }}>[{index + 1}]</span>
            <span style={{ fontFamily: F, fontSize: FS.xs, color: T.sec, flex: 1, lineHeight: 1.4 }}>
              {citation.title ? formatCitation(citation, formatStyle) : <span style={{ color: T.dim, fontStyle: 'italic' }}>Click to edit...</span>}
            </span>
            <button onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(`[${index + 1}]`) }} title="Copy [n]" style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 2, display: 'flex', flexShrink: 0 }}><Copy size={8} /></button>
            <button onClick={(e) => { e.stopPropagation(); removeCitation(citation.id) }} style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 2, display: 'flex', flexShrink: 0 }}><X size={8} /></button>
          </div>

          {editingId === citation.id && (
            <div style={{ padding: 8, borderTop: `1px solid ${T.border}`, display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div><label style={labelStyle}>AUTHORS</label><input value={citation.authors} onChange={(e) => updateCitation(citation.id, { authors: e.target.value })} style={inputStyle} placeholder="Last, F.M." /></div>
              <div><label style={labelStyle}>TITLE</label><input value={citation.title} onChange={(e) => updateCitation(citation.id, { title: e.target.value })} style={inputStyle} /></div>
              <div style={{ display: 'flex', gap: 6 }}>
                <div style={{ flex: 2 }}><label style={labelStyle}>JOURNAL</label><input value={citation.journal} onChange={(e) => updateCitation(citation.id, { journal: e.target.value })} style={inputStyle} /></div>
                <div style={{ flex: 1 }}><label style={labelStyle}>YEAR</label><input value={citation.year} onChange={(e) => updateCitation(citation.id, { year: e.target.value })} style={inputStyle} /></div>
              </div>
              <div><label style={labelStyle}>DOI</label><input value={citation.doi} onChange={(e) => updateCitation(citation.id, { doi: e.target.value })} style={inputStyle} placeholder="10.xxxx/xxxx" /></div>
            </div>
          )}
        </div>
      ))}

      {citations.length === 0 && (
        <div style={{ padding: 16, textAlign: 'center', fontFamily: F, fontSize: FS.xs, color: T.dim }}>No citations yet. Click ADD or import BibTeX.</div>
      )}
    </div>
  )
}
