import { useState, useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import SectionAnchor from '@/components/Help/SectionAnchor'
import { AlertTriangle, Search, ChevronDown, ChevronRight } from 'lucide-react'

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
    fix: 'The required Python package is not installed in the Blueprint venv. Activate the venv (source .venv/bin/activate) and pip install the missing package.',
  },
  {
    issue: 'Models not appearing in Model Hub',
    fix: 'Blueprint scans ~/.cache/huggingface/ and ~/.ollama/. For Ollama models, ensure Ollama is running. For HuggingFace models, they appear after first download via a pipeline.',
  },
  {
    issue: 'Electron app shows blank screen',
    fix: 'Ensure both backend (port 8000) and frontend dev server (port 5173) are running. The Electron app loads from the dev server. Try: cd frontend && npm run dev',
  },
  {
    issue: 'Out of memory during training',
    fix: 'Reduce batch_size in the training block config. For LoRA, reduce rank (r). For full fine-tuning, consider switching to LoRA or QLoRA for significantly less memory usage.',
  },
  {
    issue: 'Slow pipeline execution',
    fix: 'Check Monitor view for CPU/memory/GPU utilization. Common causes: CPU inference when GPU is available (check Settings → LLM Providers), large dataset loading without streaming.',
  },
  {
    issue: 'Config inheritance not working',
    fix: 'Only keys listed in GLOBAL_PROPAGATION_KEYS (seed, text_column, trust_remote_code) propagate automatically. Other config keys need explicit connections between blocks. Check that upstream blocks are correctly connected.',
  },
  {
    issue: 'Export connector fails',
    fix: 'Check that the required library is installed (wandb, huggingface_hub, or nbformat). Verify API key validity. For W&B, ensure the project name exists in your W&B account.',
  },
  {
    issue: 'Plugin not loading',
    fix: 'Check plugin.yaml syntax (valid YAML). Check __init__.py for import errors. View logs at ~/.specific-labs/logs/blueprint.jsonl for the specific error. Try: python scripts/blueprint_plugin.py info <name>',
  },
  {
    issue: 'Sweep runs stuck or queued',
    fix: 'Sweeps run up to 4 configurations in parallel. If all slots are occupied, new runs queue. Check Monitor view for active runs. Cancel stale runs to free slots.',
  },
  {
    issue: 'Re-run from node unavailable',
    fix: 'Only available on completed (not failed or cancelled) runs. The source run must have cached outputs (outputs_snapshot). If the run was deleted or artifacts cleaned, re-run from node is not available.',
  },
  {
    issue: 'Block Generator produces bad code',
    fix: 'LLM quality depends on the model. Use a capable model (7B+ parameters recommended). Review and test generated code before installing. Try rephrasing your description to be more specific.',
  },
  {
    issue: 'SSE connection keeps dropping',
    fix: 'Check if a reverse proxy (nginx, cloudflare tunnel) is timing out. Blueprint sends a 15-second keepalive. Configure your proxy timeout to be > 20 seconds. Check browser dev tools Network tab for connection status.',
  },
  {
    issue: 'Checkpoint rollback shows no checkpoints',
    fix: 'Set checkpoint_interval > 0 in the training block config. Default is 0 (final model only). For example, checkpoint_interval: 5 saves a checkpoint every 5 epochs.',
  },
  {
    issue: 'Chrome extension not connecting to Blueprint',
    fix: 'Ensure the Blueprint backend is running on port 8000. The extension sends requests to http://localhost:8000. Check that CORS is configured to allow the extension origin. Try reloading the extension from chrome://extensions.',
  },
  {
    issue: 'GPU not detected (MPS/Metal)',
    fix: 'MPS/Metal acceleration requires macOS 12.3+ and Apple Silicon (M1/M2/M3). Check Settings for hardware capabilities. Verify PyTorch is installed with MPS support: python -c "import torch; print(torch.backends.mps.is_available())". If False, reinstall PyTorch.',
  },
  {
    issue: 'Circuit breaker stuck in open state',
    fix: 'The circuit breaker opens after repeated backend failures to prevent retry storms. Ensure the backend is running and healthy. The circuit breaker will automatically reset after a cooldown period. Restart the frontend if the issue persists.',
  },
]

export const TROUBLESHOOTING_TEXT = TROUBLESHOOTING.map(
  (t) => `${t.issue}: ${t.fix}`,
).join(' ')

export default function Troubleshooting() {
  const [searchQuery, setSearchQuery] = useState('')
  const [openIssue, setOpenIssue] = useState<string | null>(null)

  const filtered = useMemo(() => {
    const q = searchQuery.toLowerCase().trim()
    if (!q) return TROUBLESHOOTING
    return TROUBLESHOOTING.filter(
      (t) => t.issue.toLowerCase().includes(q) || t.fix.toLowerCase().includes(q),
    )
  }, [searchQuery])

  return (
    <div>
      <SectionAnchor id="troubleshooting" title="Troubleshooting" level={1}>
        <AlertTriangle size={22} color={T.cyan} />
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
          placeholder="Search troubleshooting..."
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

      {/* Issues */}
      {filtered.map((t) => {
        const isOpen = openIssue === t.issue
        return (
          <div
            key={t.issue}
            style={{
              background: T.surface2,
              border: `1px solid ${T.borderHi}`,
              marginBottom: 6,
            }}
          >
            <div
              onClick={() => setOpenIssue(isOpen ? null : t.issue)}
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
              <AlertTriangle size={14} color="#f59e0b" />
              <span
                style={{
                  fontFamily: F,
                  fontSize: FS.sm,
                  fontWeight: 600,
                  color: T.text,
                }}
              >
                {t.issue}
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
                {t.fix}
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
          No matching issues found.
        </div>
      )}
    </div>
  )
}
