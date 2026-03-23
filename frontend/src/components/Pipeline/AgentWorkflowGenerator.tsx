import { useState, useCallback, useRef } from 'react'
import { T, F, FD, FS } from '@/lib/design-tokens'
import { useAgentStore } from '@/stores/agentStore'
import { usePipelineStore } from '@/stores/pipelineStore'
import type { LLMProvider } from '@/stores/agentStore'
import {
  Sparkles, Wifi, WifiOff, Upload, Download, Loader2, X,
  CheckCircle, AlertCircle, ChevronRight,
} from 'lucide-react'

const panelWidth = 320

const labelStyle: React.CSSProperties = {
  fontFamily: F,
  fontSize: FS.xxs,
  fontWeight: 900,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  color: T.dim,
  display: 'block',
  marginBottom: 4,
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '5px 8px',
  background: T.surface4,
  border: `1px solid ${T.border}`,
  color: T.text,
  fontFamily: F,
  fontSize: FS.sm,
  outline: 'none',
  borderRadius: 0,
  boxSizing: 'border-box',
}

interface Props {
  onClose: () => void
}

export default function AgentWorkflowGenerator({ onClose }: Props) {
  const {
    provider, model, endpoint, isConnected, isGenerating,
    availableModels, error,
    setProvider, setModel, setEndpoint,
    testConnection, fetchModels, generateWorkflow,
  } = useAgentStore()

  const applyGeneratedWorkflow = usePipelineStore((s) => s.applyGeneratedWorkflow)

  const [researchPlan, setResearchPlan] = useState('')
  const [generatedPipeline, setGeneratedPipeline] = useState<{ nodes: any[]; edges: any[] } | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleConnect = useCallback(async () => {
    const ok = await testConnection()
    if (ok) {
      await fetchModels()
    }
  }, [testConnection, fetchModels])

  const handleGenerate = useCallback(async () => {
    if (!researchPlan.trim()) return
    const result = await generateWorkflow(researchPlan)
    if (result) {
      setGeneratedPipeline(result)
    }
  }, [researchPlan, generateWorkflow])

  const handleApply = useCallback(() => {
    if (!generatedPipeline) return
    applyGeneratedWorkflow(generatedPipeline.nodes, generatedPipeline.edges)
    setGeneratedPipeline(null)
    onClose()
  }, [generatedPipeline, applyGeneratedWorkflow, onClose])

  const handleFileUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      setResearchPlan(ev.target?.result as string || '')
    }
    reader.readAsText(file)
    e.target.value = ''
  }, [])

  const handleDownloadTemplate = useCallback(() => {
    const template = `RESEARCH PLAN TEMPLATE — Specific Labs Blueprint
═══════════════════════════════════════════════════

1. RESEARCH QUESTION
   What question are you trying to answer?
   →

2. HYPOTHESIS
   What do you expect to find?
   →

3. DATA SOURCES
   Where will your data come from?
   • Source 1:
   • Source 2:
   • Format: (CSV / JSON / HuggingFace dataset / API)

4. PREPROCESSING STEPS
   How should data be cleaned and prepared?
   • Step 1:
   • Step 2:
   • Split ratio: (e.g., 80/10/10 train/val/test)

5. MODEL SELECTION
   What type of model will you use?
   • Base model: (e.g., Llama-3, Mistral-7B, GPT-2)
   • Training method: (LoRA / QLoRA / Full fine-tuning / DPO)
   • Key hyperparameters:
     - Learning rate:
     - Epochs:
     - Batch size:

6. EVALUATION METRICS
   How will you measure success?
   • Metric 1: (e.g., accuracy, perplexity, BLEU)
   • Metric 2:
   • Benchmark: (e.g., MMLU, HumanEval, custom)

7. OUTPUT FORMAT
   What should the final output be?
   • Model format: (GGUF / SafeTensors / ONNX)
   • Reports: (metrics dashboard / model card / paper)
   • Deployment: (API server / batch inference / export)

8. ADDITIONAL NOTES
   Any other requirements or constraints?
   →
`
    const blob = new Blob([template], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'research_plan_template.txt'
    a.click()
    URL.revokeObjectURL(url)
  }, [])

  return (
    <div
      style={{
        width: panelWidth,
        minWidth: panelWidth,
        height: '100%',
        background: T.surface1,
        borderLeft: `1px solid ${T.borderHi}`,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '10px 12px',
          borderBottom: `1px solid ${T.border}`,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          flexShrink: 0,
        }}
      >
        <Sparkles size={12} color={T.cyan} />
        <span style={{ fontFamily: FD, fontSize: FS.xl, fontWeight: 700, color: T.text, letterSpacing: '0.06em', flex: 1 }}>
          AI WORKFLOW
        </span>
        <button
          onClick={onClose}
          style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 2, display: 'flex' }}
        >
          <X size={12} />
        </button>
      </div>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 14 }}>
        {/* Connection section */}
        <div>
          <label style={labelStyle}>LLM PROVIDER</label>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value as LLMProvider)}
            style={inputStyle}
          >
            <option value="ollama">Ollama</option>
            <option value="mlx">MLX / LM Studio</option>
            <option value="manual">Custom Endpoint</option>
          </select>
        </div>

        <div>
          <label style={labelStyle}>ENDPOINT</label>
          <div style={{ display: 'flex', gap: 4 }}>
            <input
              value={endpoint}
              onChange={(e) => setEndpoint(e.target.value)}
              style={{ ...inputStyle, flex: 1 }}
              placeholder="http://localhost:11434"
            />
            <button
              onClick={handleConnect}
              style={{
                ...inputStyle,
                width: 'auto',
                cursor: 'pointer',
                color: isConnected ? T.green : T.dim,
                fontWeight: 700,
                padding: '5px 10px',
                display: 'flex',
                alignItems: 'center',
                gap: 3,
              }}
            >
              {isConnected
                ? <><Wifi size={9} /> OK</>
                : <><WifiOff size={9} /> CONNECT</>}
            </button>
          </div>
        </div>

        {isConnected && (
          <div>
            <label style={labelStyle}>MODEL</label>
            {availableModels.length > 0 ? (
              <select value={model} onChange={(e) => setModel(e.target.value)} style={inputStyle}>
                {availableModels.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            ) : (
              <input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                style={inputStyle}
                placeholder="Model name..."
              />
            )}
          </div>
        )}

        {/* Divider */}
        <div style={{ height: 1, background: T.border }} />

        {/* Research Plan */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
            <label style={{ ...labelStyle, margin: 0 }}>RESEARCH PLAN</label>
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                onClick={handleDownloadTemplate}
                style={{
                  background: 'none',
                  border: `1px solid ${T.border}`,
                  color: T.dim,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  cursor: 'pointer',
                  padding: '2px 6px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 3,
                }}
              >
                <Download size={8} /> TEMPLATE
              </button>
              <button
                onClick={() => fileInputRef.current?.click()}
                style={{
                  background: 'none',
                  border: `1px solid ${T.border}`,
                  color: T.dim,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  cursor: 'pointer',
                  padding: '2px 6px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 3,
                }}
              >
                <Upload size={8} /> UPLOAD
              </button>
            </div>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.md,.xlsx,.xls,.csv"
            style={{ display: 'none' }}
            onChange={handleFileUpload}
          />
          <textarea
            value={researchPlan}
            onChange={(e) => setResearchPlan(e.target.value)}
            placeholder="Describe your research plan here, or upload a file using the button above...

Example:
Fine-tune Llama-3-8B on a custom Q&A dataset from HuggingFace using LoRA. Evaluate with MMLU and HumanEval benchmarks. Export as GGUF for local inference."
            style={{
              ...inputStyle,
              height: 160,
              resize: 'vertical',
              lineHeight: 1.5,
              fontFamily: F,
            }}
          />
        </div>

        {/* Generate button */}
        <button
          onClick={handleGenerate}
          disabled={isGenerating || !researchPlan.trim() || (!isConnected && provider !== 'manual')}
          style={{
            width: '100%',
            padding: '8px 12px',
            background: isGenerating ? T.surface4 : `${T.cyan}18`,
            border: `1px solid ${isGenerating ? T.border : T.cyan}50`,
            color: isGenerating ? T.dim : T.cyan,
            fontFamily: F,
            fontSize: FS.md,
            fontWeight: 900,
            letterSpacing: '0.1em',
            cursor: isGenerating ? 'wait' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            transition: 'all 0.15s',
          }}
        >
          {isGenerating ? (
            <>
              <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} />
              GENERATING...
            </>
          ) : (
            <>
              <Sparkles size={12} />
              GENERATE WORKFLOW
            </>
          )}
        </button>

        {/* Error */}
        {error && (
          <div
            style={{
              padding: '6px 10px',
              background: `${T.red}15`,
              border: `1px solid ${T.red}40`,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <AlertCircle size={10} color={T.red} />
            <span style={{ fontFamily: F, fontSize: FS.xs, color: T.red }}>{error}</span>
          </div>
        )}

        {/* Generated pipeline preview */}
        {generatedPipeline && (
          <div
            style={{
              padding: 10,
              background: T.surface2,
              border: `1px solid ${T.cyan}40`,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 8 }}>
              <CheckCircle size={10} color={T.green} />
              <span style={{ fontFamily: F, fontSize: FS.xs, fontWeight: 700, color: T.green }}>
                WORKFLOW GENERATED
              </span>
            </div>
            <div style={{ fontFamily: F, fontSize: FS.xs, color: T.sec, marginBottom: 8 }}>
              {generatedPipeline.nodes.length} blocks, {generatedPipeline.edges.length} connections
            </div>
            {/* Mini block list */}
            <div style={{ maxHeight: 100, overflowY: 'auto', marginBottom: 8 }}>
              {generatedPipeline.nodes.map((n: any, i: number) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 4,
                  padding: '2px 0',
                  fontFamily: F, fontSize: FS.xxs, color: T.dim,
                }}>
                  <ChevronRight size={7} />
                  <span style={{ color: T.sec }}>{n.data?.label || n.data?.type || 'Block'}</span>
                </div>
              ))}
            </div>
            <button
              onClick={handleApply}
              style={{
                width: '100%',
                padding: '6px 10px',
                background: `${T.cyan}20`,
                border: `1px solid ${T.cyan}60`,
                color: T.cyan,
                fontFamily: F,
                fontSize: FS.sm,
                fontWeight: 900,
                letterSpacing: '0.1em',
                cursor: 'pointer',
              }}
            >
              APPLY TO CANVAS
            </button>
          </div>
        )}
      </div>

      {/* Spin animation for loader */}
      <style>{`@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
