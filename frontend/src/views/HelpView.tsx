import { useState, useMemo, useCallback, useRef, useEffect, memo } from 'react'
import { motion } from 'framer-motion'
import { T, F, FD, FS } from '@/lib/design-tokens'
import { useSettingsStore } from '@/stores/settingsStore'
import { useHardwareStore } from '@/stores/hardwareStore'
import { estimatePipeline, type HardwareSpec } from '@/lib/pipeline-estimator'
import { getAllBlocks } from '@/lib/block-registry'
import {
  BookOpen,
  Sparkles,
  Menu,
  Cpu,
} from 'lucide-react'

import HelpSidebar, { type TocSection } from '@/components/Help/HelpSidebar'
import HelpSearch, { type SearchableSection } from '@/components/Help/HelpSearch'
import HelpAssistant from '@/components/Help/HelpAssistant'

import GettingStarted, { GETTING_STARTED_TEXT } from './help/GettingStarted'
import ProjectsDashboard, { PROJECTS_DASHBOARD_TEXT } from './help/ProjectsDashboard'
import PipelineEditor, { PIPELINE_EDITOR_TEXT } from './help/PipelineEditor'
import BlocksReference, { BLOCKS_REFERENCE_TEXT } from './help/BlocksReference'
import DatasetsData, { DATASETS_DATA_TEXT } from './help/DatasetsData'
import BlockWorkshop, { BLOCK_WORKSHOP_TEXT } from './help/BlockWorkshop'
import ExecutionMonitoring, { EXECUTION_MONITORING_TEXT } from './help/ExecutionMonitoring'
import ResultsAnalysis, { RESULTS_ANALYSIS_TEXT } from './help/ResultsAnalysis'
import ExportConnectors, { EXPORT_CONNECTORS_TEXT } from './help/ExportConnectors'
import PluginSystem, { PLUGIN_SYSTEM_TEXT } from './help/PluginSystem'
import KeyboardShortcuts, { KEYBOARD_SHORTCUTS_TEXT } from './help/KeyboardShortcuts'
import CLITools, { CLI_TOOLS_TEXT } from './help/CLITools'
import SettingsConfig, { SETTINGS_CONFIG_TEXT } from './help/SettingsConfig'
import Troubleshooting, { TROUBLESHOOTING_TEXT } from './help/Troubleshooting'
import FAQ, { FAQ_TEXT } from './help/FAQ'

/* ------------------------------------------------------------------ */
/*  Table of Contents                                                  */
/* ------------------------------------------------------------------ */

