import { useEffect, useMemo, useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useRunStore } from '@/stores/runStore'
import { useOutputStore } from '@/stores/outputStore'
import { useUIStore } from '@/stores/uiStore'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useValidationStore } from '@/stores/validationStore'
import { validatePipelineClient } from '@/lib/pipeline-validator'
import { Play, Square, Loader2, FileCode, LayoutTemplate, X, Download, Copy, Check, AlertTriangle, Gauge, FileDown, MoreVertical, ShieldAlert } from 'lucide-react'
import ToolbarDropdown from './ToolbarDropdown'
import toast from 'react-hot-toast'
import PipelineAnalysisPanel from './PipelineAnalysisPanel'
import { getBlockDefinition } from '@/lib/block-registry'
import { generateRequirements } from '@/lib/block-dependencies'
import Editor from '@monaco-editor/react'

export default function RunControls() {
  const pipelineId = usePipelineStore((s) => s.id)
  const nodes = usePipelineStore((s) => s.nodes)
  const saveAsTemplate = usePipelineStore((s) => s.saveAsTemplate)
  const { status, activeRunId, overallProgress, startRun, stopRun, connectSSE, disconnectSSE, reset } =
    useRunStore()
  const [showTemplateModal, setShowTemplateModal] = useState(false)
  const [templateName, setTemplateName] = useState('')
  const [templateDesc, setTemplateDesc] = useState('')
  const [templateCat, setTemplateCat] = useState('inference')

  const [showCodeModal, setShowCodeModal] = useState(false)
  const [generatedCode, setGeneratedCode] = useState('')
  const [codeCopied, setCodeCopied] = useState(false)
  const [showAnalysis, setShowAnalysis] = useState(false)

  const isRunning = status === 'running'
  const isStarting = useRunStore((s) => s.isStarting)
  const backendValidation = useValidationStore((s) => s.result)
  const isBackendValidating = useValidationStore((s) => s.isValidating)
  const isBackendStale = useValidationStore((s) => s.isStale)
  const backendErrorCount = backendValidation ? backendValidation.errors.length : 0
  const hasBackendErrors = backendValidation !== null && !backendValidation.valid && !isBackendStale
  // Treat stale results as "still validating" — don't allow runs based on outdated state
  const isPendingValidation = isBackendValidating || isBackendStale
  const isRunDisabled = isRunning || isStarting || nodes.length === 0 || hasBackendErrors || isPendingValidation

  // SSE subscription via centralized manager
  useEffect(() => {
    if (activeRunId && isRunning) {
      connectSSE(activeRunId)
    } else {
      disconnectSSE()
    }
    return () => disconnectSSE()
  }, [activeRunId, isRunning, connectSSE, disconnectSSE])

  const [showTraceback, setShowTraceback] = useState(false)

  // Reset node statuses when run completes
  useEffect(() => {
    if (status === 'complete') {
      toast.success('Pipeline run completed')
    } else if (status === 'failed') {
      const error = useRunStore.getState().error
      toast.error(error || 'Pipeline run failed')
    } else if (status === 'cancelled') {
      toast('Pipeline run cancelled', { icon: '\u26A0\uFE0F' })
    }
  }, [status])

  const handleRun = async () => {
    if (nodes.length === 0) {
      toast.error('Add blocks to the pipeline first')
      return
    }

    // Pre-flight validation
    const edges = usePipelineStore.getState().edges
    const report = validatePipelineClient(nodes, edges)

    if (!report.valid) {
      // Show first 3 errors as toasts
      for (const err of report.errors.slice(0, 3)) {
        toast.error(err.message)
      }
      if (report.errors.length > 3) {
        toast.error(`...and ${report.errors.length - 3} more errors. Run VALIDATE for details.`)
      }
      return
    }

    // Show warnings but continue
    for (const warn of report.warnings.slice(0, 2)) {
      toast(warn.message, { icon: '⚠️' })
    }

    // Auto-save if the pipeline hasn't been persisted yet.
    // This guarantees every execution gets a unique pipeline ID,
    // which is required for artifact tracking and the output dashboard.
    let resolvedPipelineId = pipelineId
    if (!resolvedPipelineId) {
      try {
        await usePipelineStore.getState().savePipeline()
        resolvedPipelineId = usePipelineStore.getState().id
      } catch {
        toast.error('Failed to save pipeline before execution')
        return
      }
      if (!resolvedPipelineId) {
        toast.error('Failed to save pipeline before execution')
        return
      }
    }

    reset()
    await startRun(resolvedPipelineId)

    // Wire output view: subscribe to SSE and auto-switch
    const runId = useRunStore.getState().activeRunId
    if (runId) {
      useOutputStore.getState().subscribeToRun(runId)
      useUIStore.getState().setView('output')
    }
  }

  const handleStop = async () => {
    await stopRun()
    useOutputStore.getState().unsubscribeFromRun()
  }

  const handleEject = async () => {
    if (!pipelineId) {
      toast.error('Save pipeline first')
      return
    }

    // Pre-eject validation
    const warnings: string[] = []
    const errors: string[] = []
    const { edges } = usePipelineStore.getState()

    for (const node of nodes) {
      const def = getBlockDefinition(node.data.type)
      if (!def) continue

      // Check required inputs are connected
      for (const input of def.inputs) {
        if (input.required) {
          const hasConnection = edges.some(
            (e) => e.target === node.id && e.targetHandle === input.id,
          )
          if (!hasConnection) {
            errors.push(`${node.data.label}: missing required input "${input.label}"`)
          }
        }
      }

      // Check empty config fields that have no default
      for (const field of def.configFields) {
        if (field.default === undefined || field.default === '') {
          const val = node.data.config?.[field.name]
          if (val === '' || val === undefined || val === null) {
            warnings.push(`${node.data.label}: empty config "${field.label || field.name}"`)
          }
        }
      }
    }

    if (errors.length > 0) {
      errors.forEach((e) => toast.error(e, { duration: 5000 }))
      return
    }
    if (warnings.length > 0) {
      warnings.slice(0, 3).forEach((w) => toast(w, { icon: '⚠️', duration: 4000 }))
    }

    try {
      const baseUrl = import.meta.env.VITE_API_URL || '/api'
      const res = await fetch(`${baseUrl}/pipelines/${pipelineId}/compile`)
      if (!res.ok) throw new Error('Failed to compile pipeline')
      const code = await res.text()
      setGeneratedCode(code)
      setCodeCopied(false)
      setShowCodeModal(true)
    } catch (e: any) {
      toast.error(e.message || 'Failed to eject pipeline')
    }
  }

  const handleDownloadRequirements = () => {
    const blockTypes = nodes.map((n) => n.data.type)
    const content = generateRequirements(blockTypes)
    const blob = new Blob([content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'requirements.txt'
    a.click()
    URL.revokeObjectURL(url)
    toast.success('Downloaded requirements.txt')
  }

  const handleDownloadCode = () => {
    const blob = new Blob([generatedCode], { type: 'text/x-python' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `pipeline_${pipelineId?.substring(0, 8) || 'export'}.py`
    a.click()
    URL.revokeObjectURL(url)
    toast.success('Downloaded!')
  }

  const handleCopyCode = async () => {
    try {
      await navigator.clipboard.writeText(generatedCode)
      setCodeCopied(true)
      toast.success('Copied to clipboard!')
      setTimeout(() => setCodeCopied(false), 2000)
    } catch {
      toast.error('Failed to copy')
    }
  }

  const handleSaveTemplate = () => {
    if (nodes.length === 0) {
      toast.error('Add nodes before saving a template')
      return
    }
    setShowTemplateModal(true)
  }

  const submitTemplate = () => {
    if (!templateName.trim()) {
      toast.error('Name required')
      return
    }
    saveAsTemplate(templateName, templateDesc, templateCat)
    setShowTemplateModal(false)
    setTemplateName('')
    setTemplateDesc('')
    setTemplateCat('inference')
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      {isRunning && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginRight: 4 }}>
          {/* Progress bar */}
          <div
            style={{
              width: 80,
              height: 4,
              background: T.surface3,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${Math.round(overallProgress * 100)}%`,
                height: '100%',
                background: T.cyan,
                transition: 'width 0.3s ease',
              }}
            />
          </div>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.cyan }}>
            {Math.round(overallProgress * 100)}%
          </span>
        </div>
      )}

      {/* Status badge for failed/cancelled (GAP 13) */}
      {status === 'failed' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginRight: 4 }}>
          <span style={{
            padding: '1px 6px', background: `${T.red}14`, border: `1px solid ${T.red}33`,
            fontFamily: F, fontSize: FS.xxs, color: T.red, fontWeight: 600, letterSpacing: '0.08em',
          }}>
            FAILED
          </span>
          {useRunStore.getState().error && (
            <button
              onClick={() => setShowTraceback(!showTraceback)}
              style={{
                padding: '1px 6px', background: 'transparent', border: `1px solid ${T.border}`,
                fontFamily: F, fontSize: FS.xxs, color: T.dim, cursor: 'pointer',
              }}
            >
              {showTraceback ? 'HIDE' : 'DETAILS'}
            </button>
          )}
        </div>
      )}
      {status === 'cancelled' && (
        <span style={{
          padding: '1px 6px', background: '#F59E0B14', border: '1px solid #F59E0B33',
          fontFamily: F, fontSize: FS.xxs, color: '#F59E0B', fontWeight: 600,
          letterSpacing: '0.08em', marginRight: 4,
        }}>
          CANCELLED
        </span>
      )}

      {!isRunning ? (
        <>
          <button
            onClick={isRunDisabled ? undefined : handleRun}
            data-tour="btn-run-pipeline"
            title={
              nodes.length === 0 ? 'Add blocks to run'
              : isPendingValidation ? 'Validating...'
              : hasBackendErrors ? `${backendErrorCount} validation error${backendErrorCount !== 1 ? 's' : ''} — fix to enable`
              : isStarting ? 'Starting...'
              : 'Run Pipeline (Cmd/Ctrl + Enter)'
            }
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '5px 16px',
              background: hasBackendErrors ? `${T.red}14` : isPendingValidation ? `${T.amber}14` : `${T.green}22`,
              border: `1px solid ${hasBackendErrors ? `${T.red}50` : isPendingValidation ? `${T.amber}40` : `${T.green}50`}`,
              borderRadius: 4,
              color: hasBackendErrors ? T.red : isPendingValidation ? T.amber : T.green,
              fontFamily: F,
              fontSize: FS.xs,
              fontWeight: 800,
              letterSpacing: '0.08em',
              cursor: isRunDisabled ? 'not-allowed' : 'pointer',
              transition: 'all 0.15s',
              opacity: isRunDisabled ? 0.5 : 1,
              pointerEvents: isRunDisabled ? 'none' as const : 'auto' as const,
              position: 'relative' as const,
            }}
            onMouseEnter={(e) => { if (!isRunDisabled) { e.currentTarget.style.background = `${T.green}30`; e.currentTarget.style.borderColor = `${T.green}70` } }}
            onMouseLeave={(e) => { e.currentTarget.style.background = hasBackendErrors ? `${T.red}14` : `${T.green}22`; e.currentTarget.style.borderColor = hasBackendErrors ? `${T.red}50` : `${T.green}50` }}
          >
            {isPendingValidation ? (
              <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} />
            ) : hasBackendErrors ? (
              <ShieldAlert size={12} />
            ) : isStarting ? (
              <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} />
            ) : (
              <Play size={12} />
            )}
            {isPendingValidation ? 'VALIDATING...' : isStarting ? 'STARTING...' : hasBackendErrors ? `${backendErrorCount} ERROR${backendErrorCount !== 1 ? 'S' : ''}` : status === 'complete' || status === 'failed' ? 'RE-RUN' : 'RUN'}
          </button>
          <ToolbarDropdown
            label=""
            icon={<MoreVertical size={12} />}
            items={[
              { label: 'Save as Template', icon: <LayoutTemplate size={12} color={T.blue} />, onClick: handleSaveTemplate, color: T.blue },
              { label: 'Analyze Pipeline', icon: <Gauge size={12} color={T.amber} />, onClick: () => setShowAnalysis(true), color: T.amber },
              { label: 'Eject to Python', icon: <FileCode size={12} color={T.purple} />, onClick: handleEject, color: T.purple, separator: true },
            ]}
          />
        </>
      ) : (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <Loader2
              size={10}
              color={T.cyan}
              style={{ animation: 'spin 1s linear infinite' }}
            />
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.cyan }}>
              RUNNING
            </span>
          </div>
          <button
            onClick={handleStop}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              padding: '3px 10px',
              background: `${T.red}14`,
              border: `1px solid ${T.red}33`,
              color: T.red,
              fontFamily: F,
              fontSize: FS.xs,
              letterSpacing: '0.08em',
              cursor: 'pointer',
            }}
          >
            <Square size={8} />
            STOP
          </button>
        </>
      )}

      {/* Template Modal */}
      {showTemplateModal && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center', background: T.shadowHeavy }} onClick={() => setShowTemplateModal(false)}>
          <div style={{ width: 400, background: T.surface1, border: `1px solid ${T.borderHi}`, padding: 20 }} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
              <span style={{ fontFamily: F, fontSize: FS.md, color: T.text, fontWeight: 700 }}>Save Template</span>
              <button onClick={() => setShowTemplateModal(false)} style={{ background: 'none', border: 'none', color: T.dim }}><X size={14} /></button>
            </div>

            <label style={{ display: 'block', fontFamily: F, fontSize: FS.xs, color: T.sec, marginBottom: 4 }}>NAME</label>
            <input value={templateName} onChange={e => setTemplateName(e.target.value)} style={{ width: '100%', padding: 8, background: T.surface3, border: `1px solid ${T.border}`, color: T.text, marginBottom: 12 }} />

            <label style={{ display: 'block', fontFamily: F, fontSize: FS.xs, color: T.sec, marginBottom: 4 }}>DESCRIPTION</label>
            <input value={templateDesc} onChange={e => setTemplateDesc(e.target.value)} style={{ width: '100%', padding: 8, background: T.surface3, border: `1px solid ${T.border}`, color: T.text, marginBottom: 12 }} />

            <label style={{ display: 'block', fontFamily: F, fontSize: FS.xs, color: T.sec, marginBottom: 4 }}>CATEGORY</label>
            <select value={templateCat} onChange={e => setTemplateCat(e.target.value)} style={{ width: '100%', padding: 8, background: T.surface3, border: `1px solid ${T.border}`, color: T.text, marginBottom: 20 }}>
              <option value="training">Training</option>
              <option value="inference">Inference</option>
              <option value="data">Data</option>
              <option value="agents">Agents</option>
              <option value="evaluation">Evaluation</option>
              <option value="merge">Merge</option>
            </select>

            <button onClick={submitTemplate} style={{ width: '100%', padding: 10, background: T.blue, color: '#fff', border: 'none', fontWeight: 700, cursor: 'pointer' }}>
              SAVE TEMPLATE
            </button>
          </div>
        </div>
      )}

      {/* Code Preview Modal */}
      {showCodeModal && (
        <div
          style={{ position: 'fixed', inset: 0, zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center', background: T.shadowHeavy }}
          onClick={() => setShowCodeModal(false)}
        >
          <div
            style={{
              width: 720,
              maxWidth: '90vw',
              maxHeight: '85vh',
              background: T.surface1,
              border: `1px solid ${T.borderHi}`,
              borderRadius: 8,
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
            }}
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '14px 16px',
              borderBottom: `1px solid ${T.border}`,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <FileCode size={16} color={T.purple} />
                <span style={{ fontFamily: F, fontSize: FS.md, color: T.text, fontWeight: 700 }}>
                  Ejected Python Script
                </span>
              </div>
              <button
                onClick={() => setShowCodeModal(false)}
                style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 4 }}
              >
                <X size={16} />
              </button>
            </div>

            {/* Warning banner */}
            <div style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 8,
              padding: '10px 16px',
              background: `${T.amber}10`,
              borderBottom: `1px solid ${T.amber}30`,
            }}>
              <AlertTriangle size={14} color={T.amber} style={{ marginTop: 2, flexShrink: 0 }} />
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.amber, lineHeight: 1.5 }}>
                This script contains absolute paths to block directories on this machine. Copy the referenced block folders alongside the script to make it portable.
              </span>
            </div>

            {/* Code area — Monaco Editor (memoized to prevent re-initialization) */}
            <div style={{ flex: 1, overflow: 'hidden' }}>
              {useMemo(() => (
                <Editor
                  language="python"
                  theme="vs-dark"
                  value={generatedCode}
                  options={{
                    readOnly: true,
                    minimap: { enabled: false },
                    fontSize: 12,
                    lineHeight: 20,
                    scrollBeyondLastLine: false,
                    wordWrap: 'off',
                    folding: true,
                    lineNumbers: 'on',
                    renderLineHighlight: 'line',
                    scrollbar: { verticalScrollbarSize: 8, horizontalScrollbarSize: 8 },
                    padding: { top: 8, bottom: 8 },
                  }}
                />
              ), [generatedCode])}
            </div>

            {/* Footer actions */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'flex-end',
              gap: 8,
              padding: '12px 16px',
              borderTop: `1px solid ${T.border}`,
              background: T.surface1,
            }}>
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginRight: 'auto' }}>
                {generatedCode.split('\n').length} lines
              </span>
              <button
                onClick={handleCopyCode}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '6px 14px',
                  background: `${T.cyan}14`,
                  border: `1px solid ${T.cyan}33`,
                  color: T.cyan,
                  fontFamily: F,
                  fontSize: FS.xs,
                  letterSpacing: '0.06em',
                  cursor: 'pointer',
                  borderRadius: 4,
                }}
              >
                {codeCopied ? <Check size={12} /> : <Copy size={12} />}
                {codeCopied ? 'COPIED' : 'COPY'}
              </button>
              <button
                onClick={handleDownloadCode}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '6px 14px',
                  background: `${T.purple}14`,
                  border: `1px solid ${T.purple}33`,
                  color: T.purple,
                  fontFamily: F,
                  fontSize: FS.xs,
                  letterSpacing: '0.06em',
                  cursor: 'pointer',
                  borderRadius: 4,
                }}
              >
                <Download size={12} />
                DOWNLOAD .PY
              </button>
              <button
                onClick={handleDownloadRequirements}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '6px 14px',
                  background: `${T.amber}14`,
                  border: `1px solid ${T.amber}33`,
                  color: T.amber,
                  fontFamily: F,
                  fontSize: FS.xs,
                  letterSpacing: '0.06em',
                  cursor: 'pointer',
                  borderRadius: 4,
                }}
              >
                <FileDown size={12} />
                REQUIREMENTS.TXT
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Pipeline Analysis Panel */}
      <PipelineAnalysisPanel open={showAnalysis} onClose={() => setShowAnalysis(false)} />

      {/* Traceback expansion (GAP 13) */}
      {showTraceback && status === 'failed' && useRunStore.getState().error && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 100,
          marginTop: 4, padding: 10, background: T.surface1,
          border: `1px solid ${T.red}33`, maxHeight: 200, overflow: 'auto',
        }}>
          <pre style={{
            fontFamily: F, fontSize: FS.xxs, color: T.red,
            whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: 0,
          }}>
            {useRunStore.getState().error}
          </pre>
        </div>
      )}
    </div>
  )
}
