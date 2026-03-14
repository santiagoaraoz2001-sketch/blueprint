import { useState, useEffect, useCallback, useRef } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { api } from '@/api/client'
import { useSettingsStore } from '@/stores/settingsStore'
import { useMetricsStore } from '@/stores/metricsStore'
import { useUIStore } from '@/stores/uiStore'
import PluginPanel from './PluginPanel'
import type { PanelDef } from './PluginPanel'
import { Puzzle, RefreshCw } from 'lucide-react'

interface PluginPanelContainerProps {
  runId: string
}

export default function PluginPanelContainer({ runId }: PluginPanelContainerProps) {
  const [panels, setPanels] = useState<PanelDef[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const panelLayouts = useSettingsStore((s) => s.panelLayouts)
  const setPanelLayout = useSettingsStore((s) => s.setPanelLayout)
  const features = useSettingsStore((s) => s.features)
  const iframeRefs = useRef<Map<string, HTMLIFrameElement>>(new Map())

  // Stable ref callback for PluginPanel to register its iframe
  const registerIframeRef = useCallback((panelId: string, el: HTMLIFrameElement | null) => {
    if (el) {
      iframeRefs.current.set(panelId, el)
    } else {
      iframeRefs.current.delete(panelId)
    }
  }, [])

  // Fetch panel definitions from backend
  const fetchPanels = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<{ panels: PanelDef[] }>('/plugins/panels')
      setPanels(res.panels)
      // Initialize layout entries for new panels using fresh store state
      const currentLayouts = useSettingsStore.getState().panelLayouts
      for (const panel of res.panels) {
        if (!currentLayouts[panel.id]) {
          setPanelLayout(panel.id, {
            panelId: panel.id,
            order: Object.keys(currentLayouts).length,
            width: panel.default_size.width,
            height: panel.default_size.height,
            visible: true,
            config: {},
          })
        }
      }
    } catch (e: any) {
      setError(e.message || 'Failed to load plugin panels')
    } finally {
      setLoading(false)
    }
  }, [setPanelLayout])

  useEffect(() => {
    fetchPanels()
  }, [fetchPanels])

  // Forward metric events to all plugin iframes
  const runMetrics = useMetricsStore((s) => s.runs[runId])
  const prevMetricsRef = useRef(runMetrics)

  useEffect(() => {
    if (!runMetrics || runMetrics === prevMetricsRef.current) return
    prevMetricsRef.current = runMetrics

    const payload = {
      run_id: runId,
      status: runMetrics.status,
      progress: runMetrics.overallProgress,
      metrics: runMetrics.blocks,
    }

    for (const [panelId, iframe] of iframeRefs.current) {
      const panel = panels.find((p) => p.id === panelId)
      const origin = panel
        ? new URL(panel.component_url, window.location.origin).origin
        : window.location.origin
      iframe.contentWindow?.postMessage(
        { type: 'blueprint:run_update', data: payload },
        origin,
      )
    }
  }, [runId, runMetrics, panels])

  const handleClose = useCallback(
    (panelId: string) => {
      setPanelLayout(panelId, { visible: false })
    },
    [setPanelLayout],
  )

  const handleBrowsePlugins = useCallback(() => {
    useUIStore.getState().setView('marketplace')
  }, [])

  // Sort panels by stored order
  const visiblePanels = panels
    .filter((p) => panelLayouts[p.id]?.visible !== false)
    .sort((a, b) => (panelLayouts[a.id]?.order ?? 0) - (panelLayouts[b.id]?.order ?? 0))

  if (loading) return null

  // Error takes priority over empty state
  if (error) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 14px',
          margin: '0 12px 8px',
          background: `${T.red}0a`,
          border: `1px solid ${T.red}22`,
        }}
      >
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.red, flex: 1 }}>{error}</span>
        <button
          onClick={fetchPanels}
          style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 0, display: 'flex' }}
          title="Retry loading plugins"
        >
          <RefreshCw size={11} />
        </button>
      </div>
    )
  }

  // No plugins installed — show callout
  if (panels.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '10px 14px',
          margin: '0 12px 8px',
          background: `${T.cyan}08`,
          border: `1px solid ${T.cyan}22`,
        }}
      >
        <Puzzle size={14} color={T.cyan} />
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec, flex: 1 }}>
          Want more monitoring tools? Install plugins for W&B, TensorBoard, and more.
        </span>
        {features?.marketplace && (
          <button
            onClick={handleBrowsePlugins}
            style={{
              padding: '3px 10px',
              background: `${T.cyan}18`,
              border: `1px solid ${T.cyan}33`,
              color: T.cyan,
              fontFamily: F,
              fontSize: FS.xxs,
              letterSpacing: '0.06em',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            Browse Plugins
          </button>
        )}
      </div>
    )
  }

  if (visiblePanels.length === 0) {
    // Panels exist but all hidden — show restore hint
    const hiddenCount = panels.length
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '6px 14px',
          margin: '0 12px 8px',
        }}
      >
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          {hiddenCount} plugin panel{hiddenCount > 1 ? 's' : ''} hidden
        </span>
        <button
          onClick={() => {
            for (const p of panels) {
              setPanelLayout(p.id, { visible: true })
            }
          }}
          style={{
            padding: '2px 8px',
            background: 'transparent',
            border: `1px solid ${T.border}`,
            color: T.sec,
            fontFamily: F,
            fontSize: FS.xxs,
            cursor: 'pointer',
          }}
        >
          Show all
        </button>
      </div>
    )
  }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(2, 1fr)',
        gap: 8,
        padding: '8px 12px',
      }}
    >
      {visiblePanels.map((panel) => (
        <PluginPanel
          key={panel.id}
          panel={panel}
          runId={runId}
          layout={
            panelLayouts[panel.id] || {
              panelId: panel.id,
              order: 0,
              width: panel.default_size.width,
              height: panel.default_size.height,
              visible: true,
              config: {},
            }
          }
          onClose={handleClose}
          onIframeRef={registerIframeRef}
        />
      ))}
    </div>
  )
}
