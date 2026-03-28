import { useEffect, useState, useRef, useCallback, useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useShallow } from 'zustand/react/shallow'
import { useUIStore } from '@/stores/uiStore'
import { ReactFlowProvider } from '@xyflow/react'
import PipelineCanvas from '@/components/Pipeline/PipelineCanvas'
import BlockLibrary from '@/components/Pipeline/BlockLibrary'
import BlockConfig from '@/components/Pipeline/BlockConfig'
import RunControls from '@/components/Pipeline/RunControls'
import AgentWorkflowGenerator from '@/components/Pipeline/AgentWorkflowGenerator'
import ValidationPanel from '@/components/Pipeline/ValidationPanel'
import BackendValidationPanel from '@/components/Validation/ValidationPanel'
import PipelineTabBar from '@/components/Pipeline/PipelineTabBar'
import { validatePipelineClient, type DiagnosticReport } from '@/lib/pipeline-validator'
import PipelineMonitor, { type MonitorBlock } from '@/components/Pipeline/PipelineMonitor'
import { Save, StickyNote, Sparkles, FolderOpen, ChevronDown, ShieldCheck, Combine, Ungroup, Undo2, Redo2, Wand2, LayoutTemplate, FilePlus, FileDown, FileUp, AlertCircle, WifiOff } from 'lucide-react'
import TemplateGallery from '@/components/Pipeline/TemplateGallery'
import TemplateLanding from '@/components/Templates/TemplateLanding'
import ToolbarDropdown from '@/components/Pipeline/ToolbarDropdown'
import MissionController from '@/components/Mission/MissionController'
import { useRunStore } from '@/stores/runStore'
import { useValidationStore } from '@/stores/validationStore'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import toast from 'react-hot-toast'

const btnStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 4,
  padding: '3px 8px',
  background: 'transparent',
  border: `1px solid ${T.border}`,
  color: T.dim,
  fontFamily: F,
  fontSize: FS.xs,
  letterSpacing: '0.08em',
  cursor: 'pointer',
  transition: 'all 0.12s',
  whiteSpace: 'nowrap' as const,
}

