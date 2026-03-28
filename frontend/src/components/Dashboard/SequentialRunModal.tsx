import { useState, useCallback } from 'react'
import { T, F, FS, DEPTH } from '@/lib/design-tokens'
import type { DashboardExperiment } from '@/stores/dashboardStore'

interface SequentialRunModalProps {
  experiments: DashboardExperiment[]
  onStart: (pipelineIds: string[]) => void
  onClose: () => void
}

export function SequentialRunModal({ experiments, onStart, onClose }: SequentialRunModalProps) {
  const [selected, setSelected] = useState<string[]>([])

  const togglePipeline = (id: string) => {
    setSelected((prev) =>
      prev.includes(id)
        ? prev.filter((p) => p !== id)
        : prev.length < 5 ? [...prev, id] : prev
    )
  }

  const moveUp = (idx: number) => {
    if (idx <= 0) return
    setSelected((prev) => {
      const next = [...prev]
      ;[next[idx - 1], next[idx]] = [next[idx], next[idx - 1]]
      return next
    })
  }

  const moveDown = (idx: number) => {
    if (idx >= selected.length - 1) return
    setSelected((prev) => {
      const next = [...prev]
      ;[next[idx], next[idx + 1]] = [next[idx + 1], next[idx]]
      return next
    })
  }

  const pipelineNames = Object.fromEntries(
    experiments.map((e) => [e.pipeline_id, e.pipeline_name])
  )

  const handleStart = useCallback(() => {
    if (selected.length >= 2) {
      onStart(selected)
    }
  }, [selected, onStart])

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.6)',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        style={{
          background: T.raised,
          border: `1px solid ${T.border}`,
          borderRadius: 12,
          padding: 24,
          width: 440,
          maxHeight: '80vh',
          overflow: 'auto',
          boxShadow: DEPTH.modal,
        }}
      >
        <div style={{ fontFamily: F, fontSize: FS.lg, fontWeight: 700, color: T.text, marginBottom: 4 }}>
          Sequential Run
        </div>
        <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, marginBottom: 16 }}>
          Select 2-5 experiments and arrange execution order. Each pipeline waits for the previous to complete.
        </div>

        {/* Available Experiments */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: FS.xxs, fontWeight: 600, color: T.dim, marginBottom: 6, fontFamily: F, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Select Experiments
          </div>
          {experiments.map((exp) => (
            <label
              key={exp.pipeline_id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '6px 8px',
                borderRadius: 6,
                cursor: 'pointer',
                background: selected.includes(exp.pipeline_id) ? T.surface3 : 'transparent',
              }}
            >
              <input
                type="checkbox"
                checked={selected.includes(exp.pipeline_id)}
                onChange={() => togglePipeline(exp.pipeline_id)}
                disabled={!selected.includes(exp.pipeline_id) && selected.length >= 5}
              />
              <span style={{ fontFamily: F, fontSize: FS.sm, color: T.text }}>
                {exp.pipeline_name}
              </span>
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginLeft: 'auto' }}>
                {exp.runs.length} run{exp.runs.length !== 1 ? 's' : ''}
              </span>
            </label>
          ))}
        </div>

        {/* Order */}
        {selected.length >= 2 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: FS.xxs, fontWeight: 600, color: T.dim, marginBottom: 6, fontFamily: F, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Execution Order
            </div>
            {selected.map((pid, idx) => (
              <div
                key={pid}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '6px 8px',
                  borderRadius: 6,
                  background: T.surface2,
                  marginBottom: 4,
                }}
              >
                <span style={{
                  width: 20,
                  height: 20,
                  borderRadius: '50%',
                  background: T.cyan,
                  color: '#000',
                  fontSize: FS.xxs,
                  fontWeight: 700,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontFamily: F,
                }}>
                  {idx + 1}
                </span>
                <span style={{ fontFamily: F, fontSize: FS.sm, color: T.text, flex: 1 }}>
                  {pipelineNames[pid] || pid}
                </span>
                <button
                  onClick={() => moveUp(idx)}
                  disabled={idx === 0}
                  style={{ ...arrowBtn, opacity: idx === 0 ? 0.3 : 1 }}
                >
                  ↑
                </button>
                <button
                  onClick={() => moveDown(idx)}
                  disabled={idx === selected.length - 1}
                  style={{ ...arrowBtn, opacity: idx === selected.length - 1 ? 0.3 : 1 }}
                >
                  ↓
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Actions */}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            style={{
              padding: '8px 16px',
              background: T.surface3,
              color: T.sec,
              border: `1px solid ${T.border}`,
              borderRadius: 6,
              fontFamily: F,
              fontSize: FS.sm,
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleStart}
            disabled={selected.length < 2}
            style={{
              padding: '8px 16px',
              background: selected.length >= 2 ? T.cyan : T.surface4,
              color: selected.length >= 2 ? '#000' : T.dim,
              border: 'none',
              borderRadius: 6,
              fontFamily: F,
              fontSize: FS.sm,
              fontWeight: 600,
              cursor: selected.length >= 2 ? 'pointer' : 'not-allowed',
            }}
          >
            Start Sequential Run ({selected.length})
          </button>
        </div>
      </div>
    </div>
  )
}

const arrowBtn: React.CSSProperties = {
  width: 24,
  height: 24,
  background: 'transparent',
  border: `1px solid ${T.border}`,
  borderRadius: 4,
  color: T.sec,
  cursor: 'pointer',
  fontSize: 12,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
}