const TOC: TocSection[] = [
  {
    id: 'getting-started',
    title: '1. Getting Started',
    children: [
      { id: 'getting-started/what-is-blueprint', title: 'What is Blueprint?' },
      { id: 'getting-started/system-requirements', title: 'System Requirements' },
      { id: 'getting-started/installation', title: 'Installation' },
      { id: 'getting-started/mode-toggle', title: 'Simple vs Professional Mode' },
      { id: 'getting-started/first-pipeline', title: 'First Pipeline Walkthrough' },
    ],
  },
  {
    id: 'projects-dashboard',
    title: '2. Projects & Dashboard',
    children: [
      { id: 'projects-dashboard/creating', title: 'Creating Projects' },
      { id: 'projects-dashboard/lifecycle', title: 'Project Lifecycle' },
      { id: 'projects-dashboard/unassigned-runs', title: 'Unassigned Runs' },
    ],
  },
  {
    id: 'pipeline-editor',
    title: '3. Pipeline Editor',
    children: [
      { id: 'pipeline-editor/canvas', title: 'Canvas Basics' },
      { id: 'pipeline-editor/block-library', title: 'Block Library' },
      { id: 'pipeline-editor/config', title: 'Block Configuration' },
      { id: 'pipeline-editor/templates', title: 'Pipeline Templates' },
      { id: 'pipeline-editor/validation', title: 'Pipeline Validation' },
      { id: 'pipeline-editor/running', title: 'Running Pipelines' },
      { id: 'pipeline-editor/rerun-from-node', title: 'Re-Run from Node' },
      { id: 'pipeline-editor/sweeps', title: 'Parameter Sweeps' },
      { id: 'pipeline-editor/annotations', title: 'Sticky Notes & Groups' },
      { id: 'pipeline-editor/command-palette', title: 'Command Palette' },
    ],
  },
  {
    id: 'blocks-reference',
    title: '4. Blocks In Depth',
    children: [
      { id: 'blocks-reference/anatomy', title: 'Block Anatomy' },
      { id: 'blocks-reference/categories', title: 'Categories Reference' },
      { id: 'blocks-reference/special', title: 'Special Blocks' },
      { id: 'blocks-reference/validation', title: 'Validation & Errors' },
      { id: 'blocks-reference/custom', title: 'Creating Custom Blocks' },
    ],
  },
  {
    id: 'datasets-data',
    title: '5. Datasets & Data',
    children: [
      { id: 'datasets-data/formats', title: 'Supported Formats' },
      { id: 'datasets-data/preview', title: 'Registering & Preview' },
      { id: 'datasets-data/scanner', title: 'File Scanner' },
      { id: 'datasets-data/snapshots', title: 'Snapshots & Versioning' },
      { id: 'datasets-data/templates', title: 'Re-Architecture Templates' },
    ],
  },
  {
    id: 'block-workshop',
    title: '6. Block Workshop',
    children: [
      { id: 'block-workshop/creating', title: 'Creating a Block' },
      { id: 'block-workshop/code', title: 'Writing Block Code' },
      { id: 'block-workshop/testing', title: 'Testing & Validation' },
      { id: 'block-workshop/deployment', title: 'Saving & Deployment' },
    ],
  },
  {
    id: 'execution-monitoring',
    title: '7. Execution & Monitoring',
    children: [
      { id: 'execution-monitoring/engine', title: 'Execution Engine' },
      { id: 'execution-monitoring/monitor', title: 'Monitor View' },
      { id: 'execution-monitoring/sse', title: 'SSE Connection' },
      { id: 'execution-monitoring/logging', title: 'Structured Logging' },
    ],
  },
  {
    id: 'results-analysis',
    title: '8. Results & Analysis',
    children: [
      { id: 'results-analysis/results-view', title: 'Results View' },
      { id: 'results-analysis/checkpoints', title: 'Checkpoint Timeline' },
      { id: 'results-analysis/sweep-heatmap', title: 'Sweep Heatmap' },
      { id: 'results-analysis/model-diff', title: 'Model Diff Visualization' },
      { id: 'results-analysis/significance', title: 'Significance Report' },
      { id: 'results-analysis/provenance', title: 'Run Comparison & Provenance' },
      { id: 'results-analysis/structured-export', title: 'Structured Export' },
    ],
  },
  {
    id: 'export-connectors',
    title: '9. Export Connectors',
    children: [
      { id: 'export-connectors/overview', title: 'Overview' },
      { id: 'export-connectors/wandb', title: 'Weights & Biases' },
      { id: 'export-connectors/huggingface', title: 'HuggingFace Hub' },
      { id: 'export-connectors/jupyter', title: 'Jupyter Notebook' },
      { id: 'export-connectors/api', title: 'Connectors API' },
    ],
  },
  {
    id: 'plugin-system',
    title: '10. Plugin System',
    children: [
      { id: 'plugin-system/overview', title: 'Overview' },
      { id: 'plugin-system/installing', title: 'Installing Plugins' },
      { id: 'plugin-system/permissions', title: 'Plugin Permissions' },
      { id: 'plugin-system/managing', title: 'Managing Plugins' },
      { id: 'plugin-system/creating', title: 'Creating Plugins' },
      { id: 'plugin-system/wandb-plugin', title: 'W&B Monitor Plugin' },
    ],
  },
  { id: 'keyboard-shortcuts', title: '11. Keyboard Shortcuts' },
  {
    id: 'cli-tools',
    title: '12. CLI Tools',
    children: [
      { id: 'cli-tools/test-runner', title: 'Block Test Runner' },
      { id: 'cli-tools/scaffold', title: 'Block Scaffold' },
      { id: 'cli-tools/codegen', title: 'Registry Codegen' },
      { id: 'cli-tools/plugin-manager', title: 'Plugin Manager' },
      { id: 'cli-tools/launch', title: 'Launch Script' },
      { id: 'cli-tools/validator-api', title: 'Validator API' },
    ],
  },
  {
    id: 'settings-config',
    title: '13. Settings & Configuration',
    children: [
      { id: 'settings-config/appearance', title: 'Appearance' },
      { id: 'settings-config/llm-providers', title: 'LLM Providers' },
      { id: 'settings-config/ui-mode', title: 'UI Mode' },
      { id: 'settings-config/feature-flags', title: 'Feature Flags' },
      { id: 'settings-config/data-location', title: 'Data Location' },
    ],
  },
  { id: 'troubleshooting', title: '14. Troubleshooting' },
  { id: 'faq', title: '15. FAQ' },
  { id: 'machine-profile', title: '16. Machine Profile' },
]

