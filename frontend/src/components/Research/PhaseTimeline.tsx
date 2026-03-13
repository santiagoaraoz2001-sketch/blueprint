import { useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { useMetricsStore } from '@/stores/metricsStore'
import RunRow from './RunRow'
import { PAPER_STATUS_COLORS } from './PaperBadge'
import {
  ChevronDown,
  ChevronRight,
  Play,
  GitCompare,
  Plus,
} from 'lucide-react'

export interface Phase {
  phase_id: string
  name: string
  status: string
  research_question: string
  runs: PhaseRun[]
}

export interface PhaseRun {
  id: string
  name: string
  status: string
  progress?: number
  loss?: number | null
  accuracy?: number | null
  elapsed?: number
  eta?: number | null
}

interface PhaseTimelineProps {
  phases: Phase[]
  projectId: string
}

export default function PhaseTimeline({ phases, projectId: _projectId }: PhaseTimelineProps) {
  const [expandedPhases, setExpandedPhases] = useState<Set<string>>(new Set())
  const [compareSelections, setCompareSelections] = useState<Set<string>>(new Set())
  const setView = useUIStore((s) => s.setView)
  const cloneRun = useMetricsStore((s) => s.cloneRun)

  const togglePhase = (id: string) => {
    setExpandedPhases((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleCompare = (runId: string) => {
    setCompareSelections((prev) => {
      const next = new Set(prev)
      if (next.has(runId)) next.delete(runId)
      else next.add(runId)
      return next
    })
  }

  const handleClone = async (runId: string) => {
    await cloneRun(runId)
    setView('editor')
  }

  const btnStyle: React.CSSProperties = {
    padding: '3px 8px',
    background: `${T.cyan}14`,
    border: `1px solid ${T.cyan}33`,
    color: T.cyan,
    fontFamily: F,
    fontSize: FS.xxs,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    transition: 'all 0.15s',
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
  }

  if (phases.length === 0) {
    return (
      <div style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, padding: '20px 0', textAlign: 'center' }}>
        No phases defined yet
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      {phases.map((phase, idx) => {
        const expanded = expandedPhases.has(phase.phase_id)
        const completedRuns = phase.runs.filter((r) => r.status === 'complete').length
        const color = PAPER_STATUS_COLORS[phase.status] || '#64748B'

        return (
          <div key={phase.phase_id} style={{ display: 'flex', gap: 12 }}>
            {/* Vertical timeline line */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 20, flexShrink: 0 }}>
              <div
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  background: color,
                  border: `2px solid ${T.surface1}`,
                  flexShrink: 0,
                  zIndex: 1,
                }}
              />
              {idx < phases.length - 1 && (
                <div style={{ width: 2, flex: 1, background: T.border }} />
              )}
            </div>

            {/* Phase card */}
            <div
              style={{
                flex: 1,
                marginBottom: 12,
                border: `1px solid ${T.border}`,
                background: T.surface1,
              }}
            >
              {/* Phase header */}
              <div
                onClick={() => togglePhase(phase.phase_id)}
                style={{
                  padding: '8px 12px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  transition: 'background 0.15s',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = T.surface2 }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
              >
                {expanded ? <ChevronDown size={12} color={T.dim} /> : <ChevronRight size={12} color={T.dim} />}
                <span
                  style={{
                    display: 'inline-block',
                    padding: '1px 6px',
                    background: `${color}33`,
                    fontFamily: F,
                    fontSize: FS.xxs,
                    fontWeight: 700,
                    color,
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    borderRadius: 2,
                  }}
                >
                  {phase.status}
                </span>
                <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, letterSpacing: '0.06em' }}>
                  {phase.phase_id}
                </span>
                <span style={{ fontFamily: F, fontSize: FS.sm, color: T.text, flex: 1 }}>
                  {phase.name}
                </span>
                <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                  {completedRuns}/{phase.runs.length} runs
                </span>
              </div>

              {/* Research question (always visible in collapsed) */}
              {phase.research_question && (
                <div style={{ padding: '0 12px 8px 32px' }}>
                  <span style={{ fontFamily: F, fontSize: FS.xs, color: T.sec, fontStyle: 'italic' }}>
                    {phase.research_question}
                  </span>
                </div>
              )}

              {/* Expanded content */}
              {expanded && (
                <div style={{ padding: '0 12px 10px' }}>
                  {phase.runs.map((run) => (
                    <RunRow
                      key={run.id}
                      run={run}
                      onClone={handleClone}
                      onCompareToggle={toggleCompare}
                      compareSelected={compareSelections.has(run.id)}
                    />
                  ))}

                  {/* Phase actions */}
                  <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                    <button
                      onClick={() => setView('editor')}
                      style={btnStyle}
                      onMouseEnter={(e) => { e.currentTarget.style.background = `${T.cyan}22` }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = `${T.cyan}14` }}
                    >
                      <Play size={9} />
                      Launch Next
                    </button>
                    {compareSelections.size >= 2 && (
                      <button
                        onClick={() => setView('results')}
                        style={btnStyle}
                        onMouseEnter={(e) => { e.currentTarget.style.background = `${T.cyan}22` }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = `${T.cyan}14` }}
                      >
                        <GitCompare size={9} />
                        Compare ({compareSelections.size})
                      </button>
                    )}
                    <button
                      onClick={() => setView('editor')}
                      style={btnStyle}
                      onMouseEnter={(e) => { e.currentTarget.style.background = `${T.cyan}22` }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = `${T.cyan}14` }}
                    >
                      <Plus size={9} />
                      Add Run
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
