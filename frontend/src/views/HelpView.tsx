import { useState, useMemo, useEffect } from 'react'
import { motion } from 'framer-motion'
import { T, F, FD, FS, CATEGORY_COLORS } from '@/lib/design-tokens'
import { BLOCK_REGISTRY, type BlockDefinition } from '@/lib/block-registry'
import { useHardwareStore } from '@/stores/hardwareStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { estimatePipeline, type HardwareSpec } from '@/lib/pipeline-estimator'
import {
  Search,
  BookOpen,
  Blocks,
  Keyboard,
  HelpCircle,
  AlertTriangle,
  Terminal,
  ChevronDown,
  ChevronRight,
  Layout,
  GitBranch,
  BarChart3,
  Database,
  Package,
  FileText,
  Settings,
  Cpu,
} from 'lucide-react'

/* ------------------------------------------------------------------ */
/*  Shared styles                                                     */
/* ------------------------------------------------------------------ */

const sectionHeader: React.CSSProperties = {
  fontFamily: F,
  fontSize: FS.xs,
  fontWeight: 900,
  letterSpacing: '0.14em',
  textTransform: 'uppercase',
  color: T.dim,
  margin: 0,
  marginBottom: 12,
}

const cardStyle: React.CSSProperties = {
  padding: 20,
  background: T.surface2,
  border: `1px solid ${T.borderHi}`,
  marginBottom: 14,
  position: 'relative',
}

const labelStyle: React.CSSProperties = {
  fontFamily: F,
  fontSize: FS.xxs,
  color: T.dim,
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
}

const bodyText: React.CSSProperties = {
  fontFamily: F,
  fontSize: FS.sm,
  color: T.sec,
  lineHeight: 1.6,
}

/* ------------------------------------------------------------------ */
/*  Data: Keyboard Shortcuts                                           */
/* ------------------------------------------------------------------ */

const SHORTCUTS = [
  { keys: ['Cmd', 'K'], action: 'Open command palette' },
  { keys: ['Cmd', 'S'], action: 'Save current pipeline' },
  { keys: ['Cmd', 'Z'], action: 'Undo' },
  { keys: ['Cmd', 'Shift', 'Z'], action: 'Redo' },
  { keys: ['Cmd', 'E'], action: 'Export pipeline' },
  { keys: ['Cmd', 'I'], action: 'Import pipeline' },
  { keys: ['Delete'], action: 'Delete selected node/edge' },
  { keys: ['Escape'], action: 'Deselect / close panel' },
  { keys: ['Space'], action: 'Pan canvas (hold + drag)' },
  { keys: ['Cmd', '+'], action: 'Zoom in' },
  { keys: ['Cmd', '-'], action: 'Zoom out' },
  { keys: ['Cmd', '0'], action: 'Fit to screen' },
]

/* ------------------------------------------------------------------ */
/*  Data: FAQ                                                          */
/* ------------------------------------------------------------------ */

const FAQ = [
  {
    q: 'What is Blueprint?',
    a: 'Blueprint is a local-first ML experiment workbench by Specific Labs. It lets you visually build, run, and analyze machine learning pipelines using a drag-and-drop interface with 100+ block types across 11 categories.',
  },
  {
    q: 'Do I need an internet connection?',
    a: 'No. Blueprint runs entirely on your machine. You can use local models via Ollama or MLX. Internet is only needed for downloading HuggingFace datasets or using cloud LLM APIs.',
  },
  {
    q: 'Which ML frameworks are supported?',
    a: 'Blueprint supports PyTorch, HuggingFace Transformers, MLX (Apple Silicon), and Ollama for local LLM inference. Model blocks auto-detect available frameworks.',
  },
  {
    q: 'How do I add a custom block?',
    a: 'Create a new folder under backend/blocks/{category}/{block_name}/ with a block.yaml definition and run.py execution script. Then register it in frontend/src/lib/block-registry.ts.',
  },
  {
    q: 'Where is my data stored?',
    a: 'All data is stored locally in ~/.specific-labs/ including the SQLite database, model artifacts, and pipeline definitions. Nothing is sent to external servers.',
  },
  {
    q: 'Can I use GPU acceleration?',
    a: 'Yes. On Apple Silicon Macs, Blueprint auto-detects Metal/MPS support. On NVIDIA systems, CUDA is detected automatically. Check Settings for hardware capabilities.',
  },
  {
    q: 'How do I connect Ollama?',
    a: 'Install Ollama (ollama.ai), start it, then go to Settings > LLM Providers and select Ollama. The default endpoint http://localhost:11434 should auto-connect.',
  },
  {
    q: 'Can I export my results?',
    a: 'Yes. The Results view shows metrics from all pipeline runs. You can send tables and charts to the Paper tool, or export pipeline definitions as JSON.',
  },
  {
    q: 'How do pipelines execute?',
    a: 'Pipelines execute in topological order — blocks with no dependencies run first. Each block receives inputs from connected upstream blocks and produces outputs for downstream blocks.',
  },
  {
    q: 'What file formats are supported for data loading?',
    a: 'CSV, JSONL, Parquet, and plain text files. You can also load directly from HuggingFace Hub using the HuggingFace Loader block.',
  },
]

