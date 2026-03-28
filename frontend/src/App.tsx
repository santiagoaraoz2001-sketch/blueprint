import { useRef, useEffect, useState, useMemo, lazy, Suspense } from 'react'
import ErrorBoundary from '@/components/shared/ErrorBoundary'
import AppShell from '@/components/Layout/AppShell'
import CommandPalette from '@/components/shared/CommandPalette'
import StartScreen from '@/components/Layout/StartScreen'
import WelcomeModal from '@/components/Layout/WelcomeModal'
import SplashScreen from '@/components/Layout/SplashScreen'
import OnboardingWizard from '@/components/Onboarding/OnboardingWizard'
import { useUIStore } from '@/stores/uiStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useAutoSave } from '@/hooks/useAutoSave'
import { injectThemeCSSVars } from '@/lib/design-tokens'
import DashboardView from '@/views/DashboardView'
import PipelineEditorView from '@/views/PipelineEditorView'
import ResultsView from '@/views/ResultsView'
import DatasetView from '@/views/DatasetView'
const MarketplaceView = lazy(() => import('@/views/MarketplaceView'))
import SettingsView from '@/views/SettingsView'
import PaperView from '@/views/PaperView'
import WorkshopView from '@/views/WorkshopView'
import GlobalOutputsView from '@/views/GlobalOutputsView'
import DataView from '@/views/DataView'
import VisualizationView from '@/views/VisualizationView'
import ResearchDashboardView from '@/views/ResearchDashboardView'
import PaperDetailView from '@/views/PaperDetailView'
import MonitorView from '@/views/MonitorView'

// Lazy-loaded views
const HelpView = lazy(() => import('@/views/HelpView'))

const baseViewComponents: Record<string, React.ComponentType> = {
  dashboard: DashboardView,
  editor: PipelineEditorView,
  results: ResultsView,
  datasets: DatasetView,
  data: DataView,
  visualization: VisualizationView,
  output: GlobalOutputsView,
  workshop: WorkshopView,
  settings: SettingsView,
  paper: PaperView,
  help: HelpView,
  research: ResearchDashboardView,
  'research-detail': PaperDetailView,
  monitor: MonitorView,
}

function ViewTransition({ viewKey, children }: { viewKey: string; children: React.ReactNode }) {
  const [animClass, setAnimClass] = useState('')
  const prevKey = useRef(viewKey)

  useEffect(() => {
    if (prevKey.current !== viewKey) {
      prevKey.current = viewKey
      setAnimClass('view-enter')
      const timer = setTimeout(() => setAnimClass(''), 300)
      return () => clearTimeout(timer)
    }
  }, [viewKey])

  return (
    <div
      className={animClass}
      style={{ height: '100%' }}
    >
      {children}
    </div>
  )
}

export default function App() {
  const activeView = useUIStore((s) => s.activeView)
  // Subscribe to theme + font so the entire tree re-renders on change
  // Subscribe to theme + font + fontSize to trigger re-render on change
  const theme = useSettingsStore((s) => s.theme)
  useSettingsStore((s) => s.font)
  useSettingsStore((s) => s.fontSize)
  const features = useSettingsStore((s) => s.features)
  useKeyboardShortcuts()
  useAutoSave()

  // Fetch feature flags on startup
  useEffect(() => {
    useSettingsStore.getState().fetchFeatures()
  }, [])

  // Build view map based on enabled features
  const viewComponents = useMemo(() => {
    const views = { ...baseViewComponents }
    if (features?.marketplace) {
      views.marketplace = MarketplaceView
    }
    return views
  }, [features?.marketplace])

  // One-time migration: update custom blocks in localStorage from old taxonomy
  useEffect(() => {
    const KEY = 'blueprint-custom-blocks'
    const MIGRATED_KEY = 'blueprint-taxonomy-v2-migrated'
    if (localStorage.getItem(MIGRATED_KEY)) return
    try {
      const raw = localStorage.getItem(KEY)
      if (raw) {
        const blocks = JSON.parse(raw)
        const catMap: Record<string, string> = { data: 'source', evaluation: 'evaluate', output: 'flow', utility: 'flow' }
        const portMap: Record<string, string> = { dataset: 'data', text: 'data', config: 'data', agent: 'data', artifact: 'data' }
        const migrated = blocks.map((b: any) => ({
          ...b,
          category: catMap[b.category] || b.category,
          inputs: b.inputs?.map((p: any) => ({ ...p, dataType: portMap[p.dataType] || p.dataType })),
          outputs: b.outputs?.map((p: any) => ({ ...p, dataType: portMap[p.dataType] || p.dataType })),
        }))
        localStorage.setItem(KEY, JSON.stringify(migrated))
      }
    } catch { /* ignore parse errors */ }
    localStorage.setItem(MIGRATED_KEY, '1')
  }, [])

  // Inject CSS variables whenever theme changes
  useEffect(() => {
    injectThemeCSSVars(theme)
  }, [theme])

  // Handle URL params for monitor popout and deep linking
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const view = params.get('view')
    const runId = params.get('runId')
    const compareRuns = params.get('runs')

    if (view === 'monitor' && runId) {
      useUIStore.getState().openMonitor(runId)
    } else if (view === 'monitor' && compareRuns) {
      useUIStore.getState().openComparison(compareRuns.split(','))
    }
  }, [])

  const ViewComponent = viewComponents[activeView] || ResearchDashboardView

  return (
    <SplashScreen>
      <AppShell>
        <ErrorBoundary fallbackLabel={`${activeView} view crashed`} key={activeView}>
          <Suspense fallback={<div style={{ height: '100%' }} />}>
            <ViewTransition viewKey={activeView}>
              <ViewComponent />
            </ViewTransition>
          </Suspense>
        </ErrorBoundary>
      </AppShell>
      <CommandPalette />
      <StartScreen />
      <WelcomeModal />
      <OnboardingWizard />
    </SplashScreen>
  )
}
