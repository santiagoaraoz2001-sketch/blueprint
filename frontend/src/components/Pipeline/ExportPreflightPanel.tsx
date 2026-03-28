import { useEffect, useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { CheckCircle2, AlertTriangle, XCircle, Loader2, X, FileCode, FileJson, Package } from 'lucide-react'
import toast from 'react-hot-toast'

interface PreflightItem {
  label: string
  status: 'ok' | 'warning' | 'error'
  detail?: string
}

interface PreflightResult {
  can_export: boolean
  supported: PreflightItem[]
  warnings: PreflightItem[]
  blockers: PreflightItem[]
}

interface Props {
  open: boolean
  onClose: () => void
  pipelineId: string
}

export default function ExportPreflightPanel({ open, onClose, pipelineId }: Props) {
  const [preflight, setPreflight] = useState<PreflightResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !pipelineId) return
    setPreflight(null)
    setError(null)
    setLoading(true)

    const baseUrl = import.meta.env.VITE_API_URL || '/api'
    fetch(`${baseUrl}/pipelines/${pipelineId}/export/preflight`)
      .then(async (res) => {
        if (!res.ok) {
          const data = await res.json().catch(() => ({}))
          throw new Error(data.detail || 'Failed to run pre-flight check')
        }
        return res.json()
      })
      .then(setPreflight)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [open, pipelineId])

  const handleExport = async (format: 'python' | 'jupyter', bundle = false) => {
    setExporting(true)
    try {
      const baseUrl = import.meta.env.VITE_API_URL || '/api'
      const res = await fetch(`${baseUrl}/pipelines/${pipelineId}/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format, bundle }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail?.reasons?.join(', ') || data.detail || 'Export failed')
      }

      const blob = await res.blob()
      const ext = bundle ? 'zip' : format === 'jupyter' ? 'ipynb' : 'py'
      const filename = `pipeline_${pipelineId.substring(0, 8)}.${ext}`
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
      toast.success(`Downloaded ${filename}`)
      onClose()
    } catch (e: any) {
      toast.error(e.message || 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  if (!open) return null

  const statusIcon = (status: string) => {
    switch (status) {
      case 'ok': return <CheckCircle2 size={14} color={T.green} />
      case 'warning': return <AlertTriangle size={14} color={T.amber} />
      case 'error': return <XCircle size={14} color={T.red} />
      default: return null
    }
  }

  const statusColor = (status: string) => {
    switch (status) {
      case 'ok': return T.green
      case 'warning': return T.amber
      case 'error': return T.red
      default: return T.dim
    }
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: T.shadowHeavy,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: 520, maxWidth: '90vw', maxHeight: '85vh',
          background: T.surface1, border: `1px solid ${T.borderHi}`,
          borderRadius: 8, display: 'flex', flexDirection: 'column',
          overflow: 'hidden',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 16px', borderBottom: `1px solid ${T.border}`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <FileCode size={16} color={T.purple} />
            <span style={{ fontFamily: F, fontSize: FS.md, color: T.text, fontWeight: 700 }}>
              Export Pipeline
            </span>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 4 }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflow: 'auto', padding: '16px' }}>
          {loading && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 20, justifyContent: 'center' }}>
              <Loader2 size={16} color={T.cyan} style={{ animation: 'spin 1s linear infinite' }} />
              <span style={{ fontFamily: F, fontSize: FS.sm, color: T.sec }}>Running pre-flight checks...</span>
            </div>
          )}

          {error && (
            <div style={{
              padding: '10px 12px', background: `${T.red}14`,
              border: `1px solid ${T.red}33`, borderRadius: 4,
            }}>
              <span style={{ fontFamily: F, fontSize: FS.xs, color: T.red }}>{error}</span>
            </div>
          )}

          {preflight && (
            <>
              {/* Supported features */}
              <div style={{ marginBottom: 16 }}>
                <span style={{
                  fontFamily: F, fontSize: FS.xxs, color: T.dim,
                  fontWeight: 600, letterSpacing: '0.1em', display: 'block', marginBottom: 8,
                }}>
                  SUPPORTED
                </span>
                {preflight.supported.map((item, i) => (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '6px 0',
                  }}>
                    {statusIcon(item.status)}
                    <span style={{ fontFamily: F, fontSize: FS.xs, color: statusColor(item.status) }}>
                      {item.label}
                    </span>
                  </div>
                ))}
              </div>

              {/* Warnings */}
              <div style={{ marginBottom: 16 }}>
                <span style={{
                  fontFamily: F, fontSize: FS.xxs, color: T.dim,
                  fontWeight: 600, letterSpacing: '0.1em', display: 'block', marginBottom: 8,
                }}>
                  LIMITATIONS
                </span>
                {preflight.warnings.map((item, i) => (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '6px 0',
                  }}>
                    {statusIcon(item.status)}
                    <span style={{ fontFamily: F, fontSize: FS.xs, color: statusColor(item.status) }}>
                      {item.label}
                    </span>
                  </div>
                ))}
              </div>

              {/* Blockers */}
              {preflight.blockers.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <span style={{
                    fontFamily: F, fontSize: FS.xxs, color: T.dim,
                    fontWeight: 600, letterSpacing: '0.1em', display: 'block', marginBottom: 8,
                  }}>
                    BLOCKERS
                  </span>
                  {preflight.blockers.map((item, i) => (
                    <div key={i} style={{
                      display: 'flex', alignItems: 'flex-start', gap: 8,
                      padding: '6px 0',
                    }}>
                      {statusIcon(item.status)}
                      <div>
                        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.red, display: 'block' }}>
                          {item.label}
                        </span>
                        {item.detail && (
                          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, display: 'block', marginTop: 2 }}>
                            {item.detail}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer — export buttons */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
          gap: 8, padding: '12px 16px',
          borderTop: `1px solid ${T.border}`, background: T.surface1,
        }}>
          {preflight && !preflight.can_export && (
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.red, marginRight: 'auto' }}>
              Fix blockers above to enable export
            </span>
          )}
          <button
            onClick={() => handleExport('python')}
            disabled={!preflight?.can_export || exporting}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 14px',
              background: preflight?.can_export ? `${T.purple}14` : `${T.dim}14`,
              border: `1px solid ${preflight?.can_export ? `${T.purple}33` : `${T.dim}33`}`,
              color: preflight?.can_export ? T.purple : T.dim,
              fontFamily: F, fontSize: FS.xs, letterSpacing: '0.06em',
              cursor: preflight?.can_export ? 'pointer' : 'not-allowed',
              borderRadius: 4, opacity: preflight?.can_export ? 1 : 0.5,
            }}
          >
            {exporting ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <FileCode size={12} />}
            PYTHON (.py)
          </button>
          <button
            onClick={() => handleExport('jupyter')}
            disabled={!preflight?.can_export || exporting}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 14px',
              background: preflight?.can_export ? `${T.amber}14` : `${T.dim}14`,
              border: `1px solid ${preflight?.can_export ? `${T.amber}33` : `${T.dim}33`}`,
              color: preflight?.can_export ? T.amber : T.dim,
              fontFamily: F, fontSize: FS.xs, letterSpacing: '0.06em',
              cursor: preflight?.can_export ? 'pointer' : 'not-allowed',
              borderRadius: 4, opacity: preflight?.can_export ? 1 : 0.5,
            }}
          >
            {exporting ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <FileJson size={12} />}
            JUPYTER (.ipynb)
          </button>
          <button
            onClick={() => handleExport('python', true)}
            disabled={!preflight?.can_export || exporting}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 14px',
              background: preflight?.can_export ? `${T.green}14` : `${T.dim}14`,
              border: `1px solid ${preflight?.can_export ? `${T.green}33` : `${T.dim}33`}`,
              color: preflight?.can_export ? T.green : T.dim,
              fontFamily: F, fontSize: FS.xs, letterSpacing: '0.06em',
              cursor: preflight?.can_export ? 'pointer' : 'not-allowed',
              borderRadius: 4, opacity: preflight?.can_export ? 1 : 0.5,
            }}
          >
            {exporting ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <Package size={12} />}
            BUNDLE (.zip)
          </button>
        </div>
      </div>
    </div>
  )
}
