import { useState } from 'react'
import { T, F, FD, FS } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { api } from '@/api/client'
import PaperSidebar, { type PaperSummary } from '@/components/Research/PaperSidebar'
import ActivityFeed from '@/components/Research/ActivityFeed'
import { useQuery } from '@tanstack/react-query'

export default function ResearchDashboardView() {
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null)
  const setView = useUIStore((s) => s.setView)

  // Fetch papers
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.get<any[]>('/projects'),
  })

  // Fetch recent runs
  const { data: runs = [] } = useQuery({
    queryKey: ['runs-recent'],
    queryFn: () => api.get<any[]>('/runs?limit=50').catch(() => []),
  })

  const papers: PaperSummary[] = projects.map((p: any) => ({
    id: p.id,
    name: p.name,
    paperNumber: p.paper_number || null,
    status: p.status || 'active',
    phaseCount: 0,
    runCount: 0,
  }))

  const runSummaries = runs.map((r: any) => ({
    id: r.id,
    name: r.pipeline_name || r.name || r.id.substring(0, 8),
    pipelineId: r.pipeline_id,
    status: r.status,
    progress: r.progress || 0,
    eta: r.eta || null,
    errorMessage: r.error_message || null,
    completedAt: r.finished_at || r.completed_at,
    projectId: r.project_id || null,
  }))

  // Navigate to paper detail
  const handleSelectPaper = (id: string) => {
    setSelectedPaperId(id)
    setView('paperDetail' as any)
  }

  const blockedCount = projects.filter((p: any) => p.status === 'blocked').length
  const computeHours = runs.reduce((sum: number, r: any) => {
    if (r.started_at && r.finished_at) {
      const ms = new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()
      return sum + ms / 3600000
    }
    return sum
  }, 0)

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      {/* Sidebar */}
      <PaperSidebar
        papers={papers}
        selectedPaperId={selectedPaperId}
        onSelect={handleSelectPaper}
        onCreatePaper={() => setView('dashboard')}
      />

      {/* Main content */}
      <div style={{ flex: 1, overflow: 'auto', padding: 20 }}>
        <h1 style={{
          fontFamily: FD, fontSize: FS.xl * 1.5, fontWeight: 600,
          color: T.text, margin: 0, marginBottom: 6,
        }}>
          RESEARCH DASHBOARD
        </h1>
        <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, margin: '0 0 20px' }}>
          Live experiment feed and paper management
        </p>

        <ActivityFeed
          runs={runSummaries}
          stats={{ blockedCount, computeHours }}
        />
      </div>
    </div>
  )
}
