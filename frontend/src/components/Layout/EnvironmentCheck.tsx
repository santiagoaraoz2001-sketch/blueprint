import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { T, F, FS } from '@/lib/design-tokens'
import { CheckCircle2, AlertTriangle, XCircle, X, Cpu, RefreshCw } from 'lucide-react'
import { api } from '@/api/client'
import { LLM_DEFAULTS } from '@/lib/llm-prompts'

interface EnvItem {
  label: string
  status: 'ok' | 'warn' | 'error'
  detail: string
}

const STORAGE_KEY = 'blueprint_env_checked'

const statusIcon = (status: EnvItem['status'], size = 12) => {
  switch (status) {
    case 'ok':
      return <CheckCircle2 size={size} color={T.green} />
    case 'warn':
      return <AlertTriangle size={size} color={T.amber} />
    case 'error':
      return <XCircle size={size} color={T.red} />
  }
}

const statusColor = (status: EnvItem['status']) => {
  switch (status) {
    case 'ok': return T.green
    case 'warn': return T.amber
    case 'error': return T.red
  }
}

function SkeletonRow() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0' }}>
      <div
        style={{
          width: 12,
          height: 12,
          borderRadius: '50%',
          background: T.surface4,
          animation: 'pulse 1.5s ease-in-out infinite',
        }}
      />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 3 }}>
        <div
          style={{
            width: '40%',
            height: 8,
            borderRadius: 2,
            background: T.surface4,
            animation: 'pulse 1.5s ease-in-out infinite',
          }}
        />
        <div
          style={{
            width: '65%',
            height: 6,
            borderRadius: 2,
            background: T.surface3,
            animation: 'pulse 1.5s ease-in-out infinite',
            animationDelay: '0.2s',
          }}
        />
      </div>
    </div>
  )
}

interface EnvironmentCheckProps {
  onDismiss: () => void
}