/* ------------------------------------------------------------------ */
/*  Data: Page Tutorials                                               */
/* ------------------------------------------------------------------ */

const PAGE_TUTORIALS = [
  {
    icon: Layout,
    title: 'Dashboard (Projects)',
    description: 'The main entry point. Create and manage ML projects, each containing pipelines and runs.',
    steps: [
      'Click "NEW PROJECT" to create a project with a name and description',
      'Each project acts as a workspace for related experiments',
      'Click a project card to select it — all other views will filter to that project',
      'The project overview shows recent runs, active pipelines, and quick stats',
    ],
  },
  {
    icon: GitBranch,
    title: 'Pipeline Editor',
    description: 'The visual pipeline builder. Drag blocks onto the canvas and connect them to create ML workflows.',
    steps: [
      'Open the block library panel on the left to browse available blocks by category',
      'Drag a block onto the canvas to add it to your pipeline',
      'Connect blocks by dragging from an output port (bottom) to an input port (top)',
      'Click a block to open its configuration panel — set parameters, file paths, model names etc.',
      'Ports are color-coded by data type: green=dataset, pink=text, violet=model, cyan=config, amber=metrics, teal=embedding, red=artifact, sky=agent',
      'Use the toolbar to Save, Run, Validate, or Test your pipeline',
      'The minimap in the corner helps navigate large pipelines',
    ],
  },
  {
    icon: BarChart3,
    title: 'Results',
    description: 'View and compare metrics from all your pipeline runs.',
    steps: [
      'Each pipeline run creates a results entry with timing, status, and output metrics',
      'Click a run to expand its details — see per-block outputs, logs, and metrics',
      'Use the comparison view to overlay metrics from multiple runs',
      'Charts auto-generate for numeric metrics — hover for exact values',
      'Send any table or chart to the Paper tool with the "Add to Paper" button',
    ],
  },
  {
    icon: Database,
    title: 'Datasets',
    description: 'Browse and manage datasets used in your pipelines.',
    steps: [
      'Datasets are auto-detected from pipeline outputs and local file loaders',
      'Preview dataset contents — first 100 rows shown in a scrollable table',
      'Filter and search across all available datasets',
      'Click "Use in Pipeline" to quickly add a dataset reference to your active pipeline',
    ],
  },
  {
    icon: Blocks,
    title: 'Blocks (Marketplace)',
    description: 'Browse all available pipeline blocks organized by category.',
    steps: [
      'Blocks are grouped into 11 categories: Sources, Transforms, Model Ops, Inference, Training, Evaluation, Vectors, Flow Control, Agents, Gates, and Endpoints',
      'Each block card shows its name, description, and input/output port types',
      'Click a block to see detailed documentation including all config fields',
      'Drag a block directly from here to add it to your active pipeline',
    ],
  },
  {
    icon: Package,
    title: 'Models (Model Hub)',
    description: 'Manage local ML models detected on your system.',
    steps: [
      'Blueprint auto-scans common model directories (~/.cache/huggingface, ~/.ollama, etc.)',
      'Each model card shows name, size, framework, and compatibility info',
      'Models are auto-detected when Ollama or MLX is running',
      'Click "Use in Pipeline" to add a model reference block to your pipeline',
    ],
  },
  {
    icon: FileText,
    title: 'Paper',
    description: 'Write research papers with sections, tables, and charts from your experiments.',
    steps: [
      'Create a new paper with a title and select a template (ICML, NeurIPS, Custom, etc.)',
      'Add sections using the section panel — drag to reorder',
      'Each section has a rich text editor with Markdown support',
      'Insert tables from Results by clicking "Add to Paper" on any metrics table',
      'Insert charts from Results by clicking "Add to Paper" on any chart',
      'Export your paper as Markdown for further editing in LaTeX or other tools',
    ],
  },
  {
    icon: Settings,
    title: 'Settings',
    description: 'Configure appearance, LLM providers, and application preferences.',
    steps: [
      'Choose between Dark and Light themes with live preview cards',
      'Select your preferred code font from 4 options',
      'Adjust font size: Compact, Default, Comfortable, or Large',
      'Configure LLM provider: Ollama, MLX, OpenAI, Anthropic, or Manual',
      'Set API keys for cloud providers (stored locally, never transmitted)',
      'Toggle Demo Mode to explore with sample data',
      'Adjust auto-save interval or disable it',
    ],
  },
  {
    icon: Cpu,
    title: 'System & Hardware',
    description: 'Blueprint auto-detects your hardware capabilities for optimal performance.',
    steps: [
      'GPU detection: Metal (Apple Silicon), CUDA (NVIDIA), or CPU-only',
      'Memory analysis determines which models can run locally',
      'Framework detection: PyTorch, MLX, Transformers, Ollama',
      'System info is available in Settings and used by blocks to optimize execution',
    ],
  },
]

/* ------------------------------------------------------------------ */
/*  Data: Troubleshooting                                              */
/* ------------------------------------------------------------------ */

