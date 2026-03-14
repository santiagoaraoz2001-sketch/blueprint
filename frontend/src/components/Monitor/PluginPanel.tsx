import { useRef, useEffect, useCallback, useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useSettingsStore } from '@/stores/settingsStore'
import type { PanelLayoutEntry } from '@/stores/settingsStore'
import { Settings, X, GripVertical, Maximize2, Minimize2 } from 'lucide-react'

/** Height in px per grid unit for plugin panel iframes */
const GRID_UNIT_HEIGHT = 200
/** Maximum grid-height units a panel can grow to */
const MAX_GRID_HEIGHT = 5

export interface PanelDef {
  id: string
  name: string
  plugin: string
  component_url: string
  default_size: { width: number; height: number }
  config_fields: { name: string; type: string; default?: unknown; label?: string }[]
}

interface PluginPanelProps {
  panel: PanelDef
  runId: string
  layout: PanelLayoutEntry
  onClose: (panelId: string) => void
  onDragStart?: (panelId: string) => void
  onIframeRef?: (panelId: string, el: HTMLIFrameElement | null) => void
}

export default function PluginPanel({ panel, runId, layout, onClose, onDragStart, onIframeRef }: PluginPanelProps) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null)
  const [showConfig, setShowConfig] = useState(false)
  const [configValues, setConfigValues] = useState<Record<string, unknown>>(layout.config || {})
  const setPanelLayout = useSettingsStore((s) => s.setPanelLayout)

  // Initialize config with defaults
  useEffect(() => {
    const initial: Record<string, unknown> = { ...layout.config }
    for (const field of panel.config_fields) {
      if (!(field.name in initial) && field.default !== undefined) {
        initial[field.name] = field.default
      }
    }
    setConfigValues(initial)
  }, [panel.config_fields, layout.config])

  // Forward run data to iframe via postMessage
  const sendToIframe = useCallback(
    (type: string, data: unknown) => {
      const target = iframeRef.current?.contentWindow
      if (!target) return
      // Use own origin for same-origin sandboxed iframes; fall back to '*' for
      // cross-origin plugin bundles served from different hosts.
      const origin = new URL(panel.component_url, window.location.origin).origin
      target.postMessage({ type, data }, origin)
    },
    [panel.component_url],
  )

  // Listen for SSE-like updates from the parent context and relay them
  useEffect(() => {
    // Send initial config to iframe once loaded
    const handleLoad = () => {
      sendToIframe('blueprint:config', {
        panel_id: panel.id,
        config: configValues,
        run_id: runId,
      })
    }
    const iframe = iframeRef.current
    iframe?.addEventListener('load', handleLoad)
    return () => iframe?.removeEventListener('load', handleLoad)
  }, [panel.id, configValues, runId, sendToIframe])

  // Listen for messages from the plugin iframe
  useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (event.source !== iframeRef.current?.contentWindow) return
      const msg = event.data
      if (msg?.type === 'plugin:action' && typeof msg.data === 'object' && msg.data !== null) {
        if (msg.data.action === 'open_url' && typeof msg.data.url === 'string') {
          // Only allow http/https URLs from plugins
          try {
            const parsed = new URL(msg.data.url)
            if (parsed.protocol === 'https:' || parsed.protocol === 'http:') {
              window.open(msg.data.url, '_blank', 'noopener,noreferrer')
            }
          } catch {
            // Ignore malformed URLs
          }
        }
      }
    }
    window.addEventListener('message', handler)
    return () => window.removeEventListener('message', handler)
  }, [])

  const handleSaveConfig = useCallback(() => {
    setPanelLayout(panel.id, { config: configValues })
    setShowConfig(false)
    // Notify iframe of config update
    sendToIframe('blueprint:config', {
      panel_id: panel.id,
      config: configValues,
      run_id: runId,
    })
  }, [panel.id, configValues, runId, setPanelLayout, sendToIframe])

  const handleResize = useCallback(
    (delta: 1 | -1) => {
      const newH = Math.max(1, Math.min(MAX_GRID_HEIGHT, layout.height + delta))
      setPanelLayout(panel.id, { height: newH })
    },
    [panel.id, layout.height, setPanelLayout],
  )

  return (
    <div
      style={{
        gridColumn: `span ${layout.width}`,
        border: `1px solid ${T.border}`,
        background: T.surface1,
        display: 'flex',
        flexDirection: 'column',
        minHeight: 0,
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '4px 8px',
          borderBottom: `1px solid ${T.border}`,
          background: T.surface2,
          flexShrink: 0,
        }}
      >
        <button
          onMouseDown={() => onDragStart?.(panel.id)}
          style={{
            background: 'none',
            border: 'none',
            color: T.dim,
            cursor: 'grab',
            padding: 0,
            display: 'flex',
            alignItems: 'center',
          }}
          title="Drag to reorder"
        >
          <GripVertical size={12} />
        </button>
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.sec,
            letterSpacing: '0.06em',
            flex: 1,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {panel.name}
        </span>
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.dim,
            background: T.surface3,
            padding: '1px 5px',
          }}
        >
          {panel.plugin}
        </span>

        <button
          onClick={() => handleResize(layout.height > 1 ? -1 : 1)}
          style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 0, display: 'flex' }}
          title={layout.height > 1 ? 'Shrink' : 'Expand'}
        >
          {layout.height > 1 ? <Minimize2 size={10} /> : <Maximize2 size={10} />}
        </button>

        {panel.config_fields.length > 0 && (
          <button
            onClick={() => setShowConfig(!showConfig)}
            style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 0, display: 'flex' }}
            title="Panel settings"
          >
            <Settings size={10} />
          </button>
        )}

        <button
          onClick={() => onClose(panel.id)}
          style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 0, display: 'flex' }}
          title="Hide panel"
        >
          <X size={10} />
        </button>
      </div>

      {/* Config form */}
      {showConfig && (
        <div style={{ padding: 8, borderBottom: `1px solid ${T.border}`, background: T.surface0 }}>
          {panel.config_fields.map((field) => (
            <label
              key={field.name}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                marginBottom: 4,
                fontFamily: F,
                fontSize: FS.xxs,
                color: T.sec,
              }}
            >
              <span style={{ minWidth: 80 }}>{field.label || field.name}</span>
              {field.type === 'boolean' ? (
                <input
                  type="checkbox"
                  checked={Boolean(configValues[field.name])}
                  onChange={(e) =>
                    setConfigValues((prev) => ({
                      ...prev,
                      [field.name]: e.target.checked,
                    }))
                  }
                  style={{ accentColor: T.cyan }}
                />
              ) : (
                <input
                  type={field.type === 'number' ? 'number' : 'text'}
                  value={String(configValues[field.name] ?? '')}
                  onChange={(e) =>
                    setConfigValues((prev) => ({
                      ...prev,
                      [field.name]: field.type === 'number' ? Number(e.target.value) : e.target.value,
                    }))
                  }
                  style={{
                    flex: 1,
                    background: T.surface3,
                    border: `1px solid ${T.border}`,
                    color: T.text,
                    fontFamily: F,
                    fontSize: FS.xxs,
                    padding: '2px 6px',
                    outline: 'none',
                  }}
                />
              )}
            </label>
          ))}
          <button
            onClick={handleSaveConfig}
            style={{
              marginTop: 4,
              padding: '3px 10px',
              background: `${T.cyan}22`,
              border: `1px solid ${T.cyan}44`,
              color: T.cyan,
              fontFamily: F,
              fontSize: FS.xxs,
              cursor: 'pointer',
            }}
          >
            Save
          </button>
        </div>
      )}

      {/* Iframe */}
      <div style={{ flex: 1, minHeight: layout.height * GRID_UNIT_HEIGHT }}>
        <iframe
          ref={(el) => {
            iframeRef.current = el
            onIframeRef?.(panel.id, el)
          }}
          src={panel.component_url}
          title={panel.name}
          sandbox="allow-scripts allow-same-origin"
          style={{
            width: '100%',
            height: '100%',
            border: 'none',
            background: T.bg,
          }}
        />
      </div>
    </div>
  )
}
