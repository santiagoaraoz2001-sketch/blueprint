import { useEffect, useState, useCallback, useRef } from 'react'
import { T, F, FD, FS } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { useProjectStore } from '@/stores/projectStore'
import { api } from '@/api/client'
import { useSettingsStore } from '@/stores/settingsStore'
import PaperBadge, { PAPER_STATUS_COLORS } from '@/components/Research/PaperBadge'
import EditableField from '@/components/Research/EditableField'
import PhaseTimeline from '@/components/Research/PhaseTimeline'
import type { Phase } from '@/components/Research/PhaseTimeline'
import ResearchNotes from '@/components/Research/ResearchNotes'
import EmptyState from '@/components/shared/EmptyState'
import { ArrowLeft, FileText } from 'lucide-react'

function isDemoMode() {
  return useSettingsStore.getState().demoMode
}

const DEMO_PHASES: Phase[] = [
  {
    phase_id: 'P1',
    name: 'Baseline Evaluation',
    status: 'complete',
    research_question: 'What is the base model performance on our target benchmarks?',
    runs: [
      { id: 'r1', name: 'baseline-llama3-8b', status: 'complete', loss: 0.52, accuracy: 0.73, elapsed: 3600 },
      { id: 'r2', name: 'baseline-llama3-8b-v2', status: 'complete', loss: 0.48, accuracy: 0.76, elapsed: 3800 },
    ],
  },
  {
    phase_id: 'P2',
    name: 'LoRA Rank Ablation',
    status: 'active',
    research_question: 'How does LoRA rank affect downstream performance?',
    runs: [
      { id: 'r3', name: 'lora-r8-alpha16', status: 'complete', loss: 0.34, accuracy: 0.84, elapsed: 7200 },
      { id: 'r4', name: 'lora-r16-alpha32', status: 'running', progress: 0.65, loss: 0.29, elapsed: 4800, eta: 2400 },
      { id: 'r5', name: 'lora-r32-alpha64', status: 'pending' },
    ],
  },
  {
    phase_id: 'P3',
    name: 'Data Mix Optimization',
    status: 'planned',
    research_question: 'Which data composition yields the best generalization?',
    runs: [],
  },
]

const STATUS_OPTIONS = Object.keys(PAPER_STATUS_COLORS).map((s) => ({ label: s.charAt(0).toUpperCase() + s.slice(1), value: s }))

export default function PaperDetailView() {
  const { selectedProjectId, setView } = useUIStore()
  const projects = useProjectStore((s) => s.projects)
  const updateProject = useProjectStore((s) => s.updateProject)
  const project = projects.find((p) => p.id === selectedProjectId)

  const [phases, setPhases] = useState<Phase[]>([])
  const [notes, setNotes] = useState('')
  const [extFields, setExtFields] = useState<Record<string, string>>({})
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!project) return
    setNotes(project.notes || '')

    if (isDemoMode()) {
      setPhases(DEMO_PHASES)
      setExtFields({
        priority: '7',
        venue: 'NeurIPS 2026',
        blocked_by: '',
        hypothesis: 'LoRA fine-tuning with rank 16+ achieves competitive performance with full fine-tuning on domain-specific tasks.',
        criteria: 'Beat baseline by >5% on MMLU, maintain perplexity < 12.',
        key_result: 'LoRA r=16 achieves 87.1% accuracy with 0.289 loss.',
      })
      return
    }

    api.get<{ phases: Phase[] }>(`/projects/${project.id}/phases`)
      .then((data) => setPhases(data.phases || []))
      .catch(() => setPhases([]))
  }, [project])

  const handleFieldSave = useCallback(
    (field: string, value: string) => {
      if (!project) return
      if (field === 'status' || field === 'name' || field === 'description') {
        updateProject(project.id, { [field]: value })
      } else {
        setExtFields((prev) => ({ ...prev, [field]: value }))
        if (!isDemoMode()) {
          api.patch(`/projects/${project.id}`, { [field]: value }).catch(() => {})
        }
      }
    },
    [project, updateProject]
  )

  const handleNotesChange = useCallback(
    (val: string) => {
      setNotes(val)
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        if (project) {
          updateProject(project.id, { notes: val })
        }
      }, 500)
    },
    [project, updateProject]
  )

  if (!project) {
    return (
      <div style={{ padding: 20 }}>
        <EmptyState
          icon={FileText}
          title="No paper selected"
          description="Select a paper from the research dashboard"
          action={{ label: 'Back to Research', onClick: () => setView('research') }}
        />
      </div>
    )
  }

  return (
    <div style={{ padding: 20, overflow: 'auto', height: '100%' }}>
      {/* Back button */}
      <button
        onClick={() => setView('research')}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '4px 8px',
          background: 'none',
          border: `1px solid ${T.border}`,
          color: T.sec,
          fontFamily: F,
          fontSize: FS.xs,
          letterSpacing: '0.06em',
          cursor: 'pointer',
          marginBottom: 16,
          transition: 'all 0.15s',
        }}
        onMouseEnter={(e) => { e.currentTarget.style.borderColor = T.borderHi; e.currentTarget.style.color = T.text }}
        onMouseLeave={(e) => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.color = T.sec }}
      >
        <ArrowLeft size={12} />
        Research
      </button>

      {/* Top: Badge + Editable fields */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
        <div style={{ flexShrink: 0 }}>
          <PaperBadge paperNumber={project.paper_number} status={project.status} size="lg" />
        </div>
        <div style={{ flex: 1, minWidth: 300, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <EditableField
            label="Status"
            value={project.status}
            onSave={(v) => handleFieldSave('status', v)}
            type="select"
            options={STATUS_OPTIONS}
          />
          <EditableField
            label="Priority (1-10)"
            value={extFields.priority || ''}
            onSave={(v) => handleFieldSave('priority', v)}
            placeholder="1-10"
          />
          <EditableField
            label="Venue"
            value={extFields.venue || ''}
            onSave={(v) => handleFieldSave('venue', v)}
            placeholder="Target venue"
          />
          <EditableField
            label="Blocked By"
            value={extFields.blocked_by || ''}
            onSave={(v) => handleFieldSave('blocked_by', v)}
            placeholder="Nothing"
          />
        </div>
        <div style={{ flex: 1, minWidth: 300, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <EditableField
            label="Hypothesis"
            value={extFields.hypothesis || ''}
            onSave={(v) => handleFieldSave('hypothesis', v)}
            type="textarea"
            placeholder="Main research hypothesis"
          />
          <EditableField
            label="Success Criteria"
            value={extFields.criteria || ''}
            onSave={(v) => handleFieldSave('criteria', v)}
            type="textarea"
            placeholder="How we know it worked"
          />
          <EditableField
            label="Key Result"
            value={extFields.key_result || ''}
            onSave={(v) => handleFieldSave('key_result', v)}
            type="textarea"
            placeholder="Summary of findings"
          />
        </div>
      </div>

      {/* Middle: Phase Timeline */}
      <div style={{ marginBottom: 24 }}>
        <h2
          style={{
            fontFamily: FD,
            fontSize: FS.lg,
            fontWeight: 600,
            color: T.text,
            margin: '0 0 12px',
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
          }}
        >
          Experiment Phases
        </h2>
        <PhaseTimeline phases={phases} projectId={project.id} />
      </div>

      {/* Bottom: Research Notes */}
      <ResearchNotes value={notes} onChange={handleNotesChange} />
    </div>
  )
}