/* ------------------------------------------------------------------ */
/*  Search index                                                       */
/* ------------------------------------------------------------------ */

const SEARCH_SECTIONS: SearchableSection[] = [
  { id: 'getting-started', title: '1. Getting Started', text: GETTING_STARTED_TEXT },
  { id: 'projects-dashboard', title: '2. Projects & Dashboard', text: PROJECTS_DASHBOARD_TEXT },
  { id: 'pipeline-editor', title: '3. Pipeline Editor', text: PIPELINE_EDITOR_TEXT },
  { id: 'blocks-reference', title: '4. Blocks In Depth', text: BLOCKS_REFERENCE_TEXT },
  { id: 'datasets-data', title: '5. Datasets & Data', text: DATASETS_DATA_TEXT },
  { id: 'block-workshop', title: '6. Block Workshop', text: BLOCK_WORKSHOP_TEXT },
  { id: 'execution-monitoring', title: '7. Execution & Monitoring', text: EXECUTION_MONITORING_TEXT },
  { id: 'results-analysis', title: '8. Results & Analysis', text: RESULTS_ANALYSIS_TEXT },
  { id: 'export-connectors', title: '9. Export Connectors', text: EXPORT_CONNECTORS_TEXT },
  { id: 'plugin-system', title: '10. Plugin System', text: PLUGIN_SYSTEM_TEXT },
  { id: 'keyboard-shortcuts', title: '11. Keyboard Shortcuts', text: KEYBOARD_SHORTCUTS_TEXT },
  { id: 'cli-tools', title: '12. CLI Tools', text: CLI_TOOLS_TEXT },
  { id: 'settings-config', title: '13. Settings & Configuration', text: SETTINGS_CONFIG_TEXT },
  { id: 'troubleshooting', title: '14. Troubleshooting', text: TROUBLESHOOTING_TEXT },
  { id: 'faq', title: '15. FAQ', text: FAQ_TEXT },
  { id: 'machine-profile', title: '16. Machine Profile', text: 'Machine Profile. Shows your hardware profile including CPU, memory, GPU, and accelerators. Lists blocks that may not run on your current hardware based on estimated resource requirements.' },
]

/* ------------------------------------------------------------------ */
/*  Machine Profile (kept inline as it uses hooks)                     */
/* ------------------------------------------------------------------ */