const TROUBLESHOOTING = [
  {
    issue: 'Backend not connecting',
    fix: 'Ensure the backend is running on port 8000. Check terminal for errors. Run: uvicorn backend.main:app --reload --port 8000',
  },
  {
    issue: 'Ollama not detected',
    fix: 'Make sure Ollama is running (ollama serve). Default endpoint is http://localhost:11434. Test with: curl http://localhost:11434/api/tags',
  },
  {
    issue: 'Pipeline execution fails',
    fix: 'Check the run logs in Results view for specific error messages. Common issues: missing model files, incorrect file paths, or missing Python packages.',
  },
  {
    issue: '"Module not found" during block execution',
    fix: 'Install the required Python package: pip install <package_name>. Common: transformers, torch, datasets, mlx, mlx-lm.',
  },
  {
    issue: 'Models not appearing in Model Hub',
    fix: 'Models are scanned from standard locations. Ensure models are in ~/.cache/huggingface/ or ~/.ollama/. Click "Refresh" to re-scan.',
  },
  {
    issue: 'Electron app shows blank screen',
    fix: 'The backend may not have started. Check the terminal output. Try restarting the app. In dev mode, ensure both Vite and the backend server are running.',
  },
  {
    issue: 'Out of memory during training',
    fix: 'Reduce batch_size in the training block config. Use gradient accumulation steps. For Apple Silicon, ensure MLX is used instead of PyTorch for memory efficiency.',
  },
  {
    issue: 'Slow pipeline execution',
    fix: 'Check Settings > Hardware for GPU availability. Ensure models are loaded on GPU (Metal/CUDA). Reduce dataset size with max_samples parameter.',
  },
]

/* ------------------------------------------------------------------ */
/*  Data: CLI Tools                                                    */
/* ------------------------------------------------------------------ */

const CLI_TOOLS = [
  {
    name: 'Block Test Runner',
    command: 'python -m backend.tests.block_runner <block_dir>',
    aliases: [
      'python -m backend.tests.block_runner',
      'python -m backend.tests',
    ],
    description:
      'Test a single block in isolation with fixture data — no pipeline setup needed. Validates config, runs the block with auto-generated inputs, and reports outputs, metrics, timing, and memory usage.',
    options: [
      { flag: '--fixture small|medium|realistic', desc: 'Use a named fixture dataset (10 / 1,000 / 10,000 rows)' },
      { flag: '--fixture-path PATH', desc: 'Use a custom JSONL file as the fixture dataset' },
      { flag: '--config key=value ...', desc: 'Override block config values (repeatable)' },
      { flag: '--verbose, -v', desc: 'Show block log messages and captured stdout' },
      { flag: '--timeout SECONDS', desc: 'Maximum execution time (kills the block if exceeded)' },
    ],
    examples: [
      'python -m backend.tests.block_runner blocks/data/text_input --config text_value="Hello"',
      'python -m backend.tests.block_runner blocks/training/ballast_training --fixture small --config model_name=gpt2',
      'python -m backend.tests.block_runner blocks/training/lora_finetuning --fixture-path my_data.jsonl -v',
    ],
  },
  {
    name: 'Pipeline Validator',
    command: 'POST /api/pipelines/{pipeline_id}/validate',
    aliases: ['Validate button in Pipeline Editor toolbar'],
    description:
      'Check a pipeline for structural errors, missing config, type mismatches, hardware feasibility, and performance estimates — without running any blocks. Available via the Validate button (shield icon) in the Pipeline Editor or the REST API.',
    options: [
      { flag: 'Structure', desc: 'Empty pipeline, duplicate IDs, cycles, disconnected blocks' },
      { flag: 'Configuration', desc: 'Missing required inputs, empty critical config fields' },
      { flag: 'Compatibility', desc: 'Port type mismatches, self-loops, invalid edge references' },
      { flag: 'Hardware', desc: 'Memory feasibility, GPU requirements, per-block resource checks' },
      { flag: 'Performance', desc: 'Runtime estimates, bottleneck detection' },
    ],
    examples: [
      'Click the amber VALIDATE button (shield icon) in the Pipeline Editor toolbar',
      'The validation panel shows a health score, categorized issues, and per-block suggestions',
      'Click any issue to focus the affected block on the canvas',
    ],
  },
  {
    name: 'Test Runner (pytest)',
    command: 'python -m pytest backend/tests/test_block_validation.py -v',
    aliases: ['pytest backend/tests/'],
    description:
      'Run the validation framework unit tests — covers the exception hierarchy, config type checking, default application, bounds enforcement, select validation, fixture integrity, and block runner integration.',
    options: [
      { flag: '-v', desc: 'Verbose output showing each test name and status' },
      { flag: '-k PATTERN', desc: 'Run only tests matching a name pattern' },
      { flag: '--tb=short', desc: 'Show shorter tracebacks on failure' },
    ],
    examples: [
      'python -m pytest backend/tests/test_block_validation.py -v',
      'python -m pytest backend/tests/test_block_validation.py -k "test_integer" -v',
      'python -m pytest backend/tests/ -v --tb=short',
    ],
  },
]

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

