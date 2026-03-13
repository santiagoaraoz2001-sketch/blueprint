import { useState } from 'react'
import { T, F, FD, FS } from '@/lib/design-tokens'
import { useProjectStore } from '@/stores/projectStore'
import { useUIStore } from '@/stores/uiStore'
import { X, FileJson, AlertTriangle } from 'lucide-react'
import toast from 'react-hot-toast'

interface ImportPaperModalProps {
  onClose: () => void
}

const EXAMPLE_JSON = `{
  "paper_number": "P15",
  "paper_title": "Liquid Reasoning",
  "hypothesis": "LNN layers as FFN replacements enable architectural latent CoT",
  "target_venue": "arXiv → ICML",
  "estimated_compute_hours": 40,
  "phases": [
    {"phase_id": "E0", "name": "Baselines", "total_runs": 2, "research_question": "Floor performance?"},
    {"phase_id": "E1", "name": "Placement Sweep", "total_runs": 8, "research_question": "Where should LNN layers go?", "blocked_by_phase": "E0"},
    {"phase_id": "E2", "name": "Density Sweep", "total_runs": 6, "blocked_by_phase": "E1"}
  ]
}`

interface ImportPhase {
  phase_id: string
  name: string
  total_runs: number
  description?: string
  research_question?: string
  blocked_by_phase?: string
}

interface ImportData {
  paper_number?: string
  paper_title?: string
  hypothesis?: string
  target_venue?: string
  estimated_compute_hours?: number
  phases: ImportPhase[]
}

export default function ImportPaperModal({ onClose }: ImportPaperModalProps) {
  const createProject = useProjectStore((s) => s.createProject)
  const quickSetup = useProjectStore((s) => s.quickSetup)
  const { setSelectedProject, setView } = useUIStore()
  const [jsonText, setJsonText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const validate = (text: string): ImportData | null => {
    if (!text.trim()) {
      setError('Paste JSON to import')
      return null
    }
    try {
      const data = JSON.parse(text)
      if (!data.phases || !Array.isArray(data.phases) || data.phases.length === 0) {
        setError('JSON must contain a non-empty "phases" array')
        return null
      }
      for (const p of data.phases) {
        if (!p.phase_id || !p.name) {
          setError(`Each phase needs "phase_id" and "name". Found: ${JSON.stringify(p)}`)
          return null
        }
      }
      setError(null)
      return data as ImportData
    } catch (e: any) {
      setError(`Invalid JSON: ${e.message}`)
      return null
    }
  }

  const handleSubmit = async () => {
    const data = validate(jsonText)
    if (!data) return

    setLoading(true)
    try {
      const project = await createProject({
        name: data.paper_title || `Paper ${data.paper_number || 'Import'}`,
        paper_number: data.paper_number || null,
        paper_title: data.paper_title || null,
        description: data.hypothesis || '',
        target_venue: data.target_venue || null,
        hypothesis: data.hypothesis || null,
        estimated_compute_hours: data.estimated_compute_hours || 0,
        status: 'planned',
      })

      if (data.phases.length > 0) {
        await quickSetup(
          project.id,
          data.phases.map((p) => ({
            phase_id: p.phase_id,
            name: p.name,
            total_runs: p.total_runs || 0,
            description: p.description,
            research_question: p.research_question,
          }))
        )
      }

      toast.success(`Imported "${project.name}" with ${data.phases.length} phases`)
      setSelectedProject(project.id)
      setView('research-detail')
      onClose()
    } catch (e: any) {
      setError(e?.message || 'Import failed — is the backend running?')
    } finally {
      setLoading(false)
    }
  }

  const parsed = jsonText.trim() ? validate(jsonText) : null
  const phaseCount = parsed?.phases?.length || 0

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: T.shadowHeavy,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        style={{
          width: 520,
          maxHeight: '80vh',
          display: 'flex',
          flexDirection: 'column',
          background: T.surface2,
          border: `1px solid ${T.borderHi}`,
          borderTop: `2px solid ${T.cyan}`,
        }}
        className="animate-fadeSlideUp"
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '10px 14px',
            borderBottom: `1px solid ${T.border}`,
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <FileJson size={16} color={T.cyan} />
            <span
              style={{
                fontFamily: FD,
                fontSize: FS.xl,
                fontWeight: 700,
                color: T.text,
                letterSpacing: '0.04em',
              }}
            >
              IMPORT PAPER
            </span>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: T.dim, display: 'flex', cursor: 'pointer' }}
          >
            <X size={14} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10, flex: 1, overflow: 'auto' }}>
          <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, lineHeight: 1.5 }}>
            Paste a JSON object with paper metadata and experiment phases.
          </div>

          <textarea
            style={{
              width: '100%',
              minHeight: 220,
              padding: '10px 12px',
              background: T.surface4,
              border: `1px solid ${error ? '#EF444480' : T.border}`,
              color: T.text,
              fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace',
              fontSize: FS.sm,
              outline: 'none',
              resize: 'vertical',
              lineHeight: 1.5,
              tabSize: 2,
            }}
            value={jsonText}
            onChange={(e) => { setJsonText(e.target.value); setError(null) }}
            placeholder={EXAMPLE_JSON}
            autoFocus
            spellCheck={false}
          />

          {error && (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6, padding: '6px 8px', background: '#EF444412', border: '1px solid #EF444430' }}>
              <AlertTriangle size={12} color="#EF4444" style={{ flexShrink: 0, marginTop: 2 }} />
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: '#EF4444', lineHeight: 1.4 }}>{error}</span>
            </div>
          )}

          {parsed && !error && (
            <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.cyan, padding: '4px 0' }}>
              Ready: {parsed.paper_title || parsed.paper_number || 'Untitled'} — {phaseCount} phase{phaseCount !== 1 ? 's' : ''}
              {parsed.phases.reduce((s, p) => s + (p.total_runs || 0), 0) > 0 &&
                `, ${parsed.phases.reduce((s, p) => s + (p.total_runs || 0), 0)} total runs`}
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 8,
            padding: '10px 14px',
            borderTop: `1px solid ${T.border}`,
            flexShrink: 0,
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
              fontSize: FS.md,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!parsed || loading}
            style={{
              padding: '5px 14px',
              background: `${T.cyan}14`,
              border: `1px solid ${T.cyan}33`,
              color: T.cyan,
              fontFamily: F,
              fontSize: FS.md,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              cursor: !parsed || loading ? 'default' : 'pointer',
              opacity: !parsed || loading ? 0.5 : 1,
            }}
          >
            {loading ? 'Importing...' : 'Import Paper'}
          </button>
        </div>
      </div>
    </div>
  )
}
