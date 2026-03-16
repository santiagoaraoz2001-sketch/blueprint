import { useState, useCallback } from 'react'
import { T, F, FS, CONNECTOR_COLORS, CATEGORY_COLORS } from '@/lib/design-tokens'
import { type ConfigField, type ConnectorType } from '@/lib/block-registry'
import { loadCustomBlocks } from '@/components/Pipeline/CustomModuleEditor'
import type { CustomBlock } from '@/components/Pipeline/CustomModuleEditor'
import { Plus, Trash2, Save, Code, ChevronDown, ChevronRight, FlaskConical, CheckCircle2, XCircle, AlertTriangle, Loader2 } from 'lucide-react'
import * as Icons from 'lucide-react'
import toast from 'react-hot-toast'
import { api } from '@/api/client'

const STORAGE_KEY = 'blueprint-custom-blocks'

const CATEGORY_OPTIONS = ['external', 'data', 'model', 'inference', 'training', 'metrics', 'embedding', 'utilities', 'agents', 'interventions', 'endpoints']
const PORT_TYPE_OPTIONS: ConnectorType[] = ['dataset', 'text', 'model', 'config', 'metrics', 'embedding', 'artifact', 'agent', 'llm', 'any']

interface PortDef {
  id: string
  label: string
  dataType: ConnectorType
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '6px 10px',
  background: T.surface3,
  border: `1px solid ${T.border}`,
  borderRadius: 4,
  color: T.text,
  fontFamily: F,
  fontSize: FS.sm,
  outline: 'none',
  boxSizing: 'border-box',
}

const labelStyle: React.CSSProperties = {
  fontFamily: F,
  fontSize: FS.xxs,
  color: T.dim,
  fontWeight: 700,
  letterSpacing: '0.1em',
  display: 'block',
  marginBottom: 4,
  textTransform: 'uppercase',
}