function Collapsible({
  title,
  defaultOpen = false,
  accent,
  children,
}: {
  title: string
  defaultOpen?: boolean
  accent?: string
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div style={{ ...cardStyle, padding: 0 }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          width: '100%',
          padding: '10px 14px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          color: accent || T.text,
          fontFamily: F,
          fontSize: FS.sm,
          fontWeight: 700,
          letterSpacing: '0.06em',
          textAlign: 'left',
        }}
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        {title}
      </button>
      {open && <div style={{ padding: '0 14px 12px' }}>{children}</div>}
    </div>
  )
}

function BlockDoc({ block }: { block: BlockDefinition }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <div
          style={{
            width: 8,
            height: 8,
            background: block.accent,
            flexShrink: 0,
          }}
        />
        <span style={{ fontFamily: F, fontSize: FS.sm, fontWeight: 700, color: T.text }}>
          {block.name}
        </span>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          {block.type}
        </span>
      </div>
      <p style={{ ...bodyText, margin: '0 0 4px 14px', fontSize: FS.xxs }}>
        {block.description}
      </p>

      {/* I/O table */}
      <div style={{ marginLeft: 14, display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        {block.inputs.length > 0 && (
          <div>
            <span style={{ ...labelStyle, fontSize: 4.5 }}>INPUTS</span>
            {block.inputs.map((p) => (
              <div key={p.id} style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
                <span style={{ color: T.dim }}>{p.label}</span>{' '}
                <span style={{ color: block.accent, fontWeight: 700 }}>{p.dataType}</span>
                {!p.required && <span style={{ color: T.dim }}> (opt)</span>}
              </div>
            ))}
          </div>
        )}
        {block.outputs.length > 0 && (
          <div>
            <span style={{ ...labelStyle, fontSize: 4.5 }}>OUTPUTS</span>
            {block.outputs.map((p) => (
              <div key={p.id} style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
                <span style={{ color: T.dim }}>{p.label}</span>{' '}
                <span style={{ color: block.accent, fontWeight: 700 }}>{p.dataType}</span>
              </div>
            ))}
          </div>
        )}
        {block.configFields.length > 0 && (
          <div>
            <span style={{ ...labelStyle, fontSize: 4.5 }}>CONFIG</span>
            {block.configFields.slice(0, 5).map((c) => (
              <div key={c.name} style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
                <span style={{ color: T.dim }}>{c.label || c.name}</span>{' '}
                <span style={{ color: T.dim, opacity: 0.6 }}>({c.type})</span>
              </div>
            ))}
            {block.configFields.length > 5 && (
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                +{block.configFields.length - 5} more
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function KeyBadge({ k }: { k: string }) {
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 5px',
        background: T.surface4,
        border: `1px solid ${T.borderHi}`,
        fontFamily: F,
        fontSize: FS.xxs,
        fontWeight: 700,
        color: T.sec,
        letterSpacing: '0.04em',
        minWidth: 18,
        textAlign: 'center',
      }}
    >
      {k}
    </span>
  )
}

/* ------------------------------------------------------------------ */
/*  Tab navigation                                                     */
/* ------------------------------------------------------------------ */

type HelpTab = 'general' | 'modules' | 'shortcuts' | 'faq' | 'cli' | 'troubleshooting' | 'machine'

const TABS: { id: HelpTab; label: string; icon: React.ComponentType<any> }[] = [
  { id: 'general', label: 'GUIDE', icon: BookOpen },
  { id: 'modules', label: 'MODULES', icon: Blocks },
  { id: 'shortcuts', label: 'SHORTCUTS', icon: Keyboard },
  { id: 'faq', label: 'FAQ', icon: HelpCircle },
  { id: 'cli', label: 'CLI TOOLS', icon: Terminal },
  { id: 'troubleshooting', label: 'TROUBLESHOOT', icon: AlertTriangle },
  { id: 'machine', label: 'MACHINE', icon: Cpu },
]

/* ------------------------------------------------------------------ */
/*  Machine Tab                                                        */
/* ------------------------------------------------------------------ */

function MachineTab() {
  const profile = useHardwareStore((s) => s.profile)
  const fetchHardware = useHardwareStore((s) => s.fetchHardware)
  const settingsHw = useSettingsStore((s) => s.hardware)

  useEffect(() => {
    if (!profile) fetchHardware()
  }, [profile, fetchHardware])

  // Build HardwareSpec for feasibility checks
  const hw: HardwareSpec | undefined = useMemo(() => {
    if (profile) {
      return {
        ramGB: profile.ram.total_gb,
        gpuVramGB: profile.gpu[0]?.vram_gb ?? 0,
        gpuType: (profile.gpu[0]?.type as HardwareSpec['gpuType']) ?? 'cpu',
        cpuCores: profile.cpu.cores,
      }
    }
    if (settingsHw) {
      return {
        ramGB: settingsHw.usable_memory_gb || 18,
        gpuVramGB: settingsHw.max_vram_gb || 0,
        gpuType: settingsHw.gpu_backend === 'metal' ? 'metal'
          : settingsHw.gpu_backend === 'cuda' ? 'cuda'
          : settingsHw.gpu_available ? 'metal' : 'cpu',
        cpuCores: 10,
      }
    }
    return undefined
  }, [profile, settingsHw])

  // Find blocks infeasible on this hardware
  const infeasibleBlocks = useMemo(() => {
    if (!hw) return []
    const results: { block: BlockDefinition; reason: string }[] = []
    for (const block of BLOCK_REGISTRY) {
      const fakeNode = {
        id: block.type,
        type: 'blockNode' as const,
        position: { x: 0, y: 0 },
        data: {
          type: block.type,
          label: block.name,
          category: block.category,
          icon: block.icon,
          accent: block.accent,
          config: {},
          status: 'idle' as const,
          progress: 0,
        },
      }
      const est = estimatePipeline([fakeNode], hw)
      if (!est.feasible) {
        results.push({ block, reason: est.blockEstimates[0]?.warnings[0] || 'Exceeds capacity' })
      }
    }
    return results
  }, [hw])

  const gpuLabel = hw?.gpuType === 'metal' ? 'Apple Silicon (Metal)'
    : hw?.gpuType === 'cuda' ? 'NVIDIA (CUDA)'
    : hw?.gpuType === 'rocm' ? 'AMD (ROCm)'
    : 'CPU Only'

  return (
    <div>
      <h2 style={sectionHeader}>HARDWARE PROFILE</h2>

      {/* Hardware overview card */}
      <div style={cardStyle}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <div>
            <span style={labelStyle}>CPU</span>
            <div style={{ fontFamily: F, fontSize: FS.md, color: T.text, fontWeight: 700, marginTop: 4 }}>
              {profile?.cpu.brand || 'Unknown'}
            </div>
            <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 2 }}>
              {hw?.cpuCores || '?'} cores · {profile?.cpu.arch || 'unknown'} arch
            </div>
          </div>
          <div>
            <span style={labelStyle}>GPU</span>
            <div style={{ fontFamily: F, fontSize: FS.md, color: T.text, fontWeight: 700, marginTop: 4 }}>
              {gpuLabel}
            </div>
            <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 2 }}>
              {hw?.gpuVramGB ? `${hw.gpuVramGB} GB VRAM` : 'No dedicated GPU memory'}
            </div>
          </div>
          <div>
            <span style={labelStyle}>MEMORY</span>
            <div style={{ fontFamily: F, fontSize: FS.md, color: T.text, fontWeight: 700, marginTop: 4 }}>
              {hw?.ramGB || '?'} GB RAM
            </div>
            <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 2 }}>
              {profile?.ram.available_gb ? `${profile.ram.available_gb.toFixed(1)} GB available` : ''}
            </div>
          </div>
          <div>
            <span style={labelStyle}>DISK</span>
            <div style={{ fontFamily: F, fontSize: FS.md, color: T.text, fontWeight: 700, marginTop: 4 }}>
              {profile?.disk.free_gb ? `${profile.disk.free_gb.toFixed(0)} GB free` : 'Unknown'}
            </div>
          </div>
        </div>
      </div>

      {/* Accelerators */}
      <div style={cardStyle}>
        <span style={{ ...labelStyle, display: 'block', marginBottom: 8 }}>ACCELERATORS</span>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {['mlx', 'cuda', 'mps', 'coreml'].map((acc) => {
            const available = profile?.accelerators?.[acc as keyof typeof profile.accelerators] ?? false
            return (
              <div
                key={acc}
                style={{
                  padding: '4px 10px',
                  background: available ? `${T.green}14` : T.surface3,
                  border: `1px solid ${available ? `${T.green}40` : T.border}`,
                  borderRadius: 4,
                }}
              >
                <span style={{
                  fontFamily: F,
                  fontSize: FS.xs,
                  fontWeight: 700,
                  color: available ? T.green : T.dim,
                  letterSpacing: '0.08em',
                }}>
                  {acc.toUpperCase()}
                </span>
                <span style={{
                  fontFamily: F,
                  fontSize: FS.xxs,
                  color: available ? T.green : T.dim,
                  marginLeft: 6,
                }}>
                  {available ? 'Available' : 'Not found'}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Recommendations */}
      <h2 style={{ ...sectionHeader, marginTop: 20 }}>RECOMMENDATIONS</h2>
      <div style={cardStyle}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {hw?.gpuType === 'metal' && (
            <div style={{ ...bodyText, display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              <span style={{ color: T.green, fontWeight: 700, flexShrink: 0 }}>•</span>
              <span>Use <strong>MLX</strong> or <strong>Ollama</strong> for local inference — optimized for Apple Silicon unified memory.</span>
            </div>
          )}
          {hw?.gpuType === 'cuda' && (
            <div style={{ ...bodyText, display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              <span style={{ color: T.green, fontWeight: 700, flexShrink: 0 }}>•</span>
              <span>CUDA detected — full GPU acceleration available for training and inference blocks.</span>
            </div>
          )}
          {hw?.gpuType === 'cpu' && (
            <div style={{ ...bodyText, display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              <span style={{ color: T.amber, fontWeight: 700, flexShrink: 0 }}>•</span>
              <span>No GPU detected — training and large model inference will be significantly slower. Consider cloud providers.</span>
            </div>
          )}
          {(hw?.ramGB ?? 0) < 16 && (
            <div style={{ ...bodyText, display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              <span style={{ color: T.amber, fontWeight: 700, flexShrink: 0 }}>•</span>
              <span>Limited RAM ({hw?.ramGB} GB) — use quantized models (4-bit / QLoRA) and small datasets.</span>
            </div>
          )}
          {(hw?.ramGB ?? 0) >= 32 && (
            <div style={{ ...bodyText, display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              <span style={{ color: T.green, fontWeight: 700, flexShrink: 0 }}>•</span>
              <span>Sufficient RAM for most operations including 7B-13B model fine-tuning with LoRA.</span>
            </div>
          )}
          <div style={{ ...bodyText, display: 'flex', gap: 8, alignItems: 'flex-start' }}>
            <span style={{ color: T.cyan, fontWeight: 700, flexShrink: 0 }}>•</span>
            <span>Use the <strong>ANALYZE</strong> button in the pipeline editor to check block feasibility before running.</span>
          </div>
        </div>
      </div>

      {/* Infeasible blocks */}
      {infeasibleBlocks.length > 0 && (
        <>
          <h2 style={{ ...sectionHeader, marginTop: 20 }}>
            BLOCKS EXCEEDING CAPACITY ({infeasibleBlocks.length})
          </h2>
          <div style={cardStyle}>
            {infeasibleBlocks.map(({ block, reason }) => (
              <div
                key={block.type}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '6px 0',
                  borderBottom: `1px solid ${T.border}08`,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{
                    width: 6, height: 6, borderRadius: '50%',
                    background: CATEGORY_COLORS[block.category] || T.dim,
                  }} />
                  <span style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 600 }}>
                    {block.name}
                  </span>
                </div>
                <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.amber }}>
                  {reason}
                </span>
              </div>
            ))}
          </div>
        </>
      )}

      {infeasibleBlocks.length === 0 && hw && (
        <div style={{ ...cardStyle, marginTop: 20, display: 'flex', alignItems: 'center', gap: 8, background: `${T.green}08`, borderColor: `${T.green}30` }}>
          <span style={{ fontFamily: F, fontSize: FS.sm, color: T.green, fontWeight: 700 }}>
            All {BLOCK_REGISTRY.length} blocks are feasible on your hardware
          </span>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

export default function HelpView() {
  const [activeTab, setActiveTab] = useState<HelpTab>('general')
  const [searchQuery, setSearchQuery] = useState('')

  // Group blocks by category
  const blocksByCategory = useMemo(() => {
    const map: Record<string, BlockDefinition[]> = {}
    for (const block of BLOCK_REGISTRY) {
      if (!map[block.category]) map[block.category] = []
      map[block.category].push(block)
    }
    return map
  }, [])

  // Search filtering
  const sq = searchQuery.toLowerCase().trim()

  const filteredFAQ = useMemo(
    () => (sq ? FAQ.filter((f) => f.q.toLowerCase().includes(sq) || f.a.toLowerCase().includes(sq)) : FAQ),
    [sq],
  )

  const filteredBlocks = useMemo(() => {
    if (!sq) return blocksByCategory
    const filtered: Record<string, BlockDefinition[]> = {}
    for (const [cat, blocks] of Object.entries(blocksByCategory)) {
      const matched = blocks.filter(
        (b) =>
          b.name.toLowerCase().includes(sq) ||
          b.description.toLowerCase().includes(sq) ||
          b.type.toLowerCase().includes(sq),
      )
      if (matched.length) filtered[cat] = matched
    }
    return filtered
  }, [sq, blocksByCategory])

  const filteredTroubleshooting = useMemo(
    () =>
      sq
        ? TROUBLESHOOTING.filter(
          (t) => t.issue.toLowerCase().includes(sq) || t.fix.toLowerCase().includes(sq),
        )
        : TROUBLESHOOTING,
    [sq],
  )

  const filteredShortcuts = useMemo(
    () =>
      sq
        ? SHORTCUTS.filter(
          (s) =>
            s.action.toLowerCase().includes(sq) || s.keys.join(' ').toLowerCase().includes(sq),
        )
        : SHORTCUTS,
    [sq],
  )

  const filteredTutorials = useMemo(
    () =>
      sq
        ? PAGE_TUTORIALS.filter(
          (t) =>
            t.title.toLowerCase().includes(sq) ||
            t.description.toLowerCase().includes(sq) ||
            t.steps.some((s) => s.toLowerCase().includes(sq)),
        )
        : PAGE_TUTORIALS,
    [sq],
  )

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>

      {/* ── LEFT RAIL: NAVIGATION & SEARCH ── */}
      <div
        style={{
          width: 320,
          flexShrink: 0,
          background: T.surface1,
          borderRight: `1px solid ${T.borderHi}`,
          display: 'flex',
          flexDirection: 'column',
          zIndex: 10,
        }}
      >
        <div style={{ padding: '24px 20px 20px' }}>
          <h1
            style={{
              fontFamily: FD,
              fontSize: FS.h2,
              fontWeight: 700,
              color: T.text,
              margin: 0,
              letterSpacing: '0.04em',
            }}
          >
            DOCUMENTATION
          </h1>
          <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, margin: '6px 0 0', lineHeight: 1.5 }}>
            Guides, reference manuals, shortcuts, and troubleshooting for Specific Labs Blueprint.
          </p>
        </div>

        {/* Search */}
        <div style={{ padding: '0 20px 20px', position: 'relative' }}>
          <Search
            size={14}
            style={{ position: 'absolute', left: 32, top: 12, color: T.dim }}
          />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search help topics..."
            style={{
              width: '100%',
              padding: '10px 10px 10px 36px',
              background: T.surface3,
              border: `1px solid ${T.borderHi}`,
              color: T.text,
              fontFamily: F,
              fontSize: FS.md,
              outline: 'none',
              borderRadius: 0,
              transition: `border-color 0.2s`,
            }}
            onFocus={(e) => (e.currentTarget.style.borderColor = T.cyan)}
            onBlur={(e) => (e.currentTarget.style.borderColor = T.borderHi)}
          />
        </div>

        {/* Vertical Tabs */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 12px 24px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {TABS.map((tab) => {
              const Icon = tab.icon
              const active = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: '12px 16px',
                    background: active ? `${T.cyan}12` : 'transparent',
                    border: 'none',
                    borderLeft: active ? `3px solid ${T.cyan}` : `3px solid transparent`,
                    color: active ? T.cyan : T.sec,
                    fontFamily: F,
                    fontSize: FS.sm,
                    fontWeight: 900,
                    letterSpacing: '0.12em',
                    cursor: 'pointer',
                    borderRadius: 0,
                    textAlign: 'left',
                    transition: 'all 0.15s ease',
                  }}
                  onMouseEnter={(e) => {
                    if (!active) {
                      e.currentTarget.style.background = T.surface2;
                      e.currentTarget.style.color = T.text;
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!active) {
                      e.currentTarget.style.background = 'transparent';
                      e.currentTarget.style.color = T.sec;
                    }
                  }}
                >
                  <Icon size={16} />
                  {tab.label}
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* ── RIGHT PANEL: CONTENT ── */}
      <div style={{ flex: 1, padding: '40px 60px', overflowY: 'auto', background: T.bg }}>
        <div style={{ maxWidth: 840, margin: '0 auto' }}>
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
          >
            {/* ── GENERAL / PAGE TUTORIALS ── */}
            {activeTab === 'general' && (
              <div>
                <h2 style={sectionHeader}>PAGE-BY-PAGE GUIDE</h2>
                {filteredTutorials.map((tutorial) => {
                  return (
                    <Collapsible
                      key={tutorial.title}
                      title={tutorial.title}
                      accent={T.cyan}
                      defaultOpen={!!sq}
                    >
                      <p style={{ ...bodyText, marginTop: 0, marginBottom: 8 }}>
                        {tutorial.description}
                      </p>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {tutorial.steps.map((step, i) => (
                          <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                            <span
                              style={{
                                fontFamily: F,
                                fontSize: FS.xxs,
                                fontWeight: 900,
                                color: T.cyan,
                                minWidth: 14,
                                textAlign: 'right',
                                flexShrink: 0,
                              }}
                            >
                              {i + 1}.
                            </span>
                            <span style={{ fontFamily: F, fontSize: FS.sm, color: T.sec, lineHeight: 1.5 }}>
                              {step}
                            </span>
                          </div>
                        ))}
                      </div>
                    </Collapsible>
                  )
                })}

                {filteredTutorials.length === 0 && (
                  <p style={{ ...bodyText, color: T.dim, textAlign: 'center', padding: 20 }}>
                    No tutorials match your search.
                  </p>
                )}
              </div>
            )}

            {/* ── MODULES REFERENCE ── */}
            {activeTab === 'modules' && (
              <div>
                <h2 style={sectionHeader}>
                  BLOCK REFERENCE — {BLOCK_REGISTRY.length} BLOCKS
                </h2>
                {Object.entries(filteredBlocks).map(([category, blocks]) => (
                  <Collapsible
                    key={category}
                    title={`${category.toUpperCase()} (${blocks.length})`}
                    defaultOpen={!!sq}
                    accent={blocks[0]?.accent}
                  >
                    {blocks.map((block) => (
                      <BlockDoc key={block.type} block={block} />
                    ))}
                  </Collapsible>
                ))}

                {Object.keys(filteredBlocks).length === 0 && (
                  <p style={{ ...bodyText, color: T.dim, textAlign: 'center', padding: 20 }}>
                    No blocks match your search.
                  </p>
                )}
              </div>
            )}

            {/* ── KEYBOARD SHORTCUTS ── */}
            {activeTab === 'shortcuts' && (
              <div>
                <h2 style={sectionHeader}>KEYBOARD SHORTCUTS</h2>
                <div style={cardStyle}>
                  {filteredShortcuts.map((shortcut, i) => (
                    <div
                      key={i}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '6px 0',
                        borderBottom: i < filteredShortcuts.length - 1 ? `1px solid ${T.border}` : 'none',
                      }}
                    >
                      <span style={{ fontFamily: F, fontSize: FS.sm, color: T.sec }}>
                        {shortcut.action}
                      </span>
                      <div style={{ display: 'flex', gap: 3 }}>
                        {shortcut.keys.map((k, j) => (
                          <KeyBadge key={j} k={k} />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>

                {filteredShortcuts.length === 0 && (
                  <p style={{ ...bodyText, color: T.dim, textAlign: 'center', padding: 20 }}>
                    No shortcuts match your search.
                  </p>
                )}
              </div>
            )}

            {/* ── FAQ ── */}
            {activeTab === 'faq' && (
              <div>
                <h2 style={sectionHeader}>FREQUENTLY ASKED QUESTIONS</h2>
                {filteredFAQ.map((faq, i) => (
                  <Collapsible key={i} title={faq.q} defaultOpen={!!sq}>
                    <p style={{ ...bodyText, margin: 0 }}>{faq.a}</p>
                  </Collapsible>
                ))}

                {filteredFAQ.length === 0 && (
                  <p style={{ ...bodyText, color: T.dim, textAlign: 'center', padding: 20 }}>
                    No FAQ items match your search.
                  </p>
                )}
              </div>
            )}

            {/* ── CLI TOOLS ── */}
            {activeTab === 'cli' && (
              <div>
                <h2 style={sectionHeader}>CLI TOOLS &amp; TESTING</h2>
                <p style={{ ...bodyText, marginTop: 0, marginBottom: 20 }}>
                  Command-line tools for block authors and pipeline developers. Run these from the project root directory.
                </p>
                {CLI_TOOLS.map((tool, i) => (
                  <Collapsible key={i} title={tool.name} defaultOpen={i === 0} accent={T.cyan}>
                    <p style={{ ...bodyText, marginTop: 0, marginBottom: 8 }}>{tool.description}</p>
                    <div
                      style={{
                        fontFamily: 'var(--code-font, "JetBrains Mono", monospace)',
                        fontSize: FS.xxs,
                        color: T.cyan,
                        background: T.bg,
                        padding: '8px 12px',
                        marginBottom: 12,
                        overflowX: 'auto',
                        whiteSpace: 'pre',
                        border: `1px solid ${T.border}`,
                      }}
                    >
                      {tool.command}
                    </div>

                    {tool.aliases.length > 0 && (
                      <div style={{ marginBottom: 12 }}>
                        <span style={labelStyle}>ALIASES</span>
                        {tool.aliases.map((alias, j) => (
                          <div
                            key={j}
                            style={{
                              fontFamily: 'var(--code-font, "JetBrains Mono", monospace)',
                              fontSize: FS.xxs,
                              color: T.dim,
                              marginTop: 2,
                            }}
                          >
                            {alias}
                          </div>
                        ))}
                      </div>
                    )}

                    <div style={{ marginBottom: 12 }}>
                      <span style={labelStyle}>
                        {tool.name === 'Pipeline Validator' ? 'CHECKS' : 'OPTIONS'}
                      </span>
                      {tool.options.map((opt, j) => (
                        <div key={j} style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                          <code
                            style={{
                              fontFamily: 'var(--code-font, "JetBrains Mono", monospace)',
                              fontSize: FS.xxs,
                              color: T.amber,
                              flexShrink: 0,
                              minWidth: 180,
                            }}
                          >
                            {opt.flag}
                          </code>
                          <span style={{ ...bodyText, fontSize: FS.xxs, margin: 0 }}>{opt.desc}</span>
                        </div>
                      ))}
                    </div>

                    <div>
                      <span style={labelStyle}>EXAMPLES</span>
                      {tool.examples.map((ex, j) => (
                        <div
                          key={j}
                          style={{
                            fontFamily: 'var(--code-font, "JetBrains Mono", monospace)',
                            fontSize: FS.xxs,
                            color: T.sec,
                            background: T.bg,
                            padding: '4px 8px',
                            marginTop: 4,
                            overflowX: 'auto',
                            whiteSpace: 'pre',
                            border: `1px solid ${T.border}`,
                          }}
                        >
                          {ex}
                        </div>
                      ))}
                    </div>
                  </Collapsible>
                ))}
              </div>
            )}

            {/* ── MACHINE ── */}
            {activeTab === 'machine' && <MachineTab />}

            {/* ── TROUBLESHOOTING ── */}
            {activeTab === 'troubleshooting' && (
              <div>
                <h2 style={sectionHeader}>TROUBLESHOOTING</h2>
                {filteredTroubleshooting.map((item, i) => (
                  <div key={i} style={cardStyle}>
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        marginBottom: 6,
                      }}
                    >
                      <AlertTriangle size={10} color={T.amber} />
                      <span
                        style={{
                          fontFamily: F,
                          fontSize: FS.sm,
                          fontWeight: 700,
                          color: T.text,
                        }}
                      >
                        {item.issue}
                      </span>
                    </div>
                    <p style={{ ...bodyText, margin: 0, paddingLeft: 16 }}>{item.fix}</p>
                  </div>
                ))}

                {filteredTroubleshooting.length === 0 && (
                  <p style={{ ...bodyText, color: T.dim, textAlign: 'center', padding: 20 }}>
                    No troubleshooting items match your search.
                  </p>
                )}
              </div>
            )}
          </motion.div>
        </div>
      </div>
    </div>
  )
}