const MachineProfile = memo(function MachineProfile() {
  const { profile, loading: fetching, fetchHardware } = useHardwareStore()

  useEffect(() => {
    if (!profile && !fetching) fetchHardware()
  }, [profile, fetching, fetchHardware])

  // Derive hardware spec (safe even when profile is null)
  const gpu0 = profile ? (Array.isArray(profile.gpu) ? profile.gpu[0] : profile.gpu) : null
  const hw: HardwareSpec = useMemo(() => ({
    ramGB: profile ? Math.round(profile.ram.total_gb) : 0,
    gpuVramGB: gpu0 ? Math.round(gpu0.vram_gb ?? 0) : 0,
    gpuType: (gpu0?.type as HardwareSpec['gpuType']) ?? 'cpu',
    cpuCores: profile?.cpu.cores ?? 0,
  }), [gpu0, profile])

  // Memoize expensive infeasible block computation — must be called before early returns
  const infeasibleBlocks = useMemo(() => {
    if (!profile) return []
    const result: { name: string; reason: string }[] = []
    for (const block of getAllBlocks()) {
      const fakeNode = {
        id: block.type,
        type: 'blockNode',
        position: { x: 0, y: 0 },
        data: { type: block.type, config: block.defaultConfig ?? {} },
      }
      try {
        const est = estimatePipeline([fakeNode as any], hw)
        if (!est.feasible) {
          result.push({
            name: block.name,
            reason: est.blockEstimates[0]?.warnings[0] || 'Exceeds capacity',
          })
        }
      } catch {
        // Skip blocks that can't be estimated
      }
    }
    return result
  }, [hw, profile])

  const card: React.CSSProperties = {
    padding: 20,
    background: T.surface2,
    border: `1px solid ${T.borderHi}`,
    marginBottom: 14,
  }

  const label: React.CSSProperties = {
    fontFamily: F,
    fontSize: FS.xxs,
    color: T.dim,
    letterSpacing: '0.1em',
    textTransform: 'uppercase',
  }

  const val: React.CSSProperties = {
    fontFamily: F,
    fontSize: FS.sm,
    color: T.text,
    fontWeight: 600,
    marginTop: 4,
  }

  if (fetching) {
    return (
      <div style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, padding: 20 }}>
        Detecting hardware...
      </div>
    )
  }

  if (!profile) {
    return (
      <div style={card}>
        <div style={{ fontFamily: F, fontSize: FS.sm, color: T.dim }}>
          Hardware profile not available. Ensure the backend is running.
        </div>
      </div>
    )
  }

  // Build accelerator list from the object
  const accelObj = profile.accelerators ?? {}
  const accelList = typeof accelObj === 'object' && !Array.isArray(accelObj)
    ? Object.entries(accelObj).filter(([, v]) => v).map(([k]) => k)
    : Array.isArray(accelObj) ? accelObj : []

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
        <div style={card}>
          <div style={label}>CPU</div>
          <div style={val}>{profile.cpu.brand}</div>
          <div style={{ ...val, fontWeight: 400, fontSize: FS.xs, color: T.sec }}>
            {profile.cpu.cores} cores
          </div>
        </div>
        <div style={card}>
          <div style={label}>Memory</div>
          <div style={val}>{profile.ram.total_gb.toFixed(1)} GB</div>
          <div style={{ ...val, fontWeight: 400, fontSize: FS.xs, color: T.sec }}>
            {profile.ram.available_gb.toFixed(1)} GB available
          </div>
        </div>
        <div style={card}>
          <div style={label}>GPU</div>
          <div style={val}>{gpu0?.name ?? 'None detected'}</div>
          {gpu0 && (
            <div style={{ ...val, fontWeight: 400, fontSize: FS.xs, color: T.sec }}>
              {(gpu0.vram_gb ?? 0).toFixed(1)} GB VRAM &middot; {gpu0.type}
            </div>
          )}
        </div>
        <div style={card}>
          <div style={label}>Accelerators</div>
          <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {accelList.map((a) => (
              <span
                key={a}
                style={{
                  fontFamily: F,
                  fontSize: 10,
                  fontWeight: 700,
                  padding: '3px 8px',
                  background: `${T.cyan}20`,
                  color: T.cyan,
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                }}
              >
                {a}
              </span>
            ))}
            {accelList.length === 0 && (
              <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>None</span>
            )}
          </div>
        </div>
      </div>

      {infeasibleBlocks.length > 0 && (
        <div style={card}>
          <div style={label}>Blocks That May Not Run On This Hardware</div>
          <div
            style={{
              marginTop: 8,
              fontFamily: F,
              fontSize: FS.xs,
              color: T.sec,
              lineHeight: 1.6,
            }}
          >
            {infeasibleBlocks.map((b) => `${b.name} (${b.reason})`).join(', ')}
          </div>
        </div>
      )}
    </div>
  )
})

/* ------------------------------------------------------------------ */
/*  Main Help View                                                     */
/* ------------------------------------------------------------------ */

