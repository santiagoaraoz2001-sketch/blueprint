import { useState, useMemo } from 'react'
import { T, F, FS, CATEGORY_COLORS } from '@/lib/design-tokens'
import { getAllBlocks, type BlockDefinition } from '@/lib/block-registry'
import SectionAnchor from '@/components/Help/SectionAnchor'
import {
  Blocks,
  Search,
  FileCode,
  Layers,
  Cpu,
  Brain,
  TestTube,
  Merge,
  Workflow,
  Bot,
  Globe,
  FileOutput,
  AlertTriangle,
  Sparkles,

  Wand2,
  ChevronDown,
  ChevronRight,
} from 'lucide-react'
import { helpCard as card, helpBody as body, helpTip as tip, helpStepList as stepList, helpCode as code } from './styles'

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  data: <FileCode size={14} />,
  training: <Cpu size={14} />,
  inference: <Brain size={14} />,
  evaluation: <TestTube size={14} />,
  merge: <Merge size={14} />,
  flow: <Workflow size={14} />,
  agents: <Bot size={14} />,
  endpoints: <Globe size={14} />,
  output: <FileOutput size={14} />,
  external: <Globe size={14} />,
  composite: <Layers size={14} />,
  plugin: <Layers size={14} />,
}

function BlockDoc({ block }: { block: BlockDefinition }) {
  const [open, setOpen] = useState(false)
  const catColor = CATEGORY_COLORS[block.category] ?? T.cyan

  return (
    <div
      style={{
        border: `1px solid ${T.border}`,
        marginBottom: 6,
        background: T.surface1,
      }}
    >
      <div
        onClick={() => setOpen(!open)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 12px',
          cursor: 'pointer',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = T.surface2)}
        onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
      >
        {open ? (
          <ChevronDown size={13} color={T.dim} />
        ) : (
          <ChevronRight size={13} color={T.dim} />
        )}
        <span
          style={{
            fontFamily: F,
            fontSize: FS.sm,
            fontWeight: 600,
            color: T.text,
            flex: 1,
          }}
        >
          {block.name}
        </span>
        <span
          style={{
            fontFamily: F,
            fontSize: 10,
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            color: catColor,
            background: `${catColor}18`,
            padding: '2px 6px',
          }}
        >
          {block.category}
        </span>
        {block.maturity && block.maturity !== 'stable' && (
          <span
            style={{
              fontFamily: F,
              fontSize: 10,
              fontWeight: 600,
              color: block.maturity === 'beta' ? '#f59e0b' : '#ef4444',
              textTransform: 'uppercase',
            }}
          >
            {block.maturity}
          </span>
        )}
      </div>

      {open && (
        <div style={{ padding: '8px 12px 14px 32px', borderTop: `1px solid ${T.border}` }}>
          <p style={{ ...body, fontSize: FS.xs, marginBottom: 10 }}>{block.description}</p>

          {block.inputs.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <span
                style={{
                  fontFamily: F,
                  fontSize: FS.xxs,
                  fontWeight: 700,
                  color: T.dim,
                  textTransform: 'uppercase',
                  letterSpacing: '0.1em',
                }}
              >
                Inputs
              </span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                {block.inputs.map((p) => (
                  <span
                    key={p.id}
                    style={{
                      fontFamily: F,
                      fontSize: 10,
                      padding: '2px 6px',
                      background: T.surface2,
                      border: `1px solid ${T.border}`,
                      color: T.sec,
                    }}
                  >
                    {p.label} ({p.dataType})
                  </span>
                ))}
              </div>
            </div>
          )}

          {block.outputs.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <span
                style={{
                  fontFamily: F,
                  fontSize: FS.xxs,
                  fontWeight: 700,
                  color: T.dim,
                  textTransform: 'uppercase',
                  letterSpacing: '0.1em',
                }}
              >
                Outputs
              </span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                {block.outputs.map((p) => (
                  <span
                    key={p.id}
                    style={{
                      fontFamily: F,
                      fontSize: 10,
                      padding: '2px 6px',
                      background: T.surface2,
                      border: `1px solid ${T.border}`,
                      color: T.sec,
                    }}
                  >
                    {p.label} ({p.dataType})
                  </span>
                ))}
              </div>
            </div>
          )}

          {block.configFields.length > 0 && (
            <div>
              <span
                style={{
                  fontFamily: F,
                  fontSize: FS.xxs,
                  fontWeight: 700,
                  color: T.dim,
                  textTransform: 'uppercase',
                  letterSpacing: '0.1em',
                }}
              >
                Config Fields
              </span>
              <div style={{ marginTop: 4 }}>
                {block.configFields.map((cf) => (
                  <div
                    key={cf.name}
                    style={{
                      fontFamily: F,
                      fontSize: FS.xs,
                      color: T.sec,
                      padding: '2px 0',
                      display: 'flex',
                      gap: 8,
                    }}
                  >
                    <span style={{ fontWeight: 600, color: T.text }}>{cf.name}</span>
                    <span style={{ color: T.dim }}>({cf.type})</span>
                    {cf.description && (
                      <span style={{ color: T.dim, flex: 1 }}>— {cf.description}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export const BLOCKS_REFERENCE_TEXT = `Block Anatomy. Every block is a directory: blocks/{category}/{block_type}/ with block.yaml (metadata + config schema) and run.py (execution logic). block.yaml declares: name, type, category, inputs, outputs, config fields with types/defaults/bounds, timeout, max_retries. run.py exports def run(ctx: BlockContext). Block Categories: Data (34 blocks), Training (12 blocks), Inference (18 blocks), Evaluation (24 blocks), Merge (5 blocks), Flow (17 blocks), Agents (9 blocks), Endpoints (8 blocks), Output (5 blocks). 118 blocks total across 9 categories. Special Blocks: A/B Significance Test compares two model variants with statistical significance testing (Welch's t-test, Mann-Whitney U, bootstrap). Reports p-value, Cohen's d, 95% CI, verdict. Model Diff loads two models, runs same prompt, compares top-K token probabilities, KL divergence, cosine similarity. BALLAST Training freezes most parameters, trains only embeddings + LayerNorm + output head (0.1-0.5% of params). Dataset Builder prepares training-ready datasets from raw data. Composite Blocks are sub-pipeline blocks for multi-agent orchestration. Block Validation checks inputs against block.yaml schema. Typed exceptions: BlockInputError, BlockConfigError, BlockTimeoutError, BlockMemoryError, BlockDependencyError, BlockDataError. Creating Custom Blocks: Option A LLM Block Generator (Cmd+G), Option B CLI scaffold_block.py, Option C external LLM prompt.`

export default function BlocksReference() {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)

  const categories = useMemo(() => {
    const cats: Record<string, BlockDefinition[]> = {}
    getAllBlocks().forEach((b) => {
      ;(cats[b.category] ??= []).push(b)
    })
    return Object.entries(cats).sort(([a], [b]) => a.localeCompare(b))
  }, [])

  const filtered = useMemo(() => {
    const q = searchQuery.toLowerCase().trim()
    let blocks = getAllBlocks()
    if (selectedCategory) blocks = blocks.filter((b) => b.category === selectedCategory)
    if (q) {
      blocks = blocks.filter(
        (b) =>
          b.name.toLowerCase().includes(q) ||
          b.type.toLowerCase().includes(q) ||
          b.description.toLowerCase().includes(q) ||
          b.tags.some((t) => t.toLowerCase().includes(q)),
      )
    }
    return blocks
  }, [searchQuery, selectedCategory])

  return (
    <div>
      <SectionAnchor id="blocks-reference" title="Blocks In Depth" level={1}>
        <Blocks size={22} color={T.cyan} />
      </SectionAnchor>

      {/* 4.1 Block Anatomy */}
      <SectionAnchor id="blocks-reference/anatomy" title="Block Anatomy" level={2}>
        <FileCode size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          Every block is a directory:{' '}
          <span style={code}>blocks/&#123;category&#125;/&#123;block_type&#125;/</span>
        </p>
        <ul style={stepList}>
          <li>
            <span style={code}>block.yaml</span> — Metadata + config schema: name, type, category,
            inputs, outputs, config fields with types/defaults/bounds, timeout, max_retries
          </li>
          <li>
            <span style={code}>run.py</span> — Execution logic: exports{' '}
            <span style={code}>def run(ctx: BlockContext)</span> which receives config, inputs, and
            callbacks
          </li>
        </ul>
      </div>

      {/* 4.2 Block Categories Reference */}
      <SectionAnchor id="blocks-reference/categories" title="Block Categories Reference" level={2}>
        <Layers size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          {getAllBlocks().length}+ blocks across {categories.length} categories. Click any block
          below to see its full configuration.
        </p>

        {/* Search + filter */}
        <div style={{ display: 'flex', gap: 8, marginTop: 14, marginBottom: 14 }}>
          <div
            style={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '6px 10px',
              background: T.surface1,
              border: `1px solid ${T.border}`,
            }}
          >
            <Search size={14} color={T.dim} />
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search blocks..."
              style={{
                flex: 1,
                background: 'transparent',
                border: 'none',
                outline: 'none',
                fontFamily: F,
                fontSize: FS.xs,
                color: T.text,
              }}
            />
          </div>
        </div>

        {/* Category pills */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 14 }}>
          <span
            onClick={() => setSelectedCategory(null)}
            style={{
              fontFamily: F,
              fontSize: 10,
              fontWeight: 600,
              padding: '3px 8px',
              cursor: 'pointer',
              background: !selectedCategory ? T.cyan : T.surface1,
              color: !selectedCategory ? '#fff' : T.sec,
              border: `1px solid ${!selectedCategory ? T.cyan : T.border}`,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
            }}
          >
            All ({getAllBlocks().length})
          </span>
          {categories.map(([cat, blocks]) => {
            const catColor = CATEGORY_COLORS[cat] ?? T.cyan
            return (
              <span
                key={cat}
                onClick={() => setSelectedCategory(cat === selectedCategory ? null : cat)}
                style={{
                  fontFamily: F,
                  fontSize: 10,
                  fontWeight: 600,
                  padding: '3px 8px',
                  cursor: 'pointer',
                  background: cat === selectedCategory ? catColor : T.surface1,
                  color: cat === selectedCategory ? '#fff' : catColor,
                  border: `1px solid ${cat === selectedCategory ? catColor : T.border}`,
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                }}
              >
                {CATEGORY_ICONS[cat]}
                {cat} ({blocks.length})
              </span>
            )
          })}
        </div>

        {/* Block list */}
        <div style={{ maxHeight: 600, overflowY: 'auto' }}>
          {filtered.length === 0 ? (
            <p style={{ ...body, color: T.dim, textAlign: 'center', padding: 20 }}>
              No blocks match your search.
            </p>
          ) : (
            filtered.map((b) => <BlockDoc key={b.type} block={b} />)
          )}
        </div>
      </div>

      {/* 4.3 Special Blocks */}
      <SectionAnchor id="blocks-reference/special" title="Special Blocks" level={2}>
        <Sparkles size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <div style={{ marginBottom: 16 }}>
          <div
            style={{
              fontFamily: F,
              fontSize: FS.sm,
              fontWeight: 700,
              color: T.text,
              marginBottom: 6,
            }}
          >
            A/B Significance Test (ab_significance)
          </div>
          <ul style={stepList}>
            <li>Compares two model variants with statistical significance testing</li>
            <li>Supports Welch&apos;s t-test, Mann-Whitney U, and bootstrap permutation test</li>
            <li>Reports: p-value, Cohen&apos;s d (effect size), 95% confidence interval, verdict</li>
            <li>Warns when sample size is too low for reliable results</li>
          </ul>
        </div>

        <div style={{ marginBottom: 16 }}>
          <div
            style={{
              fontFamily: F,
              fontSize: FS.sm,
              fontWeight: 700,
              color: T.text,
              marginBottom: 6,
            }}
          >
            Model Diff (model_diff)
          </div>
          <ul style={stepList}>
            <li>Loads two models, runs the same prompt through both</li>
            <li>Compares: top-K token probabilities, KL divergence, cosine similarity of hidden states</li>
            <li>Output: JSON report + visualization showing where models diverge</li>
            <li>Use after merging to understand what changed</li>
          </ul>
        </div>

        <div style={{ marginBottom: 16 }}>
          <div
            style={{
              fontFamily: F,
              fontSize: FS.sm,
              fontWeight: 700,
              color: T.text,
              marginBottom: 6,
            }}
          >
            BALLAST Training (ballast_training)
          </div>
          <ul style={stepList}>
            <li>
              Specific Labs&apos; novel method: freezes most parameters, trains only embeddings + LayerNorm + output head
              (0.1–0.5% of params)
            </li>
            <li>
              <span style={code}>layer_depth</span> controls what fraction of layers to train
            </li>
            <li>
              <span style={code}>balance_factor</span> scales learning rate by layer depth
            </li>
            <li>For domain adaptation with minimal compute</li>
          </ul>
        </div>

        <div>
          <div
            style={{
              fontFamily: F,
              fontSize: FS.sm,
              fontWeight: 700,
              color: T.text,
              marginBottom: 6,
            }}
          >
            Composite Blocks
          </div>
          <ul style={stepList}>
            <li>
              A single canvas node that internally runs a sub-pipeline (marked{' '}
              <span style={code}>composite: true</span> in block.yaml)
            </li>
            <li>
              Example: <span style={code}>multi_agent_debate</span> orchestrates multiple LLM instances
              with distinct personas to debate a topic
            </li>
            <li>Useful for multi-agent architectures that should appear as one unit on the canvas</li>
          </ul>
        </div>
      </div>

      {/* 4.4 Block Validation & Error Handling */}
      <SectionAnchor
        id="blocks-reference/validation"
        title="Block Validation & Error Handling"
        level={2}
      >
        <AlertTriangle size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          Before execution, the validator checks all inputs against the{' '}
          <span style={code}>block.yaml</span> schema: required inputs connected, config types
          correct, values within bounds.
        </p>
        <p style={{ ...body, marginTop: 10 }}>
          <strong>Typed Exceptions:</strong>
        </p>
        <ul style={stepList}>
          <li>
            <span style={code}>BlockInputError</span> — Missing or invalid input data
          </li>
          <li>
            <span style={code}>BlockConfigError</span> — Invalid config values
          </li>
          <li>
            <span style={code}>BlockTimeoutError</span> — Block exceeded timeout limit
          </li>
          <li>
            <span style={code}>BlockMemoryError</span> — Out of memory
          </li>
          <li>
            <span style={code}>BlockDependencyError</span> — Missing Python package
          </li>
          <li>
            <span style={code}>BlockDataError</span> — Data format mismatch
          </li>
        </ul>
        <p style={{ ...body, marginTop: 8 }}>
          Each error shows: error type badge, human-readable message, expandable details, and a
          &ldquo;Retry&rdquo; button for recoverable errors. Blocks can set{' '}
          <span style={code}>max_retries</span> in block.yaml for auto-retry on recoverable errors.
        </p>
      </div>

      {/* 4.5 Creating Custom Blocks */}
      <SectionAnchor id="blocks-reference/custom" title="Creating Custom Blocks" level={2}>
        <Wand2 size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <div style={{ marginBottom: 16 }}>
          <div
            style={{
              fontFamily: F,
              fontSize: FS.sm,
              fontWeight: 700,
              color: T.text,
              marginBottom: 6,
            }}
          >
            Option A: LLM Block Generator (in-app)
          </div>
          <ul style={stepList}>
            <li>
              Pipeline Editor → &ldquo;Generate Block&rdquo; button (or{' '}
              <span style={code}>Cmd+G</span>)
            </li>
            <li>Describe what you want in natural language</li>
            <li>Blueprint uses your local LLM to generate block.yaml + run.py</li>
            <li>Preview the generated code → &ldquo;Test Block&rdquo; → &ldquo;Install to Blueprint&rdquo;</li>
            <li>Requires a running LLM backend (Ollama or MLX)</li>
          </ul>
        </div>

        <div style={{ marginBottom: 16 }}>
          <div
            style={{
              fontFamily: F,
              fontSize: FS.sm,
              fontWeight: 700,
              color: T.text,
              marginBottom: 6,
            }}
          >
            Option B: CLI Scaffold
          </div>
          <ul style={stepList}>
            <li>
              Run:{' '}
              <span style={code}>
                python scripts/scaffold_block.py --name &quot;My Block&quot; --category data --type my_block
              </span>
            </li>
            <li>Creates skeleton block.yaml + run.py in the correct directory</li>
            <li>
              Test with:{' '}
              <span style={code}>python -m backend.tests.block_runner blocks/data/my_block --fixture small</span>
            </li>
            <li>
              Run{' '}
              <span style={code}>python scripts/generate_block_registry.py</span> to update the
              frontend registry
            </li>
          </ul>
        </div>

        <div>
          <div
            style={{
              fontFamily: F,
              fontSize: FS.sm,
              fontWeight: 700,
              color: T.text,
              marginBottom: 6,
            }}
          >
            Option C: External LLM Prompt
          </div>
          <ul style={stepList}>
            <li>
              Copy <span style={code}>docs/BLOCK_LLM_PROMPT.md</span> into any LLM (Claude, GPT,
              etc.)
            </li>
            <li>The prompt includes the full BlockContext API, exception hierarchy, and examples</li>
            <li>
              Paste generated files into{' '}
              <span style={code}>blocks/&#123;category&#125;/&#123;type&#125;/</span>
            </li>
          </ul>
        </div>

        <div style={tip}>
          The LLM Block Generator is the fastest way for most users. For production blocks,
          consider the CLI scaffold for more control.
        </div>
      </div>
    </div>
  )
}
