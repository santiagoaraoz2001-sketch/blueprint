import { T, F, FS } from '@/lib/design-tokens'
import PaperBadge from './PaperBadge'
import { FileText, Plus } from 'lucide-react'

export interface PaperSummary {
  id: string
  name: string
  paperNumber: string | null
  status: string
  phaseCount: number
  runCount: number
}

interface PaperSidebarProps {
  papers: PaperSummary[]
  selectedPaperId: string | null
  onSelect: (id: string) => void
  onCreatePaper: () => void
}

export default function PaperSidebar({ papers, selectedPaperId, onSelect, onCreatePaper }: PaperSidebarProps) {
  return (
    <div style={{
      width: 240, borderRight: `1px solid ${T.border}`,
      display: 'flex', flexDirection: 'column', height: '100%',
      background: T.surface0,
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 12px', borderBottom: `1px solid ${T.border}`,
      }}>
        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
          PAPERS
        </span>
        <button
          onClick={onCreatePaper}
          style={{
            display: 'flex', alignItems: 'center', gap: 3,
            padding: '2px 6px', background: `${T.cyan}14`, border: `1px solid ${T.cyan}33`,
            color: T.cyan, fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
          }}
        >
          <Plus size={8} /> NEW
        </button>
      </div>

      {/* Paper list */}
      <div style={{ flex: 1, overflow: 'auto', padding: '4px 0' }}>
        {papers.length === 0 && (
          <div style={{ padding: 16, fontFamily: F, fontSize: FS.xxs, color: T.dim, textAlign: 'center' }}>
            No papers yet
          </div>
        )}
        {papers.map((paper) => (
          <div
            key={paper.id}
            onClick={() => onSelect(paper.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '8px 12px', cursor: 'pointer',
              background: paper.id === selectedPaperId ? `${T.cyan}08` : 'transparent',
              borderLeft: paper.id === selectedPaperId ? `2px solid ${T.cyan}` : '2px solid transparent',
              transition: 'background 0.1s',
            }}
          >
            <FileText size={10} color={paper.id === selectedPaperId ? T.cyan : T.dim} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontFamily: F, fontSize: FS.xxs, color: paper.id === selectedPaperId ? T.text : T.sec,
                fontWeight: paper.id === selectedPaperId ? 700 : 400,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {paper.paperNumber ? `${paper.paperNumber}: ` : ''}{paper.name}
              </div>
              <div style={{ fontFamily: F, fontSize: 5, color: T.dim, marginTop: 2 }}>
                {paper.phaseCount} phases · {paper.runCount} runs
              </div>
            </div>
            <PaperBadge status={paper.status} size="sm" />
          </div>
        ))}
      </div>
    </div>
  )
}
