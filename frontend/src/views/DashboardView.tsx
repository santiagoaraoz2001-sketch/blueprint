import { useState } from 'react'
import { motion } from 'framer-motion'
import { T, F, FD, FS } from '@/lib/design-tokens'
import { useProjectStore } from '@/stores/projectStore'
import { useUIStore } from '@/stores/uiStore'
import ProjectCard from '@/components/Projects/ProjectCard'
import ProjectDetail from '@/components/Projects/ProjectDetail'
import CreateProjectModal from '@/components/Projects/CreateProjectModal'
import EmptyState from '@/components/shared/EmptyState'
import MetricDisplay from '@/components/shared/MetricDisplay'
import { LayoutDashboard, Plus, Search } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'

export default function DashboardView() {
  const { setProjects } = useProjectStore()
  const { selectedProjectId, setSelectedProject } = useUIStore()
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [search, setSearch] = useState('')

  const { data: projects = [], isLoading: loading } = useQuery({
    queryKey: ['projects'],
    queryFn: async () => {
      const data = await api.get<any[]>('/projects')
      // Sync with Zustand store so other parts of the app can still access it if needed
      setProjects(data)
      return data
    }
  })

  const selectedProject = projects.find((p) => p.id === selectedProjectId)

  // If a project is selected, show its detail view
  if (selectedProject) {
    return (
      <ProjectDetail
        project={selectedProject}
        onBack={() => setSelectedProject(null)}
      />
    )
  }

  const filtered = projects.filter(
    (p) =>
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      p.description.toLowerCase().includes(search.toLowerCase()) ||
      (p.paper_number || '').toLowerCase().includes(search.toLowerCase())
  )

  const activeCount = projects.filter((p) => p.status === 'active').length
  const completeCount = projects.filter((p) => p.status === 'complete').length

  return (
    <div style={{ padding: 20 }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
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
          RESEARCH WORKBENCH
        </h1>
        <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, margin: '6px 0 0', letterSpacing: '0.02em' }}>
          Manage local foundation models, pipelines, and evaluation runs
        </p>
      </div>

      {/* Stats bar */}
      {projects.length > 0 && (
        <div
          className="hover-glow"
          style={{
            display: 'flex',
            gap: 32,
            marginBottom: 24,
            padding: '12px 16px',
            background: T.surface1,
            border: `1px solid ${T.borderHi}`,
          }}
        >
          <MetricDisplay label="TOTAL ENTITIES" value={projects.length} accent={T.sec} />
          <MetricDisplay label="ACTIVE JOBS" value={activeCount} accent={T.cyan} />
          <MetricDisplay label="COMPLETED" value={completeCount} accent={T.green} />
        </div>
      )}

      {/* Action bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
        <div
          className="hover-glow"
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '8px 12px',
            background: T.surface0,
            border: `1px solid ${T.borderHi}`,
          }}
        >
          <Search size={12} color={T.dim} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search projects by ID, layout, or meta-data..."
            style={{
              flex: 1,
              background: 'none',
              border: 'none',
              color: T.text,
              fontFamily: F,
              fontSize: FS.sm,
              outline: 'none',
            }}
          />
        </div>
        <button
          className="hover-glow"
          onClick={() => setShowCreateModal(true)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '8px 16px',
            background: `${T.cyan}1A`,
            border: `1px solid ${T.cyan}50`,
            color: T.cyan,
            fontFamily: F,
            fontSize: FS.sm,
            fontWeight: 600,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            whiteSpace: 'nowrap',
          }}
        >
          <Plus size={14} />
          Initialize Project
        </button>
      </div>

      {/* Project grid */}
      {filtered.length > 0 ? (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: 10,
          }}
        >
          {filtered.map((project, i) => (
            <motion.div
              key={project.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05, duration: 0.3, ease: 'easeOut' }}
            >
              <ProjectCard
                project={project}
                onClick={() => setSelectedProject(project.id)}
              />
            </motion.div>
          ))}
        </div>
      ) : loading ? (
        <div style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, padding: 20, textAlign: 'center' }}>
          Loading projects...
        </div>
      ) : (
        <EmptyState
          icon={LayoutDashboard}
          title="No projects yet"
          description="Create your first research project to get started"
          action={{ label: 'New Project', onClick: () => setShowCreateModal(true) }}
        />
      )}

      {showCreateModal && (
        <CreateProjectModal onClose={() => setShowCreateModal(false)} />
      )}
    </div>
  )
}
