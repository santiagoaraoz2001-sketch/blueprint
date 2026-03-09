import { useState, useEffect, useCallback } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { api } from '@/api/client'
import {
  Package,
  CheckCircle2,
  XCircle,
  Download,
  RefreshCw,
  Loader2,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
} from 'lucide-react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PackageInfo {
  package: string
  installed: boolean
  version: string | null
}

interface BlockInfo {
  ready: boolean
  total_deps: number
  missing: string[]
  install_command: string | null
}

interface DependencyData {
  summary: {
    total_blocks: number
    ready_blocks: number
    missing_packages: string[]
    in_virtual_env: boolean
  }
  packages: Record<string, PackageInfo>
  blocks: Record<string, BlockInfo>
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function DependencyPanel() {
  const [data, setData] = useState<DependencyData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [installing, setInstalling] = useState<string | null>(null) // 'all' | package name | null
  const [installResult, setInstallResult] = useState<{
    success: boolean
    message: string
  } | null>(null)
  const [expandedBlocks, setExpandedBlocks] = useState<Set<string>>(new Set())

  const fetchDeps = useCallback(async () => {
    setLoading(true)
    setError(null)
    setInstallResult(null)
    try {
      const result = await api.get<DependencyData>('/system/dependencies')
      setData(result)
    } catch (e: any) {
      setError(e?.message || 'Failed to fetch dependencies')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchDeps()
  }, [fetchDeps])

  const installPackages = async (packages: string[]) => {
    const label = packages.length === 1 ? packages[0] : 'all'
    setInstalling(label)
    setInstallResult(null)
    try {
      const result = await api.post<{
        success: boolean
        stdout?: string
        stderr?: string
        error?: string
        installed?: string[]
      }>('/system/install', { packages })

      if (result.success) {
        setInstallResult({
          success: true,
          message: `Installed: ${(result.installed || []).join(', ')}`,
        })
        // Refresh deps after install
        await fetchDeps()
      } else {
        setInstallResult({
          success: false,
          message: result.error || result.stderr || 'Installation failed',
        })
      }
    } catch (e: any) {
      setInstallResult({
        success: false,
        message: e?.message || 'Installation request failed',
      })
    } finally {
      setInstalling(null)
    }
  }

  const toggleBlock = (block: string) => {
    setExpandedBlocks((prev) => {
      const next = new Set(prev)
      if (next.has(block)) next.delete(block)
      else next.add(block)
      return next
    })
  }

  // -----------------------------------------------------------------------
  // Render helpers
  // -----------------------------------------------------------------------

  const renderSkeleton = () => (
    <div style={{ padding: 16 }}>
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          style={{
            height: 32,
            borderRadius: 4,
            background: T.surface3,
            marginBottom: 8,
            animation: 'depPulse 1.5s ease-in-out infinite',
            animationDelay: `${i * 0.15}s`,
          }}
        />
      ))}
      <style>{`
        @keyframes depPulse {
          0%, 100% { opacity: 0.3; }
          50% { opacity: 0.7; }
        }
      `}</style>
    </div>
  )

  const missingPackages = data?.summary?.missing_packages || []
  const totalBlocks = data?.summary?.total_blocks || 0
  const readyBlocks = data?.summary?.ready_blocks || 0
  const allReady = totalBlocks > 0 && readyBlocks === totalBlocks

  return (
    <div
      style={{
        background: T.surface,
        border: `1px solid ${T.border}`,
        overflow: 'hidden',
        width: '100%',
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
          <Package size={11} color={T.cyan} />
          <span
            style={{
              fontFamily: F,
              fontSize: FS.xs,
              fontWeight: 900,
              letterSpacing: '0.1em',
              color: T.text,
            }}
          >
            DEPENDENCY HEALTH
          </span>
        </div>
        <button
          onClick={fetchDeps}
          disabled={loading}
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
            cursor: loading ? 'default' : 'pointer',
            fontWeight: 700,
            opacity: loading ? 0.5 : 1,
          }}
          title="Refresh dependency check"
        >
          <RefreshCw
            size={9}
            style={loading ? { animation: 'depSpin 1s linear infinite' } : undefined}
          />
          REFRESH
        </button>
      </div>

      {/* Body */}
      <div style={{ padding: '8px 12px' }}>
        {loading && !data ? (
          renderSkeleton()
        ) : error ? (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '12px 0',
            }}
          >
            <AlertTriangle size={14} color={T.red} />
            <span
              style={{
                fontFamily: F,
                fontSize: FS.sm,
                color: T.red,
              }}
            >
              {error}
            </span>
          </div>
        ) : data ? (
          <>
            {/* Summary bar */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '6px 0 10px',
                borderBottom: `1px solid ${T.border}`,
                marginBottom: 8,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {allReady ? (
                  <CheckCircle2 size={14} color={T.green} />
                ) : (
                  <AlertTriangle size={14} color={T.amber} />
                )}
                <span
                  style={{
                    fontFamily: F,
                    fontSize: FS.sm,
                    fontWeight: 700,
                    color: allReady ? T.green : T.amber,
                    letterSpacing: '0.04em',
                  }}
                >
                  {readyBlocks}/{totalBlocks} blocks ready
                </span>
              </div>
              {data.summary.in_virtual_env && (
                <span
                  style={{
                    fontFamily: F,
                    fontSize: FS.xxs,
                    color: T.dim,
                    background: T.surface3,
                    padding: '2px 6px',
                    borderRadius: 2,
                  }}
                >
                  venv
                </span>
              )}
            </div>

            {/* Missing packages */}
            {missingPackages.length > 0 && (
              <div style={{ marginBottom: 10 }}>
                <div
                  style={{
                    fontFamily: F,
                    fontSize: FS.xxs,
                    fontWeight: 700,
                    color: T.sec,
                    letterSpacing: '0.1em',
                    marginBottom: 6,
                    textTransform: 'uppercase',
                  }}
                >
                  Missing Packages ({missingPackages.length})
                </div>
                <div
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: 4,
                    marginBottom: 8,
                  }}
                >
                  {missingPackages.map((pkg) => (
                    <span
                      key={pkg}
                      style={{
                        fontFamily: F,
                        fontSize: FS.xxs,
                        color: T.red,
                        background: 'rgba(255,67,61,0.08)',
                        border: `1px solid rgba(255,67,61,0.2)`,
                        padding: '2px 6px',
                        borderRadius: 2,
                        cursor: 'pointer',
                      }}
                      onClick={() => installPackages([pkg])}
                      title={`Install ${pkg}`}
                    >
                      <XCircle
                        size={8}
                        style={{
                          display: 'inline',
                          verticalAlign: 'middle',
                          marginRight: 3,
                        }}
                      />
                      {pkg}
                    </span>
                  ))}
                </div>

                {/* Install All button */}
                <button
                  onClick={() => installPackages(missingPackages)}
                  disabled={!!installing}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 5,
                    padding: '5px 12px',
                    background: T.cyan,
                    border: 'none',
                    color: '#000',
                    fontFamily: F,
                    fontSize: FS.xs,
                    fontWeight: 800,
                    letterSpacing: '0.08em',
                    cursor: installing ? 'default' : 'pointer',
                    opacity: installing ? 0.6 : 1,
                    width: '100%',
                    justifyContent: 'center',
                  }}
                >
                  {installing === 'all' ? (
                    <>
                      <Loader2
                        size={11}
                        style={{ animation: 'depSpin 1s linear infinite' }}
                      />
                      INSTALLING...
                    </>
                  ) : (
                    <>
                      <Download size={11} />
                      INSTALL ALL MISSING
                    </>
                  )}
                </button>
              </div>
            )}

            {/* Install result message */}
            {installResult && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '6px 8px',
                  marginBottom: 8,
                  background: installResult.success
                    ? 'rgba(34,197,94,0.08)'
                    : 'rgba(255,67,61,0.08)',
                  border: `1px solid ${installResult.success ? 'rgba(34,197,94,0.2)' : 'rgba(255,67,61,0.2)'}`,
                  borderRadius: 2,
                }}
              >
                {installResult.success ? (
                  <CheckCircle2 size={11} color={T.green} />
                ) : (
                  <XCircle size={11} color={T.red} />
                )}
                <span
                  style={{
                    fontFamily: F,
                    fontSize: FS.xxs,
                    color: installResult.success ? T.green : T.red,
                    wordBreak: 'break-word',
                  }}
                >
                  {installResult.message}
                </span>
              </div>
            )}

            {/* Block list */}
            <div>
              <div
                style={{
                  fontFamily: F,
                  fontSize: FS.xxs,
                  fontWeight: 700,
                  color: T.sec,
                  letterSpacing: '0.1em',
                  marginBottom: 6,
                  textTransform: 'uppercase',
                }}
              >
                Blocks
              </div>
              {Object.entries(data.blocks)
                .sort(([, a], [, b]) => (a.ready === b.ready ? 0 : a.ready ? 1 : -1))
                .map(([blockName, info]) => {
                  const expanded = expandedBlocks.has(blockName)
                  return (
                    <div
                      key={blockName}
                      style={{
                        borderBottom: `1px solid ${T.border}`,
                      }}
                    >
                      <div
                        onClick={() => toggleBlock(blockName)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 6,
                          padding: '5px 0',
                          cursor: 'pointer',
                          userSelect: 'none',
                        }}
                      >
                        {expanded ? (
                          <ChevronDown size={10} color={T.dim} />
                        ) : (
                          <ChevronRight size={10} color={T.dim} />
                        )}
                        {info.ready ? (
                          <CheckCircle2 size={10} color={T.green} />
                        ) : (
                          <XCircle size={10} color={T.red} />
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
                          {blockName}
                        </span>
                        <span
                          style={{
                            fontFamily: F,
                            fontSize: FS.xxs,
                            color: info.ready ? T.dim : T.amber,
                          }}
                        >
                          {info.ready
                            ? `${info.total_deps} deps`
                            : `${info.missing.length} missing`}
                        </span>
                      </div>

                      {/* Expanded detail */}
                      {expanded && (
                        <div
                          style={{
                            padding: '4px 0 8px 22px',
                          }}
                        >
                          {info.missing.length > 0 && (
                            <div
                              style={{
                                display: 'flex',
                                flexWrap: 'wrap',
                                gap: 4,
                                marginBottom: 6,
                              }}
                            >
                              {info.missing.map((pkg) => (
                                <span
                                  key={pkg}
                                  style={{
                                    fontFamily: F,
                                    fontSize: FS.xxs,
                                    color: T.red,
                                    background: 'rgba(255,67,61,0.06)',
                                    padding: '1px 5px',
                                    borderRadius: 2,
                                  }}
                                >
                                  {pkg}
                                </span>
                              ))}
                            </div>
                          )}
                          {info.install_command && (
                            <div
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                gap: 6,
                              }}
                            >
                              <code
                                style={{
                                  fontFamily: F,
                                  fontSize: FS.xxs,
                                  color: T.dim,
                                  background: T.surface3,
                                  padding: '2px 6px',
                                  borderRadius: 2,
                                  flex: 1,
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                }}
                              >
                                {info.install_command}
                              </code>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  installPackages(info.missing)
                                }}
                                disabled={!!installing}
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 3,
                                  padding: '2px 8px',
                                  background: T.surface3,
                                  border: `1px solid ${T.border}`,
                                  color: T.sec,
                                  fontFamily: F,
                                  fontSize: FS.xxs,
                                  fontWeight: 700,
                                  letterSpacing: '0.06em',
                                  cursor: installing ? 'default' : 'pointer',
                                  opacity: installing ? 0.5 : 1,
                                  whiteSpace: 'nowrap',
                                }}
                              >
                                {installing === info.missing[0] ? (
                                  <Loader2
                                    size={8}
                                    style={{
                                      animation: 'depSpin 1s linear infinite',
                                    }}
                                  />
                                ) : (
                                  <Download size={8} />
                                )}
                                INSTALL
                              </button>
                            </div>
                          )}
                          {info.ready && (
                            <span
                              style={{
                                fontFamily: F,
                                fontSize: FS.xxs,
                                color: T.green,
                              }}
                            >
                              All {info.total_deps} dependencies satisfied
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
            </div>
          </>
        ) : null}
      </div>

      {/* Spin animation */}
      <style>{`
        @keyframes depSpin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
