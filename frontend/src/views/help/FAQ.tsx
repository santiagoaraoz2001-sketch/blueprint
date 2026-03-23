import { useState, useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import SectionAnchor from '@/components/Help/SectionAnchor'
import { HelpCircle, Search, ChevronDown, ChevronRight } from 'lucide-react'

const FAQ_DATA = [
  {
    q: 'What is Blueprint?',
    a: 'Blueprint is a local-first ML experiment workbench by Specific Labs. It lets you visually build, run, and analyze machine learning pipelines using a drag-and-drop interface with 118 block types across 9 categories. It runs entirely on your machine — no cloud, no accounts, no data leaves your computer.',
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
    a: 'Three ways: (1) LLM Block Generator — Pipeline Editor → "Generate Block" button (Cmd+G), describe your block in natural language. (2) CLI scaffold — run python scripts/scaffold_block.py to create skeleton files. (3) External LLM — use docs/BLOCK_LLM_PROMPT.md with any LLM, paste generated files. After any method, run python scripts/generate_block_registry.py to update the frontend registry.',
  },
  {
    q: 'Where is my data stored?',
    a: 'All data is stored locally in ~/.specific-labs/ including the SQLite database, model artifacts, plugins, custom blocks, and logs. Nothing is sent to external servers.',
  },
  {
    q: 'Can I use GPU acceleration?',
    a: 'Yes. On Apple Silicon Macs, Blueprint auto-detects Metal/MPS support. On NVIDIA systems, CUDA is detected automatically. Check Settings for hardware capabilities.',
  },
  {
    q: 'How do I connect Ollama?',
    a: 'Install Ollama (ollama.ai), start it with "ollama serve", then go to Settings → LLM Providers and select Ollama. The default endpoint http://localhost:11434 should auto-connect.',
  },
  {
    q: 'Can I export my results?',
    a: 'Yes. Three export connectors are available: Weights & Biases (metrics + artifacts + config), HuggingFace Hub (model + auto-generated model card), and Jupyter Notebook (reproducible .ipynb). Every run also generates a structured run-export.json file. Access exports from Results view → "Export" dropdown.',
  },
  {
    q: 'How do pipelines execute?',
    a: 'Pipelines execute as a DAG in topological order — blocks with no dependencies run first. Each block receives inputs from connected upstream blocks and produces outputs for downstream blocks. Outputs persist after each block, so partial results survive crashes.',
  },
  {
    q: 'What file formats are supported for data loading?',
    a: 'CSV, JSONL, JSON, Parquet, YAML, and plain text files. You can also load directly from HuggingFace Hub using the HuggingFace Loader block.',
  },
  {
    q: 'How do I install plugins?',
    a: 'Use the CLI: python scripts/blueprint_plugin.py install <source> where source is a git URL or local path. Or manually copy the plugin folder to ~/.specific-labs/plugins/. After installing, restart Blueprint or go to Settings → Plugins → "Reload".',
  },
  {
    q: 'What is config inheritance?',
    a: 'Certain config keys (seed, text_column, trust_remote_code) automatically propagate through the DAG from upstream blocks to downstream blocks. This means you set a value once and every downstream block inherits it. Inherited fields show a blue left border. Click the unlink icon to override.',
  },
  {
    q: 'Can I re-run just part of a pipeline?',
    a: 'Yes. After a run completes, right-click any node → "Re-run from here" (or Shift+R). Upstream nodes use cached outputs, and only the target node and downstream nodes re-execute. A config diff preview shows what changed.',
  },
  {
    q: 'How do parameter sweeps work?',
    a: 'Right-click a node → "Parameter Sweep". Define parameter ranges (min/max/step for numbers, multi-choice for selects). Choose Grid search (all combinations) or Random search (N samples). Blueprint creates one run per combination, running up to 4 in parallel. Results appear as a heatmap.',
  },
  {
    q: "What's the difference between Simple and Professional mode?",
    a: 'Simple Mode shows the core workflow only: data, training, inference, evaluation, and output categories. It hides plugins, export connectors, config inheritance badges, the Paper tool, and Control Tower. Professional Mode shows everything. Toggle in Settings → UI Mode.',
  },
  {
    q: 'How do I compare two models?',
    a: 'Use the model_diff block. It loads two models, runs the same prompt through both, and compares top-K token probabilities per position, KL divergence, and cosine similarity of hidden states. Results show a token-by-token comparison table and distribution charts.',
  },
  {
    q: 'Can I undo a training run?',
    a: 'If checkpoint_interval is set (> 0) in your training block config, Blueprint saves checkpoints at regular intervals. Go to Results → click the run → checkpoint timeline shows loss curve with clickable markers. Click any checkpoint → "Load as Model" to use that exact state.',
  },
  {
    q: 'How does Blueprint ensure reproducibility?',
    a: 'Four mechanisms: (1) Dataset hashing — SHA256 of all inputs recorded per run. (2) Config snapshots — every run records its full pipeline config. (3) Metrics versioning — versioned metrics with aggregation types. (4) Structured exports — run-export.json contains everything needed to reproduce results.',
  },
  {
    q: 'How do I import datasets from HuggingFace?',
    a: 'Two ways: (1) Use the HuggingFace Loader block in a pipeline to load datasets programmatically. (2) Install the Blueprint Chrome extension from extensions/chrome-blueprint-hf/ — browse any dataset on huggingface.co and click the extension icon to send it directly to your local Blueprint instance.',
  },
  {
    q: 'What is the Artifact Registry?',
    a: 'The Artifact Registry tracks all outputs produced by block executions across pipeline runs. Browse artifacts from the Outputs Monitor view. Each artifact records its source block, run ID, timestamp, and file path. This gives you a global view of everything Blueprint has produced.',
  },
  {
    q: 'What happens if the backend goes down during a run?',
    a: 'The API client includes a circuit breaker that prevents retry storms. When the backend becomes unavailable, the client automatically backs off instead of flooding it with retries. Partial outputs from completed blocks are preserved. When the backend recovers, the circuit breaker resets and normal operation resumes.',
  },
  {
    q: 'How does memory pressure monitoring work?',
    a: 'Blueprint monitors system memory usage during pipeline execution. When memory pressure gets high, it automatically identifies and cleans up zombie processes to free resources, preventing out-of-memory crashes. This is especially useful during training and inference of large models.',
  },
]

export const FAQ_TEXT = FAQ_DATA.map((f) => `Q: ${f.q} A: ${f.a}`).join(' ')

export default function FAQ() {
  const [searchQuery, setSearchQuery] = useState('')
  const [openQuestion, setOpenQuestion] = useState<string | null>(null)

  const filtered = useMemo(() => {
    const q = searchQuery.toLowerCase().trim()
    if (!q) return FAQ_DATA
    return FAQ_DATA.filter(
      (f) => f.q.toLowerCase().includes(q) || f.a.toLowerCase().includes(q),
    )
  }, [searchQuery])

  return (
    <div>
      <SectionAnchor id="faq" title="Frequently Asked Questions" level={1}>
        <HelpCircle size={22} color={T.cyan} />
      </SectionAnchor>

      {/* Search */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 12px',
          background: T.surface2,
          border: `1px solid ${T.border}`,
          marginBottom: 16,
        }}
      >
        <Search size={15} color={T.dim} />
        <input
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search FAQ..."
          style={{
            flex: 1,
            background: 'transparent',
            border: 'none',
            outline: 'none',
            fontFamily: F,
            fontSize: FS.sm,
            color: T.text,
          }}
        />
      </div>

      {/* Questions */}
      {filtered.map((f) => {
        const isOpen = openQuestion === f.q
        return (
          <div
            key={f.q}
            style={{
              background: T.surface2,
              border: `1px solid ${T.borderHi}`,
              marginBottom: 6,
            }}
          >
            <div
              onClick={() => setOpenQuestion(isOpen ? null : f.q)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '12px 16px',
                cursor: 'pointer',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = T.surface1)}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              {isOpen ? (
                <ChevronDown size={14} color={T.dim} />
              ) : (
                <ChevronRight size={14} color={T.dim} />
              )}
              <HelpCircle size={14} color={T.cyan} />
              <span
                style={{
                  fontFamily: F,
                  fontSize: FS.sm,
                  fontWeight: 600,
                  color: T.text,
                }}
              >
                {f.q}
              </span>
            </div>
            {isOpen && (
              <div
                style={{
                  padding: '10px 16px 14px 42px',
                  borderTop: `1px solid ${T.border}`,
                  fontFamily: F,
                  fontSize: FS.sm,
                  color: T.sec,
                  lineHeight: 1.7,
                }}
              >
                {f.a}
              </div>
            )}
          </div>
        )
      })}

      {filtered.length === 0 && (
        <div
          style={{
            fontFamily: F,
            fontSize: FS.sm,
            color: T.dim,
            textAlign: 'center',
            padding: 32,
          }}
        >
          No matching questions found.
        </div>
      )}
    </div>
  )
}
