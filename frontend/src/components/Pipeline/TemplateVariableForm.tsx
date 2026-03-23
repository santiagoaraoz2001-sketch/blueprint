import { useState, useCallback, useEffect } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import type { PipelineTemplate, TemplateVariable } from '@/lib/pipeline-templates'
import { ArrowLeft, Play } from 'lucide-react'
import toast from 'react-hot-toast'

interface TemplateVariableFormProps {
  template: PipelineTemplate
  onSubmit: (values: Record<string, string | number>) => void
  onBack: () => void
}

export default function TemplateVariableForm({ template, onSubmit, onBack }: TemplateVariableFormProps) {
  const [values, setValues] = useState<Record<string, string | number>>(() => {
    const initial: Record<string, string | number> = {}
    for (const v of template.variables || []) {
      initial[v.id] = v.default
    }
    return initial
  })

  const handleChange = useCallback((id: string, value: string | number) => {
    setValues((prev) => ({ ...prev, [id]: value }))
  }, [])

  const handleSubmit = useCallback(() => {
    for (const v of template.variables || []) {
      if (v.required && (values[v.id] === '' || values[v.id] === undefined)) {
        toast.error(`"${v.label}" is required`)
        return
      }
    }
    onSubmit(values)
  }, [template.variables, values, onSubmit])

  // Enter key in input fields submits the form (standard form behavior)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        const tag = (e.target as HTMLElement)?.tagName
        if (tag === 'INPUT' || tag === 'SELECT') {
          handleSubmit()
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleSubmit])

  const variables = template.variables || []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px',
        borderBottom: `1px solid ${T.border}`,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
      }}>
        <button
          onClick={onBack}
          style={{
            background: 'none', border: 'none', color: T.dim, cursor: 'pointer',
            display: 'flex', padding: 4,
          }}
        >
          <ArrowLeft size={14} />
        </button>
        <div>
          <div style={{
            fontFamily: F, fontSize: FS.md, fontWeight: 700, color: T.text,
            letterSpacing: '0.04em',
          }}>
            {template.name}
          </div>
          <div style={{
            fontFamily: F, fontSize: FS.xxs, color: T.dim,
            letterSpacing: '0.08em',
          }}>
            FILL IN VARIABLES TO CREATE PIPELINE
          </div>
        </div>
      </div>

      {/* Variable fields */}
      <div style={{ flex: 1, overflow: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {variables.map((v) => (
          <VariableField
            key={v.id}
            variable={v}
            value={values[v.id]}
            onChange={(val) => handleChange(v.id, val)}
          />
        ))}
      </div>

      {/* Footer */}
      <div style={{
        padding: '12px 16px',
        borderTop: `1px solid ${T.border}`,
        display: 'flex',
        justifyContent: 'flex-end',
        gap: 8,
      }}>
        <button
          onClick={onBack}
          style={{
            padding: '6px 16px',
            background: T.surface3,
            border: `1px solid ${T.border}`,
            color: T.dim,
            fontFamily: F, fontSize: FS.xs, fontWeight: 700,
            letterSpacing: '0.08em', cursor: 'pointer',
          }}
        >
          CANCEL
        </button>
        <button
          onClick={handleSubmit}
          style={{
            padding: '6px 16px',
            background: `${T.cyan}14`,
            border: `1px solid ${T.cyan}33`,
            color: T.cyan,
            fontFamily: F, fontSize: FS.xs, fontWeight: 700,
            letterSpacing: '0.08em', cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: 6,
          }}
        >
          <Play size={10} />
          CREATE PIPELINE
        </button>
      </div>
    </div>
  )
}

function VariableField({
  variable,
  value,
  onChange,
}: {
  variable: TemplateVariable
  value: string | number
  onChange: (val: string | number) => void
}) {
  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '8px 12px',
    background: T.surface3,
    border: `1px solid ${T.borderHi}`,
    borderRadius: 6,
    color: T.text,
    fontFamily: F,
    fontSize: FS.sm,
    outline: 'none',
    boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.1)',
  }

  return (
    <div>
      <label style={{
        fontFamily: F, fontSize: FS.xs, fontWeight: 600,
        color: T.sec, display: 'flex', alignItems: 'center', gap: 6,
        marginBottom: 4,
      }}>
        {variable.label}
        {variable.required && (
          <span style={{ color: T.red, fontSize: FS.xxs }}>*</span>
        )}
      </label>
      <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 6, lineHeight: 1.4 }}>
        {variable.description}
      </div>
      {variable.type === 'select' && variable.options ? (
        <select
          value={String(value)}
          onChange={(e) => onChange(e.target.value)}
          style={inputStyle}
        >
          {variable.options.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      ) : variable.type === 'number' ? (
        <input
          type="number"
          value={value}
          onChange={(e) => {
            const raw = e.target.value
            if (raw === '') {
              onChange(0)
            } else {
              const parsed = parseFloat(raw)
              if (!isNaN(parsed)) onChange(parsed)
            }
          }}
          step="any"
          style={inputStyle}
        />
      ) : (
        <input
          type="text"
          value={String(value)}
          onChange={(e) => onChange(e.target.value)}
          placeholder={String(variable.default) || ''}
          style={inputStyle}
        />
      )}
    </div>
  )
}
