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
import PipelineTabBar from '@/components/Pipeline/PipelineTabBar'
import { validatePipelineClient, type DiagnosticReport } from '@/lib/pipeline-validator'
import PipelineMonitor, { type MonitorBlock } from '@/components/Pipeline/PipelineMonitor'
import { Save, Download, Upload, StickyNote, Sparkles, FolderOpen, ChevronDown, ShieldCheck, Combine, Ungroup, Undo2, Redo2, Wand2, LayoutTemplate } from 'lucide-react'
import TemplateGallery from '@/components/Pipeline/TemplateGallery'
import MissionController from '@/components/Mission/MissionController'
import { useRunStore } from '@/stores/runStore'
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
      toast.error('Please select a project first')
      setView('dashboard')
    }
  }, [selectedProjectId, setView])

  const [showAgent, setShowAgent] = useState(false)
  const [showPipelineList, setShowPipelineList] = useState(false)
  const [showTemplateSelector, setShowTemplateSelector] = useState(false)
  const [showValidation, setShowValidation] = useState(false)
  const [validationReport, setValidationReport] = useState<DiagnosticReport | null>(null)
  const [validating, setValidating] = useState(false)
  const [showMonitor, setShowMonitor] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Run monitor state from store — SSE is handled exclusively by RunControls
  const nodeStatuses = useRunStore((s) => s.nodeStatuses)
  const overallProgress = useRunStore((s) => s.overallProgress)
  const runLogs = useRunStore((s) => s.logs)
  const runStatus = useRunStore((s) => s.status)

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

  // Keyboard shortcuts (Undo/Redo)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger if user is typing in an input/textarea
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return

      const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0
      const isCmdOrCtrl = isMac ? e.metaKey : e.ctrlKey

      if (isCmdOrCtrl && e.key.toLowerCase() === 'z') {
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
  }, [undo, redo])

  const handleSave = async () => {
    try {
      await savePipeline()
      toast.success('Pipeline saved')
    } catch {
      toast.error('Failed to save pipeline')
    }
  }

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
    } finally {
      setValidating(false)
    }
  }, [])



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
                width: 160,
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
                onClick={() => { newPipeline(); setShowPipelineList(false) }}
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
                      onClick={(e) => { e.stopPropagation(); deletePipeline(p.id) }}
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

        {/* Left Actions */}
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', borderRight: `1px solid ${T.border}`, paddingRight: 16 }}>
          <button
            onClick={() => usePipelineStore.getState().newPipeline()}
            style={btnStyle}
            title="New Pipeline"
          >
            <FolderOpen size={10} />
            NEW
          </button>

          <button
            onClick={() => setShowTemplateSelector(true)}
            style={btnStyle}
            title="Pipeline Templates"
          >
            <LayoutTemplate size={10} />
            TEMPLATES
          </button>

          <button
            onClick={tidyUp}
            style={btnStyle}
            title="Auto-Layout / Tidy Up Pipeline"
          >
            <Wand2 size={10} />
            TIDY
          </button>

          <div style={{ width: 1, height: 12, background: T.border, margin: '0 4px' }} />

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
        <button onClick={handleAddStickyNote} style={btnStyle} title="Add sticky note">
          <StickyNote size={10} />
          NOTE
        </button>

        {/* Grouping */}
        <div style={{ width: 1, height: 14, background: T.border }} />
        <button onClick={groupSelectedNodes} style={btnStyle} title="Group selected nodes">
          <Combine size={10} />
          GROUP
        </button>
        <button onClick={ungroupSelectedNodes} style={btnStyle} title="Ungroup selected node">
          <Ungroup size={10} />
          UNGROUP
        </button>
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

        {/* Import */}
        <button onClick={handleImport} style={btnStyle} title="Import pipeline JSON">
          <Upload size={10} />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".json,.blueprint.json"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />

        {/* Export */}
        <button onClick={exportPipeline} style={btnStyle} title="Export pipeline JSON">
          <Download size={10} />
        </button>

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

      {/* Editor area */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', position: 'relative' }}>
        <ReactFlowProvider>
          <BlockLibrary />
          <PipelineCanvas />
          <BlockConfig />

          {/* Validation panel modal – must be inside ReactFlowProvider (uses useReactFlow hook) */}
          <ValidationPanel
            visible={showValidation}
            report={validationReport}
            onClose={() => setShowValidation(false)}
          />
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
    </div>
  )
}
