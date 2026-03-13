import { useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import EditableField from './EditableField'
import RunRow, { type RunRowData } from './RunRow'
import PaperBadge from './PaperBadge'
import { Play, GitCompare, Plus, ChevronDown, ChevronRight } from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────

export interface PhaseData {
  id: string
  name: string
  status: 'complete' | 'active' | 'blocked' | 'planned'
  researchQuestion?: string
  finding?: string
  blockedBy?: string
  totalRuns: number
  completedRuns: number
  runningRuns: number
  plannedRuns: number
  runs: RunRowData[]
  bestRun?: { id: string; metrics: Record<string, number> }
}

interface PhaseTimelineProps {
  phases: PhaseData[]
  paperId: string
  onFindingChange?: (phaseId: string, value: string) => Promise<void>
  onLaunchNextRun?: (phaseId: string) => void
  onCompareAll?: (phaseId: string) => void
  onAddRun?: (phaseId: string) => void
  onRunClick?: (runId: string) => void
}

// ── Phase Card ────────────────────────────────────────────────────

function PhaseCard({
  phase,
  isLast,
  onFindingChange,
  onLaunchNextRun,
  onCompareAll,
  onAddRun,
  onRunClick,
}: {
  phase: PhaseData
  isLast: boolean
  onFindingChange?: (value: string) => Promise<void>
  onLaunchNextRun?: () => void
  onCompareAll?: () => void
  onAddRun?: () => void
  onRunClick?: (runId: string) => void
}) {
  // Expand run list: active phases default open, others closed
  const [expanded, setExpanded] = useState(phase.status === 'active')

  const statusColor =
    phase.status === 'complete' ? T.green :
    phase.status === 'active' ? T.cyan :
    phase.status === 'blocked' ? T.amber : T.dim

  const progressText = [
    phase.completedRuns > 0 ? `${phase.completedRuns}/${phase.totalRuns} runs complete` : null,
    phase.runningRuns > 0 ? `${phase.runningRuns} running` : null,
    phase.plannedRuns > 0 ? `${phase.plannedRuns} planned` : null,
  ].filter(Boolean).join(', ')

  return (
    <div style={{ position: 'relative' }}>
      {/* Vertical connector line */}
      {!isLast && (
        <div style={{
          position: 'absolute',
          left: 20,
          top: '100%',
          width: 2,
          height: 20,
          background: T.border,
        }} />
      )}

      {/* Phase card */}
      <div style={{
        border: `1px solid ${statusColor}33`,
        background: T.surface1,
        marginBottom: isLast ? 0 : 20,
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '8px 12px',
          borderBottom: `1px solid ${T.border}`,
        }}>
          <span style={{ fontFamily: F, fontSize: FS.xs, color: statusColor, fontWeight: 700 }}>
            {phase.id}: {phase.name}
          </span>
          <div style={{ flex: 1 }} />
          <PaperBadge status={phase.status} />
        </div>

        {/* Body */}
        <div style={{ padding: '8px 12px' }}>
          {/* Progress text */}
          {progressText && (
            <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec, marginBottom: 4 }}>
              {progressText}
            </div>
          )}

          {/* Research question */}
          {phase.researchQuestion && (
            <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec, fontStyle: 'italic', marginBottom: 6 }}>
              "{phase.researchQuestion}"
            </div>
          )}

          {/* Blocked by */}
          {phase.status === 'blocked' && phase.blockedBy && (
            <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.amber, marginBottom: 6 }}>
              Blocked by: {phase.blockedBy}
            </div>
          )}

          {/* Finding (editable for complete phases) */}
          {phase.status === 'complete' && (
            <div style={{ marginBottom: 6 }}>
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginRight: 4 }}>Finding:</span>
              <EditableField
                value={phase.finding || ''}
                onSave={(v) => onFindingChange?.(v) || Promise.resolve()}
                placeholder="Add finding..."
                fontSize={FS.xxs}
                fontStyle="italic"
                color={T.green}
              />
            </div>
          )}

          {/* Best run */}
          {phase.bestRun && (
            <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 6 }}>
              Best run: <span style={{ color: T.sec }}>{phase.bestRun.id.substring(0, 8)}</span>
              {Object.entries(phase.bestRun.metrics).map(([k, v]) => (
                <span key={k} style={{ marginLeft: 6 }}>
                  ({k}=<span style={{ color: T.cyan }}>{v.toFixed(2)}</span>)
                </span>
              ))}
            </div>
          )}

          {/* Running experiment highlight */}
          {phase.runs.filter((r) => r.status === 'running').map((run) => (
            <div key={run.id} style={{
              padding: '4px 8px', background: `${T.cyan}06`, border: `1px solid ${T.cyan}15`,
              marginBottom: 6, fontFamily: F, fontSize: FS.xxs, color: T.text,
            }}>
              Running: {run.name}
              {run.progress != null && ` (${Math.round(run.progress * 100)}%`}
              {run.eta && `, ETA ${run.eta}`}
              {run.progress != null && ')'}
            </div>
          ))}

          {/* Expandable run list */}
          {phase.runs.length > 0 && (
            <div style={{ marginTop: 4 }}>
              <button
                onClick={() => setExpanded(!expanded)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 4,
                  background: 'none', border: 'none', color: T.dim,
                  fontFamily: F, fontSize: FS.xxs, cursor: 'pointer', padding: 0,
                  marginBottom: 4,
                }}
              >
                {expanded ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
                {expanded ? 'Hide runs' : `Show ${phase.runs.length} runs`}
              </button>

              {expanded && (
                <div style={{
                  border: `1px solid ${T.border}`,
                  background: T.surface0,
                  maxHeight: 300,
                  overflow: 'auto',
                }}>
                  {phase.runs.map((run) => (
                    <RunRow
                      key={run.id}
                      run={run}
                      onClick={() => onRunClick?.(run.id)}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Actions */}
        {phase.status !== 'blocked' && (
          <div style={{
            display: 'flex', gap: 6, padding: '6px 12px',
            borderTop: `1px solid ${T.border}`,
          }}>
            {phase.status === 'active' && onLaunchNextRun && (
              <button
                onClick={onLaunchNextRun}
                style={{
                  display: 'flex', alignItems: 'center', gap: 4,
                  padding: '3px 8px', background: `${T.green}14`, border: `1px solid ${T.green}33`,
                  color: T.green, fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
                }}
              >
                <Play size={8} /> Launch Next Run
              </button>
            )}
            {phase.completedRuns >= 2 && onCompareAll && (
              <button
                onClick={onCompareAll}
                style={{
                  display: 'flex', alignItems: 'center', gap: 4,
                  padding: '3px 8px', background: `${T.purple}14`, border: `1px solid ${T.purple}33`,
                  color: T.purple, fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
                }}
              >
                <GitCompare size={8} /> Compare All
              </button>
            )}
            {onAddRun && (
              <button
                onClick={onAddRun}
                style={{
                  display: 'flex', alignItems: 'center', gap: 4,
                  padding: '3px 8px', background: 'transparent', border: `1px solid ${T.border}`,
                  color: T.dim, fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
                }}
              >
                <Plus size={8} /> Add Run
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main PhaseTimeline ────────────────────────────────────────────

export default function PhaseTimeline({
  phases,
  paperId: _paperId,
  onFindingChange,
  onLaunchNextRun,
  onCompareAll,
  onAddRun,
  onRunClick,
}: PhaseTimelineProps) {
  const setView = useUIStore((s) => s.setView)

  const handleLaunchNextRun = (phaseId: string) => {
    if (onLaunchNextRun) {
      onLaunchNextRun(phaseId)
    } else {
      // Default: navigate to pipeline editor
      setView('editor')
    }
  }

  const handleCompareAll = (phaseId: string) => {
    if (onCompareAll) {
      onCompareAll(phaseId)
    } else {
      // Default: collect completed run IDs and navigate
      const phase = phases.find((p) => p.id === phaseId)
      if (!phase) return
      const completedIds = phase.runs
        .filter((r) => r.status === 'complete')
        .map((r) => r.id)
      if (completedIds.length > 0) {
        setView('monitor' as any)
        window.history.replaceState(null, '', `?compare=true&runs=${completedIds.join(',')}`)
      }
    }
  }

  const handleRunClick = (runId: string) => {
    if (onRunClick) {
      onRunClick(runId)
    } else {
      setView('monitor' as any)
      window.history.replaceState(null, '', `?runId=${runId}`)
    }
  }

  if (phases.length === 0) {
    return (
      <div style={{ padding: 20, fontFamily: F, fontSize: FS.sm, color: T.dim, textAlign: 'center' }}>
        No phases defined for this paper. Add phases to organize your experiments.
      </div>
    )
  }

  return (
    <div>
      {phases.map((phase, i) => (
        <PhaseCard
          key={phase.id}
          phase={phase}
          isLast={i === phases.length - 1}
          onFindingChange={onFindingChange ? (v) => onFindingChange(phase.id, v) : undefined}
          onLaunchNextRun={() => handleLaunchNextRun(phase.id)}
          onCompareAll={() => handleCompareAll(phase.id)}
          onAddRun={onAddRun ? () => onAddRun(phase.id) : undefined}
          onRunClick={handleRunClick}
        />
      ))}
    </div>
  )
}
