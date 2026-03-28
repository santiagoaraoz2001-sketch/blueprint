import { useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { usePipelineStore } from '@/stores/pipelineStore'

const OPERATORS = [
  { value: 'gt', label: '>', description: 'greater than' },
  { value: 'lt', label: '<', description: 'less than' },
  { value: 'gte', label: '>=', description: 'greater or equal' },
  { value: 'lte', label: '<=', description: 'less or equal' },
  { value: 'eq', label: '==', description: 'equal to' },
  { value: 'neq', label: '!=', description: 'not equal to' },
]

interface BreakpointConditionDialogProps {
  nodeId: string
  open: boolean
  onClose: () => void
}

export default function BreakpointConditionDialog({ nodeId, open, onClose }: BreakpointConditionDialogProps) {
  const existingCondition = usePipelineStore((s) => {
    const node = s.nodes.find((n) => n.id === nodeId)
    return node?.data?.breakpoint_condition as { field: string; op: string; value: number } | undefined
  })

  const [field, setField] = useState(existingCondition?.field ?? '')
  const [op, setOp] = useState(existingCondition?.op ?? 'gt')
  const [value, setValue] = useState(existingCondition?.value?.toString() ?? '')

  if (!open) return null

  const handleSave = () => {
    const numValue = parseFloat(value)
    if (!field.trim() || isNaN(numValue)) return

    usePipelineStore.getState().setBreakpointCondition(nodeId, {
      field: field.trim(),
      op,
      value: numValue,
    })
    onClose()
  }

  const handleClear = () => {
    usePipelineStore.getState().setBreakpointCondition(nodeId, null)
    onClose()
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.5)',
        zIndex: 1100,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: 340,
          background: T.surface2,
          border: `1px solid ${T.borderHi}`,
          borderRadius: 8,
          boxShadow: `0 16px 48px ${T.shadowHeavy}`,
          padding: '16px 20px',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Title */}
        <div style={{
          fontFamily: F,
          fontSize: FS.sm,
          fontWeight: 700,
          color: T.text,
          marginBottom: 12,
        }}>
          Set Breakpoint Condition
        </div>

        <div style={{
          fontFamily: F,
          fontSize: FS.xxs,
          color: T.dim,
          marginBottom: 12,
          lineHeight: 1.5,
        }}>
          Pause only when the output matches this condition.
          The field refers to an output port name or a key in the output dict.
        </div>

        {/* Field input */}
        <div style={{ marginBottom: 10 }}>
          <label style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.sec,
            fontWeight: 600,
            display: 'block',
            marginBottom: 4,
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
          }}>
            Field
          </label>
          <input
            type="text"
            value={field}
            onChange={(e) => setField(e.target.value)}
            placeholder="e.g., loss, accuracy, score"
            style={{
              width: '100%',
              padding: '6px 10px',
              fontFamily: F,
              fontSize: FS.xs,
              color: T.text,
              background: T.surface0,
              border: `1px solid ${T.border}`,
              borderRadius: 4,
              outline: 'none',
              boxSizing: 'border-box',
            }}
            onFocus={(e) => { e.currentTarget.style.borderColor = T.cyan }}
            onBlur={(e) => { e.currentTarget.style.borderColor = T.border }}
          />
        </div>

        {/* Operator select */}
        <div style={{ marginBottom: 10 }}>
          <label style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.sec,
            fontWeight: 600,
            display: 'block',
            marginBottom: 4,
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
          }}>
            Operator
          </label>
          <div style={{ display: 'flex', gap: 4 }}>
            {OPERATORS.map((o) => (
              <button
                key={o.value}
                onClick={() => setOp(o.value)}
                title={o.description}
                style={{
                  flex: 1,
                  padding: '5px 4px',
                  fontFamily: F,
                  fontSize: FS.xs,
                  fontWeight: op === o.value ? 700 : 400,
                  color: op === o.value ? T.cyan : T.sec,
                  background: op === o.value ? `${T.cyan}14` : T.surface0,
                  border: `1px solid ${op === o.value ? T.cyan + '44' : T.border}`,
                  borderRadius: 4,
                  cursor: 'pointer',
                  transition: 'all 0.1s',
                }}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>

        {/* Value input */}
        <div style={{ marginBottom: 16 }}>
          <label style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.sec,
            fontWeight: 600,
            display: 'block',
            marginBottom: 4,
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
          }}>
            Value
          </label>
          <input
            type="number"
            step="any"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="e.g., 2.0"
            style={{
              width: '100%',
              padding: '6px 10px',
              fontFamily: F,
              fontSize: FS.xs,
              color: T.text,
              background: T.surface0,
              border: `1px solid ${T.border}`,
              borderRadius: 4,
              outline: 'none',
              boxSizing: 'border-box',
            }}
            onFocus={(e) => { e.currentTarget.style.borderColor = T.cyan }}
            onBlur={(e) => { e.currentTarget.style.borderColor = T.border }}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSave() }}
          />
        </div>

        {/* Preview */}
        {field && value && (
          <div style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.dim,
            marginBottom: 12,
            padding: '6px 10px',
            background: T.surface0,
            border: `1px solid ${T.border}`,
            borderRadius: 4,
          }}>
            Pauses when <span style={{ color: T.cyan, fontWeight: 600 }}>{field}</span>
            {' '}{OPERATORS.find((o) => o.value === op)?.label}{' '}
            <span style={{ color: T.amber, fontWeight: 600 }}>{value}</span>
          </div>
        )}

        {/* Actions */}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          {existingCondition && (
            <button
              onClick={handleClear}
              style={{
                padding: '5px 12px',
                fontFamily: F,
                fontSize: FS.xxs,
                color: T.red,
                background: `${T.red}14`,
                border: `1px solid ${T.red}33`,
                borderRadius: 4,
                cursor: 'pointer',
                marginRight: 'auto',
              }}
            >
              Clear Condition
            </button>
          )}
          <button
            onClick={onClose}
            style={{
              padding: '5px 12px',
              fontFamily: F,
              fontSize: FS.xxs,
              color: T.sec,
              background: T.surface3,
              border: `1px solid ${T.border}`,
              borderRadius: 4,
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={!field.trim() || !value || isNaN(parseFloat(value))}
            style={{
              padding: '5px 14px',
              fontFamily: F,
              fontSize: FS.xxs,
              fontWeight: 600,
              color: T.cyan,
              background: `${T.cyan}14`,
              border: `1px solid ${T.cyan}33`,
              borderRadius: 4,
              cursor: 'pointer',
              opacity: !field.trim() || !value || isNaN(parseFloat(value)) ? 0.4 : 1,
            }}
          >
            Save
          </button>
        </div>
      </div>
    </div>
  )
}
