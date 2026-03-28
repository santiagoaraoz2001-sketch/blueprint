import { useState, useEffect } from 'react'
import { T, F } from '@/lib/design-tokens'
import { api } from '@/api/client'
import {
  X, Server, Cloud, FileType, Globe, ArrowRight, ArrowLeft,
  CheckCircle, AlertCircle, Loader2, Info,
} from 'lucide-react'
import toast from 'react-hot-toast'

interface DeployTargets {
  ollama: { cli_available: boolean; server_running: boolean }
  huggingface: { available: boolean; install_command?: string }
  onnx: { available: boolean; has_optimum: boolean; install_command?: string }
  server: { available: boolean }
}

interface DeployModalProps {
  modelId: string
  modelName: string
  modelFormat: string
  modelPath: string | null
  onClose: () => void
}

type Target = 'ollama' | 'huggingface' | 'onnx' | 'server'
type Step = 'select' | 'config' | 'progress'

const TARGET_INFO: Record<Target, { icon: typeof Server; label: string; description: string; color: string }> = {
  ollama: { icon: Server, label: 'Ollama', description: 'Register model with local Ollama for inference', color: '#FF8C4A' },
  huggingface: { icon: Cloud, label: 'HuggingFace', description: 'Push model and card to HuggingFace Hub', color: '#FFD21E' },
  onnx: { icon: FileType, label: 'ONNX', description: 'Convert model to ONNX format for cross-platform inference', color: '#3EF07A' },
  server: { icon: Globe, label: 'API Server', description: 'Generate a standalone FastAPI inference server', color: '#5B96FF' },
}

