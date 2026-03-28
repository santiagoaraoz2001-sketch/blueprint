import { useState, useRef, useCallback, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import Editor from '@monaco-editor/react'
import toast from 'react-hot-toast'
import { T, F, FS } from '@/lib/design-tokens'
import { api } from '@/api/client'
import {
  X, Sparkles, Loader2, CheckCircle2, AlertTriangle,
  XCircle, Download, Play, RotateCcw,
} from 'lucide-react'

/** LLM generation can take minutes — use a generous timeout */
const GENERATE_TIMEOUT_MS = 180_000
const MAX_DESCRIPTION_LENGTH = 2000

interface Props {
  visible: boolean
  onClose: () => void
  onInstalled?: () => void
}

interface ValidationResult {
  yaml_valid: boolean
  py_syntax_valid: boolean
  has_run_function: boolean
  outputs_match: boolean
  errors: string[]
  warnings: string[]
}

interface GenerateResult {
  block_yaml: string
  run_py: string
  block_type: string
  category: string
  validation: ValidationResult
}

interface TestResult {
  success: boolean
  outputs?: Record<string, unknown>
  error?: string
  stdout?: string
}

const CATEGORIES = [
  '', 'data', 'inference', 'training', 'evaluation',
  'flow', 'agents', 'endpoints', 'merge', 'output',
]

type ViewState = 'input' | 'loading' | 'preview'

export default function BlockGeneratorModal({ visible, onClose, onInstalled }: Props) {
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('')
  const [name, setName] = useState('')
  const [view, setView] = useState<ViewState>('input')
  const [result, setResult] = useState<GenerateResult | null>(null)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState<'yaml' | 'python'>('yaml')
  const [installing, setInstalling] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<TestResult | null>(null)

  // AbortController for cancelling in-flight LLM generation requests
  const abortRef = useRef<AbortController | null>(null)

  const cancelInFlight = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
  }, [])

  const handleGenerate = async () => {
    if (!description.trim()) return
    cancelInFlight()
    setView('loading')
    setError('')
    setResult(null)
    setTestResult(null)

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const res = await api.post<GenerateResult>('/block-generator/generate', {
        description: description.trim(),
        category: category || undefined,
        name: name.trim() || undefined,
      }, { timeoutMs: GENERATE_TIMEOUT_MS, signal: controller.signal })
      setResult(res)
      setView('preview')
    } catch (e: any) {
      // Don't show error if the request was intentionally cancelled
      if (e?.message === 'Request was cancelled') return
      setError(e?.message || 'Generation failed')
      setView('input')
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null
      }
    }
  }

  const handleInstall = async () => {
    if (!result) return
    setInstalling(true)
    try {
      await api.post('/block-generator/generate/install', {
        block_yaml: result.block_yaml,
        run_py: result.run_py,
        block_type: result.block_type,
        category: result.category,
      })
      toast.success(`Block "${result.block_type}" installed successfully`)
      onInstalled?.()
      onClose()
    } catch (e: any) {
      toast.error(e?.message || 'Installation failed')
    } finally {
      setInstalling(false)
    }
  }

  const handleTest = async () => {
    if (!result) return
    setTesting(true)
    setTestResult(null)
    try {
      const res = await api.post<TestResult>('/block-generator/generate/test', {
        block_yaml: result.block_yaml,
        run_py: result.run_py,
      })
      setTestResult(res)
    } catch (e: any) {
      setTestResult({ success: false, error: e?.message || 'Test failed' })
    } finally {
      setTesting(false)
    }
  }

  const handleRegenerate = () => {
    cancelInFlight()
    setView('input')
    setResult(null)
    setError('')
    setTestResult(null)
  }

  const handleClose = () => {
    cancelInFlight()
    setView('input')
    setResult(null)
    setError('')
    setDescription('')
    setCategory('')
    setName('')
    setTestResult(null)
    onClose()
  }

  if (!visible) return null

  const allValid = result?.validation &&
    result.validation.yaml_valid &&
    result.validation.py_syntax_valid &&
    result.validation.has_run_function

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        style={{
          position: 'fixed', inset: 0, zIndex: 10000,
          background: T.shadowHeavy, display: 'flex',
          alignItems: 'center', justifyContent: 'center',
        }}
        onClick={handleClose}
      >
        <motion.div
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.95, opacity: 0 }}
          onClick={(e) => e.stopPropagation()}
          style={{
            width: view === 'preview' ? 720 : 520,
            maxHeight: '85vh',
            overflowY: 'auto',
            background: T.surface1,
            border: `1px solid ${T.borderHi}`,
            borderRadius: 8,
            boxShadow: `0 16px 64px ${T.shadow}`,
            transition: 'width 0.2s ease',
          }}
        >
          {/* Header */}
          <div style={{
            display: 'flex', alignItems: 'center', padding: '14px 18px',
            borderBottom: `1px solid ${T.border}`, gap: 10,
          }}>
            <Sparkles size={14} color={T.purple} />
            <span style={{ fontFamily: F, fontSize: FS.lg, fontWeight: 700, color: T.text, flex: 1 }}>
              Generate Block with AI
            </span>
            <button onClick={handleClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.dim }}>
              <X size={14} />
            </button>
          </div>

          {/* Content */}
          {view === 'input' && (
            <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
              {error && (
                <div style={{
                  padding: '10px 14px', background: `${T.red}15`, border: `1px solid ${T.red}30`,
                  borderRadius: 6, fontFamily: F, fontSize: FS.xs, color: T.red, whiteSpace: 'pre-wrap',
                }}>
                  {error}
                </div>
              )}

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <label style={labelStyle}>DESCRIPTION</label>
                  <span style={{
                    fontFamily: F, fontSize: FS.xxs,
                    color: description.length > MAX_DESCRIPTION_LENGTH ? T.red : T.dim,
                  }}>
                    {description.length}/{MAX_DESCRIPTION_LENGTH}
                  </span>
                </div>
                <textarea
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  maxLength={MAX_DESCRIPTION_LENGTH}
                  rows={4}
                  placeholder="Describe the block you want to create, e.g.: A block that counts words in each text entry and outputs word frequency statistics"
                  style={{
                    ...inputStyle,
                    resize: 'vertical',
                  }}
                />
              </div>

              <div style={{ display: 'flex', gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <label style={labelStyle}>NAME (OPTIONAL)</label>
                  <input
                    value={name}
                    onChange={e => setName(e.target.value)}
                    placeholder="e.g. Word Counter"
                    style={inputStyle}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={labelStyle}>CATEGORY (OPTIONAL)</label>
                  <select
                    value={category}
                    onChange={e => setCategory(e.target.value)}
                    style={inputStyle}
                  >
                    <option value="">Auto-detect</option>
                    {CATEGORIES.filter(Boolean).map(c => (
                      <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          )}

          {view === 'loading' && (
            <div style={{
              padding: '60px 18px', display: 'flex', flexDirection: 'column',
              alignItems: 'center', gap: 16,
            }}>
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ repeat: Infinity, duration: 1.5, ease: 'linear' }}
              >
                <Loader2 size={28} color={T.purple} />
              </motion.div>
              <span style={{ fontFamily: F, fontSize: FS.sm, color: T.sec }}>
                Generating block with LLM...
              </span>
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                This may take 30-60 seconds depending on your model
              </span>
            </div>
          )}

          {view === 'preview' && result && (
            <div style={{ padding: '0' }}>
              {/* Validation badges */}
              <div style={{
                display: 'flex', gap: 8, padding: '12px 18px', flexWrap: 'wrap',
                borderBottom: `1px solid ${T.border}`,
              }}>
                <ValidationBadge ok={result.validation.yaml_valid} label="YAML Valid" />
                <ValidationBadge ok={result.validation.py_syntax_valid} label="Python Syntax" />
                <ValidationBadge ok={result.validation.has_run_function} label="run() Found" />
                <ValidationBadge ok={result.validation.outputs_match} label="Outputs Match" />
              </div>

              {/* Validation errors / warnings */}
              {result.validation.errors.length > 0 && (
                <div style={{
                  margin: '8px 18px 0', padding: '8px 12px',
                  background: `${T.red}10`, border: `1px solid ${T.red}25`, borderRadius: 6,
                }}>
                  {result.validation.errors.map((err, i) => (
                    <div key={i} style={{ fontFamily: F, fontSize: FS.xxs, color: T.red, marginBottom: 2 }}>
                      {err}
                    </div>
                  ))}
                </div>
              )}
              {result.validation.warnings.length > 0 && (
                <div style={{
                  margin: '8px 18px 0', padding: '8px 12px',
                  background: `${T.orange}10`, border: `1px solid ${T.orange}25`, borderRadius: 6,
                }}>
                  {result.validation.warnings.map((w, i) => (
                    <div key={i} style={{ fontFamily: F, fontSize: FS.xxs, color: T.orange, marginBottom: 2 }}>
                      {w}
                    </div>
                  ))}
                </div>
              )}

              {/* Tabs */}
              <div style={{
                display: 'flex', gap: 0, padding: '12px 18px 0',
              }}>
                <TabButton active={activeTab === 'yaml'} label="block.yaml" onClick={() => setActiveTab('yaml')} />
                <TabButton active={activeTab === 'python'} label="run.py" onClick={() => setActiveTab('python')} />
              </div>

              {/* Code preview */}
              <div style={{ padding: '8px 18px 12px', height: 320 }}>
                {useMemo(() => (
                  <Editor
                    language={activeTab === 'yaml' ? 'yaml' : 'python'}
                    theme={document.documentElement.dataset.theme === 'light' ? 'vs' : 'vs-dark'}
                    value={activeTab === 'yaml' ? result.block_yaml : result.run_py}
                    options={{
                      readOnly: true,
                      minimap: { enabled: false },
                      fontSize: 12,
                      lineNumbers: 'on',
                      wordWrap: 'off',
                      scrollBeyondLastLine: false,
                      padding: { top: 8 },
                    }}
                  />
                ), [activeTab, result.block_yaml, result.run_py])}
              </div>

              {/* Test result */}
              {testResult && (
                <div style={{
                  margin: '0 18px 12px', padding: '10px 14px',
                  background: testResult.success ? `${T.green}10` : `${T.red}10`,
                  border: `1px solid ${testResult.success ? `${T.green}25` : `${T.red}25`}`,
                  borderRadius: 6,
                }}>
                  <div style={{
                    fontFamily: F, fontSize: FS.xs, fontWeight: 700,
                    color: testResult.success ? T.green : T.red,
                    display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4,
                  }}>
                    {testResult.success ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                    {testResult.success ? 'Test Passed' : 'Test Failed'}
                  </div>
                  {testResult.error && (
                    <div style={{
                      fontFamily: F, fontSize: FS.xxs, color: T.sec,
                      whiteSpace: 'pre-wrap', maxHeight: 100, overflow: 'auto',
                    }}>
                      {testResult.error}
                    </div>
                  )}
                  {testResult.success && testResult.outputs && Object.keys(testResult.outputs).length > 0 && (
                    <div style={{
                      fontFamily: F, fontSize: FS.xxs, color: T.sec,
                      whiteSpace: 'pre-wrap',
                    }}>
                      Outputs: {JSON.stringify(testResult.outputs, null, 2)}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Footer */}
          <div style={{
            display: 'flex', justifyContent: 'flex-end', padding: '12px 18px',
            borderTop: `1px solid ${T.border}`, gap: 10,
          }}>
            {view === 'input' && (
              <>
                <button onClick={handleClose} style={btnSecondary}>Cancel</button>
                <button
                  onClick={handleGenerate}
                  disabled={!description.trim()}
                  style={{
                    ...btnPrimary,
                    opacity: description.trim() ? 1 : 0.5,
                    cursor: description.trim() ? 'pointer' : 'not-allowed',
                  }}
                >
                  <Sparkles size={12} /> Generate
                </button>
              </>
            )}
            {view === 'loading' && (
              <button onClick={handleRegenerate} style={btnSecondary}>Cancel</button>
            )}
            {view === 'preview' && (
              <>
                <button onClick={handleRegenerate} style={btnSecondary}>
                  <RotateCcw size={11} /> Regenerate
                </button>
                <button
                  onClick={handleTest}
                  disabled={testing || !result?.validation.py_syntax_valid}
                  style={{
                    ...btnSecondary,
                    borderColor: `${T.cyan}40`,
                    color: T.cyan,
                    opacity: testing || !result?.validation.py_syntax_valid ? 0.5 : 1,
                  }}
                >
                  {testing ? <Loader2 size={11} /> : <Play size={11} />}
                  Test Block
                </button>
                <button
                  onClick={handleInstall}
                  disabled={installing || !allValid}
                  style={{
                    ...btnPrimary,
                    background: T.green,
                    opacity: installing || !allValid ? 0.5 : 1,
                    cursor: installing || !allValid ? 'not-allowed' : 'pointer',
                  }}
                >
                  {installing ? <Loader2 size={12} /> : <Download size={12} />}
                  Install to Blueprint
                </button>
              </>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}


function ValidationBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 4,
      padding: '3px 8px', borderRadius: 4,
      background: ok ? `${T.green}12` : `${T.red}12`,
      border: `1px solid ${ok ? `${T.green}25` : `${T.red}25`}`,
    }}>
      {ok ? <CheckCircle2 size={10} color={T.green} /> : <AlertTriangle size={10} color={T.red} />}
      <span style={{ fontFamily: F, fontSize: FS.xxs, color: ok ? T.green : T.red, fontWeight: 600 }}>
        {label}
      </span>
    </div>
  )
}


function TabButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '6px 14px', background: active ? T.surface3 : 'transparent',
        border: 'none', borderBottom: active ? `2px solid ${T.cyan}` : '2px solid transparent',
        color: active ? T.text : T.dim, fontFamily: F, fontSize: FS.xs,
        fontWeight: active ? 700 : 400, cursor: 'pointer',
      }}
    >
      {label}
    </button>
  )
}


// ── Shared styles ──

const labelStyle: React.CSSProperties = {
  fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 700,
  letterSpacing: '0.1em', display: 'block', marginBottom: 4,
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '8px 12px', background: T.surface3,
  border: `1px solid ${T.border}`, borderRadius: 6,
  color: T.text, fontFamily: F, fontSize: FS.sm, outline: 'none',
  boxSizing: 'border-box',
}

const btnSecondary: React.CSSProperties = {
  padding: '8px 16px', background: T.surface3,
  border: `1px solid ${T.border}`, borderRadius: 6,
  color: T.dim, fontFamily: F, fontSize: FS.sm, cursor: 'pointer',
  display: 'flex', alignItems: 'center', gap: 6,
}

const btnPrimary: React.CSSProperties = {
  padding: '8px 20px', background: T.purple, border: 'none',
  borderRadius: 6, color: '#fff', fontFamily: F, fontSize: FS.sm,
  fontWeight: 700, cursor: 'pointer',
  display: 'flex', alignItems: 'center', gap: 6,
}