export default function PipelineEditorView() {
  // Use targeted selectors to avoid re-rendering on unrelated state changes
  // (e.g. node dimension updates, edge changes, etc.)
  const { name, isDirty, nodes, pipelines } = usePipelineStore(useShallow((s) => ({
    name: s.name,
    isDirty: s.isDirty,
    nodes: s.nodes,
    pipelines: s.pipelines,
  })))
  const pastLength = usePipelineStore((s) => s.past.length)
  const futureLength = usePipelineStore((s) => s.future.length)
  const pipelineNotes = usePipelineStore((s) => s.pipelineNotes)
  const setPipelineNotes = usePipelineStore((s) => s.setPipelineNotes)

  // Actions — stable function refs, don't cause re-renders
  const setName = usePipelineStore((s) => s.setName)
  const savePipeline = usePipelineStore((s) => s.savePipeline)
  const addStickyNote = usePipelineStore((s) => s.addStickyNote)
  const exportPipeline = usePipelineStore((s) => s.exportPipeline)
  const importPipeline = usePipelineStore((s) => s.importPipeline)
  const groupSelectedNodes = usePipelineStore((s) => s.groupSelectedNodes)
  const ungroupSelectedNodes = usePipelineStore((s) => s.ungroupSelectedNodes)
  const tidyUp = usePipelineStore((s) => s.tidyUp)
  const fetchPipelines = usePipelineStore((s) => s.fetchPipelines)
  const loadPipeline = usePipelineStore((s) => s.loadPipeline)
  const newPipeline = usePipelineStore((s) => s.newPipeline)
  const deletePipeline = usePipelineStore((s) => s.deletePipeline)
  const undo = usePipelineStore((s) => s.undo)
  const redo = usePipelineStore((s) => s.redo)

  const selectedProjectId = useUIStore((s) => s.selectedProjectId)
  const setView = useUIStore((s) => s.setView)

  useEffect(() => {
    if (!selectedProjectId) {
      setView('dashboard')
    }
  }, [selectedProjectId, setView])

  // First-launch detection: show template landing when no pipelines exist
  const [firstLaunchChecked, setFirstLaunchChecked] = useState(false)
  const [showFirstLaunch, setShowFirstLaunch] = useState(false)

  useEffect(() => {
    if (firstLaunchChecked) return
    fetchPipelines().then(() => {
      const state = usePipelineStore.getState()
      if (state.pipelines.length === 0 && state.nodes.length === 0 && !state.id) {
        setShowFirstLaunch(true)
      }
      setFirstLaunchChecked(true)
    })
  }, [firstLaunchChecked, fetchPipelines])

  // Exit first-launch when a pipeline is loaded or created
  useEffect(() => {
    if (showFirstLaunch && (nodes.length > 0 || pipelines.length > 0)) {
      setShowFirstLaunch(false)
    }
  }, [showFirstLaunch, nodes.length, pipelines.length])

  const [showAgent, setShowAgent] = useState(false)
  const [showPipelineList, setShowPipelineList] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [showNewConfirm, setShowNewConfirm] = useState(false)
  const [showTemplateSelector, setShowTemplateSelector] = useState(false)
  const [showValidation, setShowValidation] = useState(false)
  const [validationReport, setValidationReport] = useState<DiagnosticReport | null>(null)
  const [validating, setValidating] = useState(false)
  const [showMonitor, setShowMonitor] = useState(false)
  const [showPipelineNotes, setShowPipelineNotes] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Run monitor state from store — SSE is handled exclusively by RunControls
  const nodeStatuses = useRunStore((s) => s.nodeStatuses)
  const overallProgress = useRunStore((s) => s.overallProgress)
  const runLogs = useRunStore((s) => s.logs)
  const runStatus = useRunStore((s) => s.status)
  const sseStatus = useRunStore((s) => s.sseStatus)
  const runError = useRunStore((s) => s.error)

  // Convert nodeStatuses to MonitorBlock format — memoized to avoid re-creating on every render
  const monitorBlocks: MonitorBlock[] = useMemo(() =>
    Object.values(nodeStatuses).map((ns) => {
      const nodeName = nodes.find(n => n.id === ns.nodeId)?.data.label || ns.nodeId
      return {
        id: ns.nodeId,
        name: nodeName,
        status: ns.status,
        log: ns.error || '',
      }
    }),
    [nodeStatuses, nodes]
  )

  // Auto-show monitor when run starts + sync tab run status
  const updateTabRunStatus = usePipelineStore((s) => s.updateTabRunStatus)
  const activeTabId = usePipelineStore((s) => s.activeTabId)
  useEffect(() => {
    if (runStatus === 'running') {
      setShowMonitor(true)
    }
    // Sync run status to active tab
    if (runStatus !== 'idle') {
      updateTabRunStatus(activeTabId, runStatus)
    }
  }, [runStatus, activeTabId, updateTabRunStatus])

  const handleSave = useCallback(async () => {
    try {
      await savePipeline()
      toast.success('Pipeline saved')
    } catch {
      toast.error('Failed to save pipeline')
    }
  }, [savePipeline])

  // Keyboard shortcuts (Undo/Redo/Save)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger if user is typing in an input/textarea
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return

      const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0
      const isCmdOrCtrl = isMac ? e.metaKey : e.ctrlKey

      if (isCmdOrCtrl && e.key.toLowerCase() === 's') {
        e.preventDefault()
        handleSave()
      } else if (isCmdOrCtrl && e.key.toLowerCase() === 'z') {
        e.preventDefault()
        if (e.shiftKey) {
          redo()
        } else {
          undo()
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [undo, redo, handleSave])

  // Warn before closing tab with unsaved changes
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (usePipelineStore.getState().isDirty) {
        e.preventDefault()
      }
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [])

  const handleImport = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      const text = ev.target?.result as string
      importPipeline(text)
    }
    reader.readAsText(file)
    e.target.value = ''
  }, [importPipeline])

  const handleAddStickyNote = useCallback(() => {
    addStickyNote({ x: 200, y: 200 })
  }, [addStickyNote])

  const handleOpenPipelineList = useCallback(async () => {
    if (!showPipelineList) {
      await fetchPipelines()
    }
    setShowPipelineList(!showPipelineList)
  }, [showPipelineList, fetchPipelines])

  const handleValidate = useCallback(async () => {
    setValidating(true)
    try {
      const { nodes, edges } = usePipelineStore.getState()
      const report = validatePipelineClient(nodes, edges)
      setValidationReport(report)
      setShowValidation(true)
    } finally {
      setValidating(false)
    }
  }, [])

  // ── Debounced backend validation on graph changes ──
  const pipelineId = usePipelineStore((s) => s.id)
  const edges = usePipelineStore((s) => s.edges)
  const backendValidation = useValidationStore((s) => s.result)
  const isBackendValidating = useValidationStore((s) => s.isValidating)
  const isBackendStale = useValidationStore((s) => s.isStale)
  const backendNodeErrors = useValidationStore((s) => s.nodeErrors)
  const backendPanelVisible = useValidationStore((s) => s.panelVisible)
  const validateBackend = useValidationStore((s) => s.validate)
  const markStale = useValidationStore((s) => s.markStale)

  // Stringify configs once per render for dependency tracking
  const configFingerprint = JSON.stringify(nodes.map(n => n.data.config))

  // Debounce backend validation by 500ms on node/edge/config changes.
  // markStale() fires immediately so the UI shows "VALIDATING..." without
  // waiting for the debounce to expire, preventing stale result display.
  const validationTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (!pipelineId || nodes.length === 0) return

    // Immediately mark current results stale — this causes the Run button
    // to show "VALIDATING..." and prevents acting on outdated validation
    markStale()

    if (validationTimerRef.current) clearTimeout(validationTimerRef.current)
    validationTimerRef.current = setTimeout(() => {
      validateBackend(pipelineId)
    }, 500)
    return () => {
      if (validationTimerRef.current) clearTimeout(validationTimerRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineId, nodes.length, edges.length, validateBackend, markStale, configFingerprint])

  // Count backend validation errors for the panel toggle badge
  const backendErrorCount = backendValidation ? backendValidation.errors.length : 0
  const backendWarningCount = backendValidation ? backendValidation.warnings.length : 0

  // Show TemplateLanding for first-launch (no pipelines exist)
  if (showFirstLaunch) {
    return <TemplateLanding />
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Toolbar */}
      <div
        style={{
          minHeight: 34,
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          padding: '4px 10px',
          gap: 6,
          borderBottom: `1px solid ${T.border}`,
          background: T.surface1,
          flexShrink: 0,
        }}
      >
        {/* Pipeline name + dropdown */}
        <div style={{ position: 'relative' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              style={{
                background: 'none',
                border: 'none',
                color: T.text,
                fontFamily: F,
                fontSize: FS.lg,
                fontWeight: 600,
                outline: 'none',
                padding: '2px 4px',
                minWidth: 140,
                maxWidth: 300,
                width: 'auto',
              }}
            />
            <button
              onClick={handleOpenPipelineList}
              style={{
                background: 'none',
                border: 'none',
                color: T.dim,
                cursor: 'pointer',
                padding: 2,
                display: 'flex',
              }}
            >
              <ChevronDown size={10} />
            </button>
          </div>

          {/* Pipeline list dropdown */}
          {showPipelineList && (
            <div
              style={{
                position: 'absolute',
                top: '100%',
                left: 0,
                width: 280,
                maxHeight: 300,
                overflowY: 'auto',
                background: T.surface2,
                border: `1px solid ${T.borderHi}`,
                zIndex: 100,
                boxShadow: `0 8px 24px ${T.shadow}`,
              }}
            >
              {/* New pipeline */}
              <button
                onClick={() => {
                  if (isDirty) {
                    setShowPipelineList(false)
                    setShowNewConfirm(true)
                  } else {
                    newPipeline()
                    setShowPipelineList(false)
                  }
                }}
                style={{
                  ...btnStyle,
                  width: '100%',
                  border: 'none',
                  borderBottom: `1px solid ${T.border}`,
                  color: T.cyan,
                  padding: '7px 10px',
                  fontWeight: 700,
                }}
              >
                + NEW PIPELINE
              </button>

              {pipelines.length === 0 ? (
                <div style={{ padding: 12, fontFamily: F, fontSize: FS.xs, color: T.dim, textAlign: 'center' }}>
                  No saved pipelines
                </div>
              ) : (
                pipelines.map((p) => (
                  <div
                    key={p.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      padding: '6px 10px',
                      borderBottom: `1px solid ${T.border}`,
                      gap: 8,
                      cursor: 'pointer',
                    }}
                    onClick={() => { loadPipeline(p.id); setShowPipelineList(false) }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = T.surface4 }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
                  >
                    <FolderOpen size={9} color={T.dim} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 600 }}>
                        {p.name}
                      </div>
                      <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                        {p.block_count} blocks
                      </div>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); setConfirmDelete(p.id); setShowPipelineList(false) }}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: T.red,
                        fontFamily: F,
                        fontSize: FS.xxs,
                        cursor: 'pointer',
                        opacity: 0.6,
                      }}
                    >
                      DEL
                    </button>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {isDirty && (
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.amber }}>UNSAVED</span>
        )}

        {/* Separator */}
        <div style={{ width: 1, height: 14, background: T.border }} />

        {/* File actions dropdown */}
        <ToolbarDropdown
          label="FILE"
          icon={<FolderOpen size={10} />}
          items={[
            {
              label: 'New Pipeline',
              icon: <FilePlus size={12} />,
              onClick: () => {
                if (isDirty) setShowNewConfirm(true)
                else usePipelineStore.getState().newPipeline()
              },
            },
            {
              label: 'Browse Templates',
              icon: <LayoutTemplate size={12} />,
              onClick: () => setShowTemplateSelector(true),
            },
            {
              label: 'Import JSON',
              icon: <FileUp size={12} />,
              onClick: handleImport,
              separator: true,
            },
            {
              label: 'Export JSON',
              icon: <FileDown size={12} />,
              onClick: exportPipeline,
            },
          ]}
        />

        {/* Quick actions */}
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <button onClick={tidyUp} style={btnStyle} title="Auto-Layout (Tidy)">
            <Wand2 size={10} />
            TIDY
          </button>

          <div style={{ width: 1, height: 12, background: T.border, margin: '0 2px' }} />

          <button
            onClick={undo}
            disabled={pastLength === 0}
            style={{ ...btnStyle, opacity: pastLength === 0 ? 0.4 : 1, cursor: pastLength === 0 ? 'default' : 'pointer' }}
            title="Undo (Cmd/Ctrl + Z)"
          >
            <Undo2 size={12} />
          </button>
          <button
            onClick={redo}
            disabled={futureLength === 0}
            style={{ ...btnStyle, opacity: futureLength === 0 ? 0.4 : 1, cursor: futureLength === 0 ? 'default' : 'pointer' }}
            title="Redo (Cmd/Ctrl + Shift + Z)"
          >
            <Redo2 size={12} />
          </button>
        </div>

        <div style={{ width: 1, height: 14, background: T.border }} />

        <button onClick={handleAddStickyNote} style={btnStyle} title="Add sticky note">
          <StickyNote size={10} />
        </button>
        <button
          onClick={() => setShowPipelineNotes(!showPipelineNotes)}
          style={{
            ...btnStyle,
            color: showPipelineNotes || pipelineNotes ? '#FFB74D' : T.dim,
            borderColor: showPipelineNotes ? 'rgba(255, 183, 77, 0.3)' : T.border,
          }}
          title="Pipeline notes"
        >
          <StickyNote size={10} color={showPipelineNotes || pipelineNotes ? '#FFB74D' : undefined} />
          <span style={{ fontSize: FS.xxs }}>Notes</span>
        </button>

        <ToolbarDropdown
          label="GROUP"
          icon={<Combine size={10} />}
          items={[
            { label: 'Group Selected', icon: <Combine size={12} />, onClick: groupSelectedNodes },
            { label: 'Ungroup Selected', icon: <Ungroup size={12} />, onClick: ungroupSelectedNodes },
          ]}
        />

        <div style={{ width: 1, height: 14, background: T.border }} />

        {/* Agent button */}
        <button
          onClick={() => setShowAgent(!showAgent)}
          style={{
            ...btnStyle,
            color: showAgent ? T.cyan : T.dim,
            border: showAgent ? `1px solid ${T.cyan}50` : `1px solid ${T.border}`,
            background: showAgent ? `${T.cyan}10` : 'transparent',
          }}
          title="AI Workflow Generator"
        >
          <Sparkles size={10} />
          AI
        </button>

        <div style={{ flex: 1 }} />

        {/* Block count */}
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          {nodes.length} BLOCKS
        </span>

        <div style={{ width: 1, height: 14, background: T.border }} />

        {/* Hidden file input for import */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".json,.blueprint.json"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />

        {/* Save */}
        <button
          onClick={handleSave}
          style={{
            ...btnStyle,
            background: T.surface3,
            color: T.sec,
          }}
        >
          <Save size={10} />
          SAVE
        </button>

        {/* Validate */}
        <button
          onClick={handleValidate}
          disabled={validating}
          style={{
            ...btnStyle,
            background: `${T.amber}10`,
            border: `1px solid ${T.amber}30`,
            color: T.amber,
            opacity: validating ? 0.5 : 1,
          }}
          title="Validate pipeline"
        >
          <ShieldCheck size={10} />
          <div style={{ width: 1, height: 14, background: T.border, marginLeft: 6, marginRight: 6 }} />
          {validating ? 'CHECKING...' : 'VALIDATE'}
        </button>

        <div style={{ width: 1, height: 14, background: T.border, marginLeft: 6, marginRight: 6 }} />

        {/* Run Controls (SSE, Execute, Template, Eject) */}
        <RunControls />
      </div>

      {/* Pipeline Tabs */}
      <PipelineTabBar />

      {/* Persistent error banner for failed runs */}
      {runStatus === 'failed' && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '8px 12px',
          background: `${T.red}10`,
          borderBottom: `1px solid ${T.red}25`,
          flexShrink: 0,
        }}>
          <AlertCircle size={14} color={T.red} />
          <span style={{ fontFamily: F, fontSize: FS.sm, color: T.red, flex: 1 }}>
            Pipeline run failed{runError ? `: ${runError.substring(0, 120)}` : ''}
          </span>
          <button
            onClick={() => useRunStore.getState().reset()}
            style={{
              background: 'none', border: `1px solid ${T.red}30`,
              color: T.red, fontFamily: F, fontSize: FS.xxs,
              padding: '2px 8px', cursor: 'pointer',
            }}
          >
            DISMISS
          </button>
        </div>
      )}

      {/* SSE connection warning during active run */}
      {runStatus === 'running' && (sseStatus === 'reconnecting' || sseStatus === 'stale') && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '6px 12px',
          background: '#F59E0B10',
          borderBottom: '1px solid #F59E0B25',
          flexShrink: 0,
        }}>
          <WifiOff size={14} color="#F59E0B" />
          <span style={{ fontFamily: F, fontSize: FS.xs, color: '#F59E0B' }}>
            {sseStatus === 'reconnecting'
              ? 'Reconnecting to server\u2026 Your run is still executing.'
              : 'Connection lost. Your run may still be executing on the server.'}
          </span>
        </div>
      )}

      {/* Editor area */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', position: 'relative' }}>
        <ReactFlowProvider>
          <BlockLibrary />
          <PipelineCanvas
            onShowTemplates={() => setShowTemplateSelector(true)}
            onShowAgent={() => setShowAgent(true)}
          />
          <BlockConfig />

          {/* Pipeline notes side panel — uses store for state, saved via savePipeline */}
          {showPipelineNotes && (
            <div
              style={{
                width: 300,
                minWidth: 300,
                height: '100%',
                background: `linear-gradient(180deg, ${T.surface1} 0%, ${T.surface0} 100%)`,
                borderLeft: `1px solid rgba(255, 183, 77, 0.2)`,
                display: 'flex',
                flexDirection: 'column',
                overflow: 'hidden',
              }}
            >
              <div style={{
                padding: '12px 16px',
                borderBottom: `1px solid ${T.border}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}>
                <span style={{
                  fontFamily: F,
                  fontSize: FS.sm,
                  color: '#FFB74D',
                  fontWeight: 700,
                  letterSpacing: '0.06em',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}>
                  <StickyNote size={14} color="#FFB74D" />
                  Pipeline Notes
                </span>
                <button
                  onClick={() => setShowPipelineNotes(false)}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: T.dim,
                    cursor: 'pointer',
                    padding: 4,
                  }}
                >
                  &times;
                </button>
              </div>
              <div style={{ flex: 1, padding: 16, overflow: 'auto' }}>
                <textarea
                  value={pipelineNotes}
                  onChange={(e) => setPipelineNotes(e.target.value)}
                  placeholder="Add hypotheses, reminders, reasoning..."
                  style={{
                    width: '100%',
                    height: '100%',
                    minHeight: 200,
                    padding: '10px 12px',
                    background: T.surface3,
                    border: `1px solid ${T.border}`,
                    borderRadius: 6,
                    color: T.text,
                    fontFamily: F,
                    fontSize: FS.sm,
                    resize: 'none',
                    outline: 'none',
                    lineHeight: 1.6,
                  }}
                  onFocus={(e) => { e.currentTarget.style.borderColor = 'rgba(255, 183, 77, 0.4)' }}
                  onBlur={(e) => { e.currentTarget.style.borderColor = T.border }}
                />
              </div>
              <div style={{
                padding: '12px 16px',
                borderTop: `1px solid ${T.border}`,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}>
                <span style={{
                  fontFamily: F,
                  fontSize: FS.xxs,
                  color: T.dim,
                  flex: 1,
                }}>
                  {isDirty ? 'Unsaved changes' : 'Saved'}
                </span>
                <button
                  onClick={handleSave}
                  style={{
                    padding: '6px 16px',
                    background: 'rgba(255, 183, 77, 0.15)',
                    border: '1px solid rgba(255, 183, 77, 0.3)',
                    borderRadius: 6,
                    color: '#FFB74D',
                    fontFamily: F,
                    fontSize: FS.xs,
                    fontWeight: 700,
                    cursor: 'pointer',
                  }}
                >
                  Save
                </button>
              </div>
            </div>
          )}

          {/* Validation panel modal – must be inside ReactFlowProvider (uses useReactFlow hook) */}
          <ValidationPanel
            visible={showValidation}
            report={validationReport}
            onClose={() => setShowValidation(false)}
          />

          {/* Backend validation panel — collapsible from bottom */}
          <BackendValidationPanel />
        </ReactFlowProvider>

        {/* Agent workflow generator panel */}
        {showAgent && (
          <AgentWorkflowGenerator onClose={() => setShowAgent(false)} />
        )}

        {/* Pipeline monitor panel */}
        <PipelineMonitor
          visible={showMonitor}
          blocks={monitorBlocks}
          progress={overallProgress}
          logs={runLogs}
          onClose={() => setShowMonitor(false)}
        />
      </div>

      {/* Template selector: show on button click */}
      {showTemplateSelector && (
        <TemplateGallery onClose={() => setShowTemplateSelector(false)} />
      )}

      {/* Mission system */}
      <MissionController />

      {/* Confirm delete pipeline */}
      <ConfirmDialog
        open={!!confirmDelete}
        title="Delete Pipeline"
        message="This pipeline will be permanently deleted. This action cannot be undone."
        confirmLabel="Delete"
        confirmColor={T.red}
        onConfirm={() => { if (confirmDelete) deletePipeline(confirmDelete); setConfirmDelete(null) }}
        onCancel={() => setConfirmDelete(null)}
      />

      {/* Confirm new pipeline when dirty */}
      <ConfirmDialog
        open={showNewConfirm}
        title="Unsaved Changes"
        message="You have unsaved changes. Create a new pipeline anyway? Your current changes will be lost."
        confirmLabel="Create New"
        confirmColor={T.amber}
        onConfirm={() => { newPipeline(); setShowNewConfirm(false) }}
        onCancel={() => setShowNewConfirm(false)}
      />
    </div>
  )
}