export default function HelpView() {
  const [activeSection, setActiveSection] = useState('getting-started')
  const [showAssistant, setShowAssistant] = useState(false)
  const [showMobileSidebar, setShowMobileSidebar] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)
  const uiMode = useSettingsStore((s) => s.uiMode)

  // Navigate to a section by scrolling it into view
  const navigateToSection = useCallback((id: string) => {
    setActiveSection(id.split('/')[0])
    setShowMobileSidebar(false)

    // Small delay for state update, then scroll
    requestAnimationFrame(() => {
      const el = document.getElementById(id)
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    })
  }, [])

  // Track scroll position to update active section
  useEffect(() => {
    const container = contentRef.current
    if (!container) return

    const allIds = TOC.flatMap((s) => [s.id, ...(s.children?.map((c) => c.id) ?? [])])

    const handleScroll = () => {
      for (let i = allIds.length - 1; i >= 0; i--) {
        const el = document.getElementById(allIds[i])
        if (el) {
          const rect = el.getBoundingClientRect()
          if (rect.top <= 120) {
            const topSection = allIds[i].split('/')[0]
            setActiveSection(topSection)
            return
          }
        }
      }
    }

    container.addEventListener('scroll', handleScroll, { passive: true })
    return () => container.removeEventListener('scroll', handleScroll)
  }, [])

  // Compute current context text for LLM assistant
  const currentContextText = useMemo(() => {
    const section = SEARCH_SECTIONS.find((s) => s.id === activeSection)
    return section?.text ?? SEARCH_SECTIONS.map((s) => s.text).join('\n\n').slice(0, 6000)
  }, [activeSection])

  const currentContextTitle = useMemo(() => {
    const section = SEARCH_SECTIONS.find((s) => s.id === activeSection)
    return section?.title ?? 'Blueprint Documentation'
  }, [activeSection])

  // Filter TOC for Simple mode
  const filteredToc = useMemo(() => {
    if (uiMode === 'professional') return TOC
    // In simple mode, hide some advanced sections
    const hiddenIds = new Set(['plugin-system', 'export-connectors'])
    return TOC.filter((s) => !hiddenIds.has(s.id))
  }, [uiMode])

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden', background: T.bg }}>
      {/* Mobile sidebar overlay */}
      {showMobileSidebar && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 50,
            background: 'rgba(0,0,0,0.5)',
          }}
          onClick={() => setShowMobileSidebar(false)}
        >
          <div onClick={(e) => e.stopPropagation()}>
            <HelpSidebar
              sections={filteredToc}
              activeId={activeSection}
              onNavigate={navigateToSection}
            />
          </div>
        </div>
      )}

      {/* Desktop sidebar */}
      <div style={{ display: 'flex', flexDirection: 'column', minWidth: 260 }}>
        <HelpSidebar
          sections={filteredToc}
          activeId={activeSection}
          onNavigate={navigateToSection}
        />
      </div>

      {/* Main content area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Top bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: '12px 24px',
            borderBottom: `1px solid ${T.border}`,
            background: T.surface1,
          }}
        >
          {/* Mobile menu button */}
          <button
            onClick={() => setShowMobileSidebar(true)}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: 4,
              display: 'none', // visible only on small screens via media query workaround
            }}
          >
            <Menu size={18} color={T.text} />
          </button>

          <BookOpen size={18} color={T.cyan} />
          <span
            style={{
              fontFamily: FD,
              fontSize: FS.lg,
              fontWeight: 800,
              color: T.text,
            }}
          >
            Blueprint Documentation
          </span>

          <div style={{ flex: 1, maxWidth: 400, marginLeft: 16 }}>
            <HelpSearch sections={SEARCH_SECTIONS} onNavigate={navigateToSection} />
          </div>

          <div style={{ flex: 1 }} />

          {/* AI Assistant toggle */}
          <button
            onClick={() => setShowAssistant(!showAssistant)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '6px 14px',
              background: showAssistant ? T.cyan : T.surface2,
              border: `1px solid ${showAssistant ? T.cyan : T.border}`,
              color: showAssistant ? '#fff' : T.sec,
              fontFamily: F,
              fontSize: FS.xs,
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <Sparkles size={14} />
            AI Assistant
          </button>
        </div>

        {/* Content + Assistant side by side */}
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          {/* Scrollable content */}
          <motion.div
            ref={contentRef}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '24px 32px 80px 32px',
              maxWidth: 900,
            }}
          >
            <GettingStarted />
            <ProjectsDashboard />
            <PipelineEditor />
            <BlocksReference />
            <DatasetsData />
            <BlockWorkshop />
            <ExecutionMonitoring />
            <ResultsAnalysis />

            {/* These sections hidden in Simple mode */}
            {uiMode === 'professional' && (
              <>
                <ExportConnectors />
                <PluginSystem />
              </>
            )}

            <KeyboardShortcuts />
            <CLITools />
            <SettingsConfig />
            <Troubleshooting />
            <FAQ />

            {/* Machine Profile */}
            <div style={{ scrollMarginTop: 24 }} id="machine-profile">
              <div
                style={{
                  fontFamily: FD,
                  fontSize: FS.xl,
                  fontWeight: 800,
                  color: T.text,
                  marginTop: 48,
                  marginBottom: 20,
                  lineHeight: 1.3,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <Cpu size={22} color={T.cyan} />
                Machine Profile
              </div>
              <MachineProfile />
            </div>

            {/* Footer */}
            <div
              style={{
                marginTop: 48,
                padding: '24px 0',
                borderTop: `1px solid ${T.border}`,
                fontFamily: F,
                fontSize: FS.xs,
                color: T.dim,
                textAlign: 'center',
                lineHeight: 1.6,
              }}
            >
              Blueprint by Specific Labs &middot; {getAllBlocks().length}+ blocks &middot; Local-first
              ML workbench
              <br />
              For issues and feedback:{' '}
              <span style={{ color: T.cyan }}>
                github.com/santiagoaraoz2001-sketch/blueprint
              </span>
            </div>
          </motion.div>

          {/* AI Assistant panel */}
          {showAssistant && (
            <HelpAssistant
              contextText={currentContextText}
              contextTitle={currentContextTitle}
              onClose={() => setShowAssistant(false)}
            />
          )}
        </div>
      </div>
    </div>
  )
}
