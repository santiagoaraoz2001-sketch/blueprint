import { useEffect, useRef } from 'react'
import { T, F, FD, FS } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { useProjectStore } from '@/stores/projectStore'
import { useMetricsStore } from '@/stores/metricsStore'
import { useDashboardMonitor } from '@/hooks/useRunMonitor'
import StatsBar from '@/components/Research/StatsBar'
import ActivityFeed from '@/components/Research/ActivityFeed'
import PaperSidebar from '@/components/Research/PaperSidebar'
import QuickStats from '@/components/Research/QuickStats'
import CreateProjectModal from '@/components/Projects/CreateProjectModal'
import EmptyState from '@/components/shared/EmptyState'
import { FlaskConical } from 'lucide-react'
import { useState } from 'react'

const REFRESH_INTERVAL = 60_000

export default function ResearchDashboardView() {
  const { setView, setSelectedProject } = useUIStore()
  const projects = useProjectStore((s) => s.projects)
  const fetchProjects = useProjectStore((s) => s.fetchProjects)
  const { dashboard, loading, fetchDashboard } = useMetricsStore()
  const [showCreateModal, setShowCreateModal] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // SSE subscription for live run updates
  useDashboardMonitor({ enabled: true })

  // Fetch on mount + periodic refresh for static stats
  useEffect(() => {
    fetchDashboard()
    fetchProjects()

    intervalRef.current = setInterval(() => {
      fetchDashboard()
    }, REFRESH_INTERVAL)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [fetchDashboard, fetchProjects])

  const handleSelectPaper = (id: string) => {
    setSelectedProject(id)
    setView('research-detail')
  }

  if (loading && !dashboard) {
    return (
      <div style={{ padding: 20, fontFamily: F, fontSize: FS.sm, color: T.dim }}>
        Loading research dashboard...
      </div>
    )
  }

  if (!dashboard) {
    return (
      <div style={{ padding: 20 }}>
        <EmptyState
          icon={FlaskConical}
          title="No research data"
          description="Start by creating a project and running experiments"
          action={{ label: 'New Project', onClick: () => setShowCreateModal(true) }}
        />
        {showCreateModal && <CreateProjectModal onClose={() => setShowCreateModal(false)} />}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{ padding: '16px 20px 0' }}>
        <h1
          style={{
            fontFamily: FD,
            fontSize: FS.xl * 1.5,
            fontWeight: 600,
            color: T.text,
            margin: 0,
            letterSpacing: '0.04em',
          }}
        >
          RESEARCH COMMAND CENTER
        </h1>
        <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, margin: '4px 0 0', letterSpacing: '0.02em' }}>
          Live overview of experiments, papers, and compute
        </p>
      </div>

      {/* Stats */}
      <div style={{ padding: '12px 20px' }}>
        <StatsBar stats={dashboard} />
      </div>

      {/* Main content: two-column */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          gap: 12,
          padding: '0 20px',
          overflow: 'hidden',
          minHeight: 0,
        }}
      >
        {/* Activity Feed — 65% */}
        <div
          style={{
            flex: 65,
            overflow: 'auto',
            paddingRight: 4,
          }}
        >
          <ActivityFeed dashboard={dashboard} />
        </div>

        {/* Paper Sidebar — 35% */}
        <div style={{ flex: 35, overflow: 'hidden' }}>
          <PaperSidebar
            projects={projects}
            onSelect={handleSelectPaper}
            onAdd={() => setShowCreateModal(true)}
          />
        </div>
      </div>

      {/* QuickStats bottom strip */}
      <QuickStats stats={dashboard} />

      {showCreateModal && <CreateProjectModal onClose={() => setShowCreateModal(false)} />}
    </div>
  )
}