export default function EnvironmentCheck({ onDismiss }: EnvironmentCheckProps) {
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(STORAGE_KEY) === '1'
  )
  const [items, setItems] = useState<EnvItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (dismissed) return
    checkEnvironment()
  }, [dismissed])

  async function checkEnvironment() {
    setLoading(true)
    const results: EnvItem[] = []

    // Check backend connectivity
    try {
      await api.get<{ status: string }>('/health')
      results.push({
        label: 'Backend Server',
        status: 'ok',
        detail: 'Running and connected',
      })
    } catch {
      results.push({
        label: 'Backend Server',
        status: 'error',
        detail: 'Not connected \u2014 start the backend',
      })
    }

    // Check hardware/capabilities from the backend
    try {
      const caps = await api.get<any>('/system/capabilities')

      // GPU
      results.push({
        label: 'GPU Acceleration',
        status: caps.gpu_available ? 'ok' : 'warn',
        detail: caps.gpu_available
          ? `${caps.gpu_backend} detected`
          : 'CPU only \u2014 GPU recommended for training',
      })

      // Memory
      const memGB = caps.usable_memory_gb ?? 0
      results.push({
        label: 'Memory',
        status: memGB > 4 ? 'ok' : 'warn',
        detail: `${memGB}GB available`,
      })

      // Disk
      results.push({
        label: 'Disk Space',
        status: caps.disk_ok ? 'ok' : 'warn',
        detail: caps.disk_ok ? 'Sufficient' : 'Low disk space',
      })

      // Python
      if (caps.python_version) {
        results.push({
          label: 'Python',
          status: 'ok',
          detail: `v${caps.python_version}`,
        })
      }

      // Pip packages
      if (caps.pip_packages) {
        const count = Array.isArray(caps.pip_packages)
          ? caps.pip_packages.length
          : typeof caps.pip_packages === 'number'
            ? caps.pip_packages
            : 0
        results.push({
          label: 'Pip Packages',
          status: count > 0 ? 'ok' : 'warn',
          detail: count > 0 ? `${count} installed` : 'None detected',
        })
      }
    } catch {
      results.push({
        label: 'Hardware Detection',
        status: 'warn',
        detail: 'Could not detect \u2014 backend may not be running',
      })
    }

    // Check Ollama
    try {
      const resp = await fetch(`${LLM_DEFAULTS.endpoints.ollama}/api/tags`, {
        signal: AbortSignal.timeout(3000),
      })
      if (resp.ok) {
        const data = await resp.json()
        const count = data.models?.length ?? 0
        results.push({
          label: 'Ollama',
          status: 'ok',
          detail: `Running (${count} model${count !== 1 ? 's' : ''})`,
        })
      } else {
        results.push({
          label: 'Ollama',
          status: 'warn',
          detail: 'Not running \u2014 install from ollama.ai for local LLMs',
        })
      }
    } catch {
      results.push({
        label: 'Ollama',
        status: 'warn',
        detail: 'Not detected \u2014 optional for local LLM inference',
      })
    }

    setItems(results)
    setLoading(false)
  }

  const dismiss = () => {
    localStorage.setItem(STORAGE_KEY, '1')
    setDismissed(true)
    onDismiss()
  }

  if (dismissed) return null

  const errorCount = items.filter((i) => i.status === 'error').length
  const warnCount = items.filter((i) => i.status === 'warn').length
  const okCount = items.filter((i) => i.status === 'ok').length

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.25 }}
        style={{
          background: T.surface,
          border: `1px solid ${T.borderHi}`,
          padding: 0,
          width: 340,
          overflow: 'hidden',
          boxShadow: `0 4px 24px ${T.shadowLight}`,
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '8px 12px',
            borderBottom: `1px solid ${T.border}`,
            background: T.surface1,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Cpu size={11} color={T.cyan} />
            <span
              style={{
                fontFamily: F,
                fontSize: FS.xs,
                fontWeight: 900,
                letterSpacing: '0.1em',
                color: T.text,
              }}
            >
              ENVIRONMENT CHECK
            </span>
          </div>
          <button
            onClick={dismiss}
            style={{
              background: 'none',
              border: 'none',
              color: T.dim,
              cursor: 'pointer',
              padding: 2,
              display: 'flex',
              alignItems: 'center',
            }}
            title="Dismiss"
          >
            <X size={12} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '8px 12px' }}>
          {loading ? (
            <>
              <SkeletonRow />
              <SkeletonRow />
              <SkeletonRow />
              <SkeletonRow />
              <style>{`
                @keyframes pulse {
                  0%, 100% { opacity: 0.4; }
                  50% { opacity: 0.8; }
                }
              `}</style>
            </>
          ) : (
            items.map((item, i) => (
              <div
                key={item.label}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 8,
                  padding: '5px 0',
                  borderBottom:
                    i < items.length - 1
                      ? `1px solid ${T.border}`
                      : 'none',
                }}
              >
                <div style={{ paddingTop: 1 }}>
                  {statusIcon(item.status)}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontFamily: F,
                      fontSize: FS.sm,
                      fontWeight: 700,
                      color: T.text,
                      letterSpacing: '0.04em',
                    }}
                  >
                    {item.label}
                  </div>
                  <div
                    style={{
                      fontFamily: F,
                      fontSize: FS.xxs,
                      color: statusColor(item.status),
                      marginTop: 1,
                      lineHeight: 1.3,
                    }}
                  >
                    {item.detail}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        {!loading && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '6px 12px',
              borderTop: `1px solid ${T.border}`,
              background: T.surface1,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {okCount > 0 && (
                <span
                  style={{
                    fontFamily: F,
                    fontSize: FS.xxs,
                    color: T.green,
                    fontWeight: 700,
                  }}
                >
                  {okCount} OK
                </span>
              )}
              {warnCount > 0 && (
                <span
                  style={{
                    fontFamily: F,
                    fontSize: FS.xxs,
                    color: T.amber,
                    fontWeight: 700,
                  }}
                >
                  {warnCount} WARN
                </span>
              )}
              {errorCount > 0 && (
                <span
                  style={{
                    fontFamily: F,
                    fontSize: FS.xxs,
                    color: T.red,
                    fontWeight: 700,
                  }}
                >
                  {errorCount} ERROR
                </span>
              )}
            </div>

            <div style={{ display: 'flex', gap: 6 }}>
              <button
                onClick={() => checkEnvironment()}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '3px 8px',
                  background: 'transparent',
                  border: `1px solid ${T.border}`,
                  color: T.dim,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  letterSpacing: '0.08em',
                  cursor: 'pointer',
                  fontWeight: 700,
                }}
                title="Re-check environment"
              >
                <RefreshCw size={9} />
                RECHECK
              </button>

              <button
                onClick={dismiss}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '3px 8px',
                  background: T.surface3,
                  border: `1px solid ${T.border}`,
                  color: T.sec,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  letterSpacing: '0.08em',
                  cursor: 'pointer',
                  fontWeight: 700,
                }}
              >
                DISMISS
              </button>
            </div>
          </div>
        )}
      </motion.div>
    </AnimatePresence>
  )
}