export default function WorkshopView() {
  const [customBlocks, setCustomBlocks] = useState<CustomBlock[]>(() => loadCustomBlocks())
  const [selectedBlockType, setSelectedBlockType] = useState<string | null>(null)
  const [showList, setShowList] = useState(true)

  // Form state
  const [name, setName] = useState('My Custom Block')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('external')
  const [icon, setIcon] = useState('Box')
  const [inputs, setInputs] = useState<PortDef[]>([{ id: 'input', label: 'Input', dataType: 'dataset' }])
  const [outputs, setOutputs] = useState<PortDef[]>([{ id: 'output', label: 'Output', dataType: 'dataset' }])
  const [configFields, setConfigFields] = useState<ConfigField[]>([])
  const [code, setCode] = useState(`import json
import sys

def run(inputs: dict, config: dict) -> dict:
    """
    Block entry point.

    Args:
        inputs: dict of input port data (keys = port ids)
        config: dict of configuration values

    Returns:
        dict of output port data (keys = port ids)
    """
    # Your logic here
    return {"output": inputs.get("input", {})}
`)

  // Test/validation state
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ valid: boolean; errors: string[]; warnings: string[] } | null>(null)

  const handleTest = useCallback(async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const result = await api.post<{ valid: boolean; errors: string[]; warnings: string[] }>(
        '/custom-blocks/validate-code',
        { code, name },
      )
      setTestResult(result)
      if (result.valid) {
        toast.success(result.warnings.length > 0 ? 'Code valid (with warnings)' : 'Code is valid ✓')
      } else {
        toast.error(`${result.errors.length} error${result.errors.length !== 1 ? 's' : ''} found`)
      }
    } catch {
      toast.error('Validation request failed')
    } finally {
      setTesting(false)
    }
  }, [code, name])

  const refreshBlocks = useCallback(() => {
    setCustomBlocks(loadCustomBlocks())
  }, [])

  const loadBlock = useCallback((block: CustomBlock) => {
    setSelectedBlockType(block.type)
    setName(block.name)
    setDescription(block.description)
    setCategory(block.category)
    setIcon(block.icon)
    setInputs(block.inputs.map(p => ({ id: p.id, label: p.label, dataType: p.dataType as ConnectorType })))
    setOutputs(block.outputs.map(p => ({ id: p.id, label: p.label, dataType: p.dataType as ConnectorType })))
    setConfigFields([...block.configFields])
  }, [])

  const handleNew = () => {
    setSelectedBlockType(null)
    setName('My Custom Block')
    setDescription('')
    setCategory('external')
    setIcon('Box')
    setInputs([{ id: 'input', label: 'Input', dataType: 'dataset' }])
    setOutputs([{ id: 'output', label: 'Output', dataType: 'dataset' }])
    setConfigFields([])
    setCode(`import json\nimport sys\n\ndef run(inputs: dict, config: dict) -> dict:\n    return {"output": inputs.get("input", {})}`)
  }

  const handleSave = () => {
    const typeId = selectedBlockType || `custom_${name.toLowerCase().replace(/[^a-z0-9]/g, '_')}_${Date.now()}`
    const block: CustomBlock = {
      type: typeId,
      name,
      description,
      category,
      tags: [category, 'custom'],
      aliases: [name.toLowerCase()],
      icon,
      accent: CATEGORY_COLORS[category] || '#94A3B8',
      inputs: inputs.map(p => ({ id: p.id, label: p.label, dataType: p.dataType, required: true })),
      outputs: outputs.map(p => ({ id: p.id, label: p.label, dataType: p.dataType, required: true })),
      defaultConfig: {},
      configFields: [...configFields],
      isCustom: true,
      maturity: 'stable',
      baseType: '',
    }

    const existing = loadCustomBlocks()
    const idx = existing.findIndex(b => b.type === typeId)
    if (idx >= 0) {
      existing[idx] = block
    } else {
      existing.push(block)
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(existing))
    refreshBlocks()
    setSelectedBlockType(typeId)
    toast.success('Block saved')
  }

  const handleDelete = () => {
    if (!selectedBlockType) return
    const existing = loadCustomBlocks().filter(b => b.type !== selectedBlockType)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(existing))
    refreshBlocks()
    handleNew()
    toast.success('Block deleted')
  }

  const addPort = (list: PortDef[], setter: (v: PortDef[]) => void) => {
    const id = `port_${list.length + 1}`
    setter([...list, { id, label: `Port ${list.length + 1}`, dataType: 'dataset' }])
  }

  const removePort = (list: PortDef[], setter: (v: PortDef[]) => void, idx: number) => {
    setter(list.filter((_, i) => i !== idx))
  }

  const updatePort = (list: PortDef[], setter: (v: PortDef[]) => void, idx: number, updates: Partial<PortDef>) => {
    setter(list.map((p, i) => i === idx ? { ...p, ...updates } : p))
  }

  const IconComponent = (Icons as any)[icon] || Icons.Box

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{
        height: 34,
        display: 'flex',
        alignItems: 'center',
        padding: '0 14px',
        gap: 10,
        borderBottom: `1px solid ${T.border}`,
        background: T.surface1,
        flexShrink: 0,
      }}>
        <Code size={12} color={T.cyan} />
        <span style={{ fontFamily: F, fontSize: FS.lg, fontWeight: 700, color: T.text, letterSpacing: '0.06em' }}>
          BLOCK WORKSHOP
        </span>
        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>
          Create and edit custom blocks
        </span>
      </div>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Left sidebar: block list */}
        <div style={{
          width: 220,
          minWidth: 220,
          borderRight: `1px solid ${T.border}`,
          display: 'flex',
          flexDirection: 'column',
          background: T.surface0,
        }}>
          <div style={{
            padding: '10px 12px',
            borderBottom: `1px solid ${T.border}`,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}>
            <button onClick={() => setShowList(!showList)} style={{
              background: 'none', border: 'none', cursor: 'pointer', color: T.dim, padding: 0,
            }}>
              {showList ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
            </button>
            <span style={{ ...labelStyle, margin: 0, flex: 1 }}>CUSTOM BLOCKS</span>
            <button onClick={handleNew} style={{
              background: `${T.cyan}15`, border: `1px solid ${T.cyan}30`, borderRadius: 4,
              color: T.cyan, fontFamily: F, fontSize: FS.xxs, padding: '2px 8px', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 3,
            }}>
              <Plus size={8} /> NEW
            </button>
          </div>

          {showList && (
            <div style={{ flex: 1, overflow: 'auto', padding: '4px 0' }}>
              {customBlocks.length === 0 && (
                <div style={{ padding: '16px 14px', fontFamily: F, fontSize: FS.xxs, color: T.dim, textAlign: 'center' }}>
                  No custom blocks yet.
                </div>
              )}
              {customBlocks.map(block => (
                <div
                  key={block.type}
                  onClick={() => loadBlock(block)}
                  style={{
                    padding: '8px 14px',
                    cursor: 'pointer',
                    background: selectedBlockType === block.type ? `${T.cyan}10` : 'transparent',
                    borderLeft: selectedBlockType === block.type ? `2px solid ${T.cyan}` : '2px solid transparent',
                    transition: 'all 0.1s',
                  }}
                  onMouseEnter={e => { if (selectedBlockType !== block.type) e.currentTarget.style.background = T.surface2 }}
                  onMouseLeave={e => { if (selectedBlockType !== block.type) e.currentTarget.style.background = 'transparent' }}
                >
                  <div style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 600 }}>{block.name}</div>
                  <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 2 }}>{block.category}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Main area: form + preview */}
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          {/* Definition form */}
          <div style={{
            width: 340,
            minWidth: 340,
            borderRight: `1px solid ${T.border}`,
            overflow: 'auto',
            padding: 16,
            display: 'flex',
            flexDirection: 'column',
            gap: 14,
          }}>
            {/* Name */}
            <div>
              <label style={labelStyle}>NAME</label>
              <input value={name} onChange={e => setName(e.target.value)} style={inputStyle} />
            </div>

            {/* Description */}
            <div>
              <label style={labelStyle}>DESCRIPTION</label>
              <textarea value={description} onChange={e => setDescription(e.target.value)} rows={2}
                style={{ ...inputStyle, resize: 'vertical' }} />
            </div>

            {/* Category + Icon row */}
            <div style={{ display: 'flex', gap: 10 }}>
              <div style={{ flex: 1 }}>
                <label style={labelStyle}>CATEGORY</label>
                <select value={category} onChange={e => setCategory(e.target.value)}
                  style={{ ...inputStyle, cursor: 'pointer' }}>
                  {CATEGORY_OPTIONS.map(c => (
                    <option key={c} value={c}>{c.toUpperCase()}</option>
                  ))}
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <label style={labelStyle}>ICON</label>
                <input value={icon} onChange={e => setIcon(e.target.value)}
                  placeholder="Lucide icon name"
                  style={inputStyle} />
              </div>
            </div>

            {/* Inputs */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <span style={labelStyle}>INPUTS</span>
                <button onClick={() => addPort(inputs, setInputs)} style={{
                  background: `${T.cyan}15`, border: `1px solid ${T.cyan}30`, borderRadius: 4,
                  color: T.cyan, fontFamily: F, fontSize: FS.xxs, padding: '2px 6px', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 3,
                }}>
                  <Plus size={8} /> ADD
                </button>
              </div>
              {inputs.map((port, idx) => (
                <div key={idx} style={{ display: 'flex', gap: 4, alignItems: 'center', marginBottom: 4 }}>
                  <input value={port.id} onChange={e => updatePort(inputs, setInputs, idx, { id: e.target.value })}
                    placeholder="id" style={{ ...inputStyle, width: 70 }} />
                  <input value={port.label} onChange={e => updatePort(inputs, setInputs, idx, { label: e.target.value })}
                    placeholder="label" style={{ ...inputStyle, flex: 1 }} />
                  <select value={port.dataType} onChange={e => updatePort(inputs, setInputs, idx, { dataType: e.target.value as ConnectorType })}
                    style={{ ...inputStyle, width: 80, cursor: 'pointer' }}>
                    {PORT_TYPE_OPTIONS.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                  <button onClick={() => removePort(inputs, setInputs, idx)} style={{
                    background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 2,
                  }}>
                    <Trash2 size={10} />
                  </button>
                </div>
              ))}
            </div>

            {/* Outputs */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <span style={labelStyle}>OUTPUTS</span>
                <button onClick={() => addPort(outputs, setOutputs)} style={{
                  background: `${T.cyan}15`, border: `1px solid ${T.cyan}30`, borderRadius: 4,
                  color: T.cyan, fontFamily: F, fontSize: FS.xxs, padding: '2px 6px', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 3,
                }}>
                  <Plus size={8} /> ADD
                </button>
              </div>
              {outputs.map((port, idx) => (
                <div key={idx} style={{ display: 'flex', gap: 4, alignItems: 'center', marginBottom: 4 }}>
                  <input value={port.id} onChange={e => updatePort(outputs, setOutputs, idx, { id: e.target.value })}
                    placeholder="id" style={{ ...inputStyle, width: 70 }} />
                  <input value={port.label} onChange={e => updatePort(outputs, setOutputs, idx, { label: e.target.value })}
                    placeholder="label" style={{ ...inputStyle, flex: 1 }} />
                  <select value={port.dataType} onChange={e => updatePort(outputs, setOutputs, idx, { dataType: e.target.value as ConnectorType })}
                    style={{ ...inputStyle, width: 80, cursor: 'pointer' }}>
                    {PORT_TYPE_OPTIONS.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                  <button onClick={() => removePort(outputs, setOutputs, idx)} style={{
                    background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 2,
                  }}>
                    <Trash2 size={10} />
                  </button>
                </div>
              ))}
            </div>

            {/* Config Fields */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <span style={labelStyle}>CONFIG FIELDS</span>
                <button onClick={() => setConfigFields([...configFields, { name: `field_${configFields.length + 1}`, label: 'New Field', type: 'string' }])} style={{
                  background: `${T.cyan}15`, border: `1px solid ${T.cyan}30`, borderRadius: 4,
                  color: T.cyan, fontFamily: F, fontSize: FS.xxs, padding: '2px 6px', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 3,
                }}>
                  <Plus size={8} /> ADD
                </button>
              </div>
              {configFields.map((field, idx) => (
                <div key={idx} style={{ display: 'flex', gap: 4, alignItems: 'center', marginBottom: 4 }}>
                  <input value={field.label} onChange={e => setConfigFields(prev => prev.map((f, i) => i === idx ? { ...f, label: e.target.value } : f))}
                    placeholder="Label" style={{ ...inputStyle, flex: 1 }} />
                  <select value={field.type} onChange={e => setConfigFields(prev => prev.map((f, i) => i === idx ? { ...f, type: e.target.value as any } : f))}
                    style={{ ...inputStyle, width: 90, cursor: 'pointer' }}>
                    {['string', 'integer', 'float', 'boolean', 'select', 'text_area', 'file_path'].map(t => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                  <button onClick={() => setConfigFields(prev => prev.filter((_, i) => i !== idx))} style={{
                    background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 2,
                  }}>
                    <Trash2 size={10} />
                  </button>
                </div>
              ))}
            </div>

            {/* Actions */}
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <button onClick={handleSave} style={{
                flex: 1, padding: '8px 16px', background: T.cyan, border: 'none', borderRadius: 4,
                color: '#000', fontFamily: F, fontSize: FS.sm, fontWeight: 700, cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              }}>
                <Save size={12} /> SAVE
              </button>
              {selectedBlockType && (
                <button onClick={handleDelete} style={{
                  padding: '8px 12px', background: `${T.red}15`, border: `1px solid ${T.red}30`, borderRadius: 4,
                  color: T.red, fontFamily: F, fontSize: FS.sm, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 4,
                }}>
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          </div>

          {/* Right: Code editor + preview */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {/* Code editor area */}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', borderBottom: `1px solid ${T.border}`, minHeight: 0 }}>
              <div style={{
                padding: '8px 14px',
                borderBottom: `1px solid ${T.border}`,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                flexShrink: 0,
              }}>
                <Code size={10} color={T.dim} />
                <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.1em', fontWeight: 700 }}>
                  RUN.PY
                </span>
                <div style={{ flex: 1 }} />
                <button
                  onClick={handleTest}
                  disabled={testing}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 5,
                    padding: '3px 10px',
                    background: testing ? `${T.purple}08` : `${T.purple}14`,
                    border: `1px solid ${T.purple}33`,
                    borderRadius: 4,
                    color: T.purple,
                    fontFamily: F,
                    fontSize: FS.xxs,
                    fontWeight: 700,
                    letterSpacing: '0.08em',
                    cursor: testing ? 'default' : 'pointer',
                    opacity: testing ? 0.6 : 1,
                    transition: 'all 0.12s',
                  }}
                  title="Validate block code for syntax errors and compatibility"
                >
                  {testing
                    ? <Loader2 size={9} style={{ animation: 'spin 1s linear infinite' }} />
                    : <FlaskConical size={9} />}
                  {testing ? 'TESTING...' : 'TEST BLOCK'}
                </button>
              </div>
              <textarea
                value={code}
                onChange={e => { setCode(e.target.value); setTestResult(null) }}
                spellCheck={false}
                style={{
                  flex: 1,
                  padding: 14,
                  background: T.surface0,
                  color: T.text,
                  fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace",
                  fontSize: 12,
                  lineHeight: 1.6,
                  border: 'none',
                  outline: 'none',
                  resize: 'none',
                  tabSize: 4,
                }}
              />
              {/* Test results panel */}
              {testResult && (
                <div style={{
                  flexShrink: 0,
                  borderTop: `1px solid ${testResult.valid ? T.green : T.red}40`,
                  background: testResult.valid ? `${T.green}08` : `${T.red}08`,
                  maxHeight: 180,
                  overflowY: 'auto',
                }}>
                  {/* Header */}
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '6px 12px',
                    borderBottom: `1px solid ${testResult.valid ? T.green : T.red}20`,
                  }}>
                    {testResult.valid
                      ? <CheckCircle2 size={11} color={T.green} />
                      : <XCircle size={11} color={T.red} />}
                    <span style={{
                      fontFamily: F,
                      fontSize: FS.xxs,
                      fontWeight: 700,
                      color: testResult.valid ? T.green : T.red,
                      letterSpacing: '0.08em',
                    }}>
                      {testResult.valid ? 'VALIDATION PASSED' : 'VALIDATION FAILED'}
                    </span>
                    {testResult.warnings.length > 0 && (
                      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.amber, marginLeft: 4 }}>
                        · {testResult.warnings.length} warning{testResult.warnings.length !== 1 ? 's' : ''}
                      </span>
                    )}
                    <button
                      onClick={() => setTestResult(null)}
                      style={{ marginLeft: 'auto', background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 2, fontSize: 10 }}
                    >
                      ✕
                    </button>
                  </div>
                  {/* Errors */}
                  {testResult.errors.map((err, i) => (
                    <div key={i} style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 6,
                      padding: '5px 12px',
                      borderBottom: `1px solid ${T.red}15`,
                    }}>
                      <XCircle size={9} color={T.red} style={{ marginTop: 1, flexShrink: 0 }} />
                      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: T.red, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
                        {err}
                      </span>
                    </div>
                  ))}
                  {/* Warnings */}
                  {testResult.warnings.map((warn, i) => (
                    <div key={i} style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 6,
                      padding: '5px 12px',
                      borderBottom: `1px solid ${T.amber}15`,
                    }}>
                      <AlertTriangle size={9} color={T.amber} style={{ marginTop: 1, flexShrink: 0 }} />
                      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: T.amber, lineHeight: 1.5 }}>
                        {warn}
                      </span>
                    </div>
                  ))}
                  {testResult.valid && testResult.errors.length === 0 && testResult.warnings.length === 0 && (
                    <div style={{ padding: '6px 12px', fontFamily: F, fontSize: FS.xxs, color: T.green }}>
                      No issues found. Block code is compatible.
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Preview */}
            <div style={{ height: 180, minHeight: 180, display: 'flex' }}>
              {/* Live block preview */}
              <div style={{
                flex: 1,
                padding: 20,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: T.bg,
              }}>
                <div style={{
                  width: 240,
                  background: `linear-gradient(145deg, ${T.surface2} 0%, ${T.surface1} 100%)`,
                  border: `1px solid ${T.borderHi}`,
                  borderRadius: 8,
                  overflow: 'hidden',
                  boxShadow: `0 4px 12px ${T.shadow}`,
                }}>
                  {/* Accent bar */}
                  {(() => {
                    const previewAccent = CATEGORY_COLORS[category] || '#94A3B8'
                    return (
                      <>
                        <div style={{
                          height: 3,
                          background: `linear-gradient(90deg, ${previewAccent}, ${previewAccent}40, transparent)`,
                        }} />
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px 8px 14px', borderBottom: `1px solid ${T.border}` }}>
                          <div style={{
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            width: 24, height: 24, borderRadius: 4,
                            background: `linear-gradient(135deg, ${T.surface3}, ${T.surface1})`,
                            border: `1px solid ${T.borderHi}`,
                          }}>
                            <IconComponent size={12} color={previewAccent} />
                    </div>
                    <div style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 700 }}>{name}</div>
                  </div>
                  {/* Ports */}
                  <div style={{ padding: '6px 12px 10px', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {[...inputs, ...outputs].map((p, i) => (
                      <span key={i} style={{
                        fontFamily: F, fontSize: 5, color: CONNECTOR_COLORS[p.dataType] || T.dim,
                        display: 'flex', alignItems: 'center', gap: 2,
                      }}>
                        <span style={{ width: 3, height: 3, background: CONNECTOR_COLORS[p.dataType] || T.dim, display: 'inline-block' }} />
                        {p.dataType}
                      </span>
                    ))}
                  </div>
                      </>
                    )
                  })()}
                </div>
              </div>

              {/* YAML preview */}
              <div style={{
                width: 280,
                borderLeft: `1px solid ${T.border}`,
                overflow: 'auto',
                padding: 10,
                background: T.surface0,
              }}>
                <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 6, letterSpacing: '0.1em', fontWeight: 700 }}>
                  YAML PREVIEW
                </div>
                <pre style={{ margin: 0, fontFamily: F, fontSize: 10, color: T.sec, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
{`name: ${name}
type: ${selectedBlockType || 'custom_...'}
category: ${category}
description: ${description || '...'}
version: "1.0.0"
inputs:
${inputs.map(p => `  - id: ${p.id}\n    label: ${p.label}\n    data_type: ${p.dataType}`).join('\n')}
outputs:
${outputs.map(p => `  - id: ${p.id}\n    label: ${p.label}\n    data_type: ${p.dataType}`).join('\n')}
config:
${configFields.map(f => `  ${f.name}: # ${f.type}`).join('\n') || '  {}'}`}
                </pre>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