export default function DeployModal({ modelId, modelName, modelFormat, modelPath, onClose }: DeployModalProps) {
  const t = T()
  const [step, setStep] = useState<Step>('select')
  const [target, setTarget] = useState<Target | null>(null)
  const [targets, setTargets] = useState<DeployTargets | null>(null)
  const [deploying, setDeploying] = useState(false)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Config state
  const [ollamaName, setOllamaName] = useState(modelName.toLowerCase().replace(/\s+/g, '-'))
  const [hfRepoId, setHfRepoId] = useState('')
  const [hfToken, setHfToken] = useState('')
  const [hfPrivate, setHfPrivate] = useState(true)
  const [hfUseSaved, setHfUseSaved] = useState(false)
  const [hfHasSaved, setHfHasSaved] = useState(false)
  const [hfSaveToken, setHfSaveToken] = useState(false)
  const [onnxPath, setOnnxPath] = useState('')
  const [serverDir, setServerDir] = useState('')

  useEffect(() => {
    api.get<DeployTargets>('/models/deploy/targets')
      .then(setTargets)
      .catch(() => toast.error('Failed to check deploy targets'))
    // Check if HF_TOKEN is saved in the secrets store
    api.get<{ secrets: string[] }>('/secrets')
      .then((data) => {
        if (data.secrets?.includes('HF_TOKEN')) {
          setHfHasSaved(true)
          setHfUseSaved(true) // Default to using saved token when available
        }
      })
      .catch(() => {}) // Non-critical
  }, [])

  const handleDeploy = async () => {
    if (!target) return
    setDeploying(true)
    setError(null)
    setResult(null)
    setStep('progress')

    try {
      let body: Record<string, unknown> = {}
      if (target === 'ollama') {
        body = { model_name: ollamaName }
      } else if (target === 'huggingface') {
        // Use the secrets store reference or the literal token
        const tokenValue = hfUseSaved ? '$secret:HF_TOKEN' : hfToken
        body = { repo_id: hfRepoId, hf_token: tokenValue, private: hfPrivate }
      } else if (target === 'onnx') {
        body = { output_path: onnxPath }
      } else if (target === 'server') {
        body = { output_dir: serverDir }
      }

      const res = await api.post<Record<string, unknown>>(
        `/models/${modelId}/deploy/${target}`,
        body,
        { timeoutMs: 300_000 },
      )
      setResult(res)

      // After successful HF deploy: save the token if requested, then clear from state
      if (target === 'huggingface') {
        if (hfSaveToken && hfToken && !hfUseSaved) {
          try {
            await api.post('/secrets/HF_TOKEN', { value: hfToken })
            setHfHasSaved(true)
            toast.success('HF token saved to secrets store')
          } catch {
            // Non-critical — deploy already succeeded
          }
        }
        // Clear the token from React state immediately after use
        setHfToken('')
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Deploy failed'
      setError(msg)
    } finally {
      setDeploying(false)
    }
  }

  const isTargetDisabled = (t: Target): string | null => {
    if (!targets) return 'Loading...'
    if (t === 'ollama') {
      if (!targets.ollama.cli_available) return 'Ollama not installed. Install from https://ollama.com'
      if (!targets.ollama.server_running) return 'Ollama server is not running. Start it with "ollama serve"'
      if (!modelPath) return 'Model has no file path'
    }
    if (t === 'huggingface' && !targets.huggingface.available) {
      return `huggingface_hub not installed. Run: ${targets.huggingface.install_command}`
    }
    if (t === 'onnx' && !targets.onnx.available) {
      return `PyTorch not installed. Run: ${targets.onnx.install_command}`
    }
    return null
  }

  // ── Render ────────────────────────────────────────────────────────

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
    }} onClick={onClose}>
      <div
        style={{
          background: t.bg, border: `1px solid ${t.border}`, borderRadius: 12,
          width: 520, maxHeight: '80vh', overflow: 'auto',
          boxShadow: t.shadowHeavy,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{
          padding: '14px 16px', borderBottom: `1px solid ${t.border}`,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span style={{ ...F.sm, fontWeight: 700, color: t.text }}>
            Deploy — {modelName}
          </span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: t.dim, padding: 4 }}>
            <X size={16} />
          </button>
        </div>

        <div style={{ padding: 16 }}>
          {/* Step 1: Select target */}
          {step === 'select' && (
            <div>
              <p style={{ ...F.xs, color: t.dim, marginTop: 0, marginBottom: 12 }}>
                Select a deployment target for this model
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {(Object.keys(TARGET_INFO) as Target[]).map((key) => {
                  const info = TARGET_INFO[key]
                  const Icon = info.icon
                  const disabledReason = isTargetDisabled(key)
                  const disabled = disabledReason !== null
                  return (
                    <button
                      key={key}
                      disabled={disabled}
                      onClick={() => { setTarget(key); setStep('config') }}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 12,
                        padding: '12px 14px', borderRadius: 8,
                        border: `1px solid ${disabled ? t.border : t.borderHi}`,
                        background: disabled ? t.surface2 : t.surface,
                        cursor: disabled ? 'not-allowed' : 'pointer',
                        opacity: disabled ? 0.5 : 1,
                        textAlign: 'left', transition: 'border-color 0.15s',
                      }}
                    >
                      <div style={{
                        width: 36, height: 36, borderRadius: 8,
                        background: `${info.color}18`, display: 'flex',
                        alignItems: 'center', justifyContent: 'center',
                      }}>
                        <Icon size={18} style={{ color: info.color }} />
                      </div>
                      <div style={{ flex: 1 }}>
                        <div style={{ ...F.sm, fontWeight: 600, color: disabled ? t.dim : t.text }}>{info.label}</div>
                        <div style={{ ...F.xs, color: t.dim, marginTop: 2 }}>
                          {disabled ? disabledReason : info.description}
                        </div>
                      </div>
                      {!disabled && <ArrowRight size={14} style={{ color: t.dim }} />}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {/* Step 2: Target-specific config */}
          {step === 'config' && target && (
            <div>
              <button
                onClick={() => setStep('select')}
                style={{
                  ...F.xs, display: 'flex', alignItems: 'center', gap: 4,
                  color: t.cyan, background: 'none', border: 'none', cursor: 'pointer',
                  padding: '4px 0', marginBottom: 12, fontWeight: 500,
                }}
              >
                <ArrowLeft size={14} /> Back
              </button>

              <h3 style={{ ...F.sm, fontWeight: 600, color: t.text, marginTop: 0, marginBottom: 12 }}>
                Configure {TARGET_INFO[target].label} Export
              </h3>

              {target === 'ollama' && (
                <div>
                  <Label text="Model Name" />
                  <Input value={ollamaName} onChange={setOllamaName} placeholder="my-model" />
                  <Hint text="Name used to reference the model in Ollama (e.g. 'ollama run my-model')" />
                </div>
              )}

              {target === 'huggingface' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div>
                    <Label text="Repository ID" />
                    <Input value={hfRepoId} onChange={setHfRepoId} placeholder="username/model-name" />
                  </div>
                  <div>
                    <Label text="HuggingFace Token" />
                    {hfHasSaved && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                        <input
                          type="checkbox" checked={hfUseSaved}
                          onChange={(e) => setHfUseSaved(e.target.checked)}
                          style={{ accentColor: t.cyan }}
                        />
                        <span style={{ ...F.xs, color: t.green }}>
                          Use saved token from secrets store
                        </span>
                      </div>
                    )}
                    {!hfUseSaved && (
                      <>
                        <Input value={hfToken} onChange={setHfToken} placeholder="hf_..." type="password" />
                        <Hint text="Write-access token from huggingface.co/settings/tokens. Cleared from memory after deploy." />
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
                          <input
                            type="checkbox" checked={hfSaveToken}
                            onChange={(e) => setHfSaveToken(e.target.checked)}
                            style={{ accentColor: t.cyan }}
                          />
                          <span style={{ ...F.xs, color: t.sec }}>
                            Save token to encrypted secrets store for future use
                          </span>
                        </div>
                      </>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input
                      type="checkbox" checked={hfPrivate}
                      onChange={(e) => setHfPrivate(e.target.checked)}
                      style={{ accentColor: t.cyan }}
                    />
                    <span style={{ ...F.xs, color: t.sec }}>Private repository</span>
                  </div>
                </div>
              )}

              {target === 'onnx' && (
                <div>
                  <Label text="Output Path" />
                  <Input value={onnxPath} onChange={setOnnxPath} placeholder="/path/to/model.onnx" />
                  <Hint text="Where to save the converted ONNX file" />
                </div>
              )}

              {target === 'server' && (
                <div>
                  <Label text="Output Directory" />
                  <Input value={serverDir} onChange={setServerDir} placeholder="/path/to/server/" />
                  <Hint text="Directory where server.py, requirements.txt, and Dockerfile will be generated" />
                </div>
              )}

              <button
                onClick={handleDeploy}
                disabled={!isConfigValid(target, { ollamaName, hfRepoId, hfToken, hfUseSaved, onnxPath, serverDir })}
                style={{
                  ...F.sm, marginTop: 16, padding: '10px 20px', borderRadius: 8,
                  background: t.cyan, color: t.bg, border: 'none',
                  cursor: 'pointer', fontWeight: 600, width: '100%',
                  opacity: isConfigValid(target, { ollamaName, hfRepoId, hfToken, hfUseSaved, onnxPath, serverDir }) ? 1 : 0.5,
                }}
              >
                Deploy to {TARGET_INFO[target].label}
              </button>
            </div>
          )}

          {/* Step 3: Progress / Result */}
          {step === 'progress' && (
            <div style={{ textAlign: 'center', padding: '20px 0' }}>
              {deploying && (
                <>
                  <Loader2 size={32} style={{ color: t.cyan, animation: 'spin 1s linear infinite', marginBottom: 12 }} />
                  <p style={{ ...F.sm, color: t.text, margin: 0 }}>Deploying to {target ? TARGET_INFO[target].label : ''}...</p>
                  <p style={{ ...F.xs, color: t.dim, marginTop: 4 }}>This may take a few minutes</p>
                  <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
                </>
              )}

              {!deploying && result && (
                <>
                  <CheckCircle size={32} style={{ color: t.green, marginBottom: 12 }} />
                  <p style={{ ...F.sm, fontWeight: 600, color: t.green, margin: 0 }}>Deploy Successful</p>
                  <div style={{
                    marginTop: 12, textAlign: 'left', background: t.surface2,
                    borderRadius: 8, padding: 12,
                  }}>
                    {result.model_name && (
                      <ResultRow label="Model Name" value={String(result.model_name)} />
                    )}
                    {result.url && (
                      <ResultRow label="URL" value={String(result.url)} isLink />
                    )}
                    {result.path && (
                      <ResultRow label="Path" value={String(result.path)} />
                    )}
                    {result.output_dir && (
                      <ResultRow label="Output" value={String(result.output_dir)} />
                    )}
                    {result.size != null && (
                      <ResultRow label="Size" value={formatSize(Number(result.size))} />
                    )}
                    {result.files && (
                      <ResultRow label="Files" value={(result.files as string[]).join(', ')} />
                    )}
                    {result.message && (
                      <ResultRow label="Info" value={String(result.message)} />
                    )}
                  </div>
                  <button
                    onClick={onClose}
                    style={{
                      ...F.sm, marginTop: 16, padding: '8px 20px', borderRadius: 8,
                      background: t.cyan, color: t.bg, border: 'none',
                      cursor: 'pointer', fontWeight: 600,
                    }}
                  >
                    Done
                  </button>
                </>
              )}

              {!deploying && error && (
                <>
                  <AlertCircle size={32} style={{ color: t.red, marginBottom: 12 }} />
                  <p style={{ ...F.sm, fontWeight: 600, color: t.red, margin: 0 }}>Deploy Failed</p>
                  <div style={{
                    marginTop: 12, background: `${t.red}11`, border: `1px solid ${t.red}33`,
                    borderRadius: 8, padding: 12, textAlign: 'left',
                  }}>
                    <p style={{ ...F.xs, color: t.red, margin: 0, whiteSpace: 'pre-wrap' }}>{error}</p>
                  </div>
                  <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 16 }}>
                    <button
                      onClick={() => { setStep('config'); setError(null) }}
                      style={{
                        ...F.sm, padding: '8px 16px', borderRadius: 8,
                        background: 'none', color: t.sec, border: `1px solid ${t.border}`,
                        cursor: 'pointer', fontWeight: 500,
                      }}
                    >
                      Back
                    </button>
                    <button
                      onClick={handleDeploy}
                      style={{
                        ...F.sm, padding: '8px 16px', borderRadius: 8,
                        background: t.cyan, color: t.bg, border: 'none',
                        cursor: 'pointer', fontWeight: 600,
                      }}
                    >
                      Retry
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}


// ── Helpers ──────────────────────────────────────────────────────────

function isConfigValid(
  target: Target,
  cfg: {
    ollamaName: string; hfRepoId: string; hfToken: string;
    hfUseSaved: boolean; onnxPath: string; serverDir: string
  },
): boolean {
  switch (target) {
    case 'ollama': return cfg.ollamaName.trim().length > 0
    case 'huggingface':
      return cfg.hfRepoId.includes('/') && (cfg.hfUseSaved || cfg.hfToken.trim().length > 0)
    case 'onnx': return cfg.onnxPath.trim().length > 0
    case 'server': return cfg.serverDir.trim().length > 0
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function Label({ text }: { text: string }) {
  const t = T()
  return <label style={{ ...F.xs, color: t.sec, fontWeight: 600, display: 'block', marginBottom: 4 }}>{text}</label>
}

function Input({ value, onChange, placeholder, type = 'text' }: {
  value: string; onChange: (v: string) => void; placeholder: string; type?: string
}) {
  const t = T()
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      style={{
        ...F.xs, width: '100%', padding: '8px 10px', borderRadius: 6,
        border: `1px solid ${t.border}`, background: t.surface2,
        color: t.text, outline: 'none', fontFamily: 'JetBrains Mono, monospace',
        boxSizing: 'border-box',
      }}
    />
  )
}

function Hint({ text }: { text: string }) {
  const t = T()
  return (
    <div style={{ ...F.xs, color: t.dim, marginTop: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
      <Info size={10} /> {text}
    </div>
  )
}

function ResultRow({ label, value, isLink }: { label: string; value: string; isLink?: boolean }) {
  const t = T()
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: `1px solid ${t.border}22` }}>
      <span style={{ ...F.xs, color: t.dim }}>{label}</span>
      {isLink ? (
        <a
          href={value}
          target="_blank"
          rel="noopener noreferrer"
          style={{ ...F.xs, color: t.cyan, textDecoration: 'none', fontFamily: 'JetBrains Mono, monospace' }}
        >
          {value}
        </a>
      ) : (
        <span style={{
          ...F.xs, color: t.text, fontFamily: 'JetBrains Mono, monospace',
          maxWidth: '60%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {value}
        </span>
      )}
    </div>
  )
}
