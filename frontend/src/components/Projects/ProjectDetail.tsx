import { T, F, FD, FS, STATUS_COLORS } from '@/lib/design-tokens'
import { useUIStore } from '@/stores/uiStore'
import { useProjectStore, type Project } from '@/stores/projectStore'
import { usePipelineStore } from '@/stores/pipelineStore'
import { usePaperStore } from '@/stores/paperStore'
import { useEffect, useState } from 'react'
import StatusBadge from '@/components/shared/StatusBadge'
import EmptyState from '@/components/shared/EmptyState'
import { ArrowLeft, GitBranch, Plus, Trash2, FileText } from 'lucide-react'
import toast from 'react-hot-toast'

interface ProjectDetailProps {
  project: Project
  onBack: () => void
}

export default function ProjectDetail({ project, onBack }: ProjectDetailProps) {
  const setView = useUIStore((s) => s.setView)
  const updateProject = useProjectStore((s) => s.updateProject)
  const deleteProject = useProjectStore((s) => s.deleteProject)

  const accent = STATUS_COLORS[project.status] || T.dim

  const pipelines = usePipelineStore((s) => s.pipelines)
  const fetchPipelines = usePipelineStore((s) => s.fetchPipelines)
  const loadPipeline = usePipelineStore((s) => s.loadPipeline)
  const newPipeline = usePipelineStore((s) => s.newPipeline)
  const deletePipeline = usePipelineStore((s) => s.deletePipeline)

  const [papers, setPapers] = useState<any[]>([])
  const fetchProjectPapers = usePaperStore((s) => s.fetchProjectPapers)
  const loadPaper = usePaperStore((s) => s.loadPaper)
  const deletePaper = usePaperStore((s) => s.deletePaper)
  const setPaperProjectId = usePaperStore((s) => s.setProjectId)
  const resetPaper = usePaperStore((s) => s.resetPaper)

  const loadData = async () => {
    fetchPipelines()
    const p = await fetchProjectPapers(project.id)
    setPapers(p)
  }

  useEffect(() => {
    loadData()
  }, [project.id, fetchPipelines])

  const handleDelete = async () => {
    await deleteProject(project.id)
    toast.success('Project deleted')
    onBack()
  }

  const handleStatusChange = async (status: string) => {
    await updateProject(project.id, { status })
  }

  const handleCreatePipeline = () => {
    newPipeline()
    setView('editor')
  }

  const handleOpenPipeline = async (id: string) => {
    await loadPipeline(id)
    setView('editor')
  }

  const handleCreatePaper = () => {
    resetPaper()
    setPaperProjectId(project.id)
    setView('paper')
  }

  const handleOpenPaper = async (id: string) => {
    await loadPaper(id)
    setView('paper')
  }

  const handleDeletePaper = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    await deletePaper(id)
    loadData()
  }

  return (
    <div style={{ padding: 20 }}>
      {/* Back nav */}
      <button
        onClick={onBack}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          background: 'none',
          border: 'none',
          color: T.dim,
          fontFamily: F,
          fontSize: FS.md,
          marginBottom: 16,
          padding: 0,
          transition: 'color 0.15s',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.color = T.sec)}
        onMouseLeave={(e) => (e.currentTarget.style.color = T.dim)}
      >
        <ArrowLeft size={12} />
        BACK TO PROJECTS
      </button>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <h1
              style={{
                fontFamily: FD,
                fontSize: FS.h2,
                fontWeight: 700,
                color: T.text,
                margin: 0,
                letterSpacing: '0.04em',
              }}
            >
              {project.name}
            </h1>
            <StatusBadge status={project.status} size="md" />
            {project.paper_number && (
              <span style={{ fontFamily: F, fontSize: FS.xs, color: accent, fontWeight: 600 }}>
                {project.paper_number}
              </span>
            )}
          </div>
          {project.description && (
            <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, margin: '6px 0 0' }}>
              {project.description}
            </p>
          )}
        </div>

        <div style={{ display: 'flex', gap: 6 }}>
          {/* Status selector */}
          <select
            value={project.status}
            onChange={(e) => handleStatusChange(e.target.value)}
            style={{
              padding: '4px 8px',
              background: T.surface3,
              border: `1px solid ${T.border}`,
              color: T.sec,
              fontFamily: F,
              fontSize: FS.xs,
            }}
          >
            <option value="planning">Planning</option>
            <option value="active">Active</option>
            <option value="complete">Complete</option>
            <option value="paused">Paused</option>
          </select>

          <button
            onClick={handleDelete}
            style={{
              padding: '4px 8px',
              background: `${T.red}14`,
              border: `1px solid ${T.red}33`,
              color: T.red,
              fontFamily: F,
              fontSize: FS.xs,
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            <Trash2 size={10} />
            DELETE
          </button>
        </div>
      </div>

      {/* Pipelines section */}
      <div
        style={{
          borderTop: `1px solid ${T.border}`,
          paddingTop: 16,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <span
            style={{
              fontFamily: F,
              fontSize: FS.xs,
              color: T.dim,
              letterSpacing: '0.14em',
              textTransform: 'uppercase',
              fontWeight: 900,
            }}
          >
            PIPELINES
          </span>
          <button
            onClick={handleCreatePipeline}
            style={{
              padding: '4px 10px',
              background: `${T.cyan}14`,
              border: `1px solid ${T.cyan}33`,
              color: T.cyan,
              fontFamily: F,
              fontSize: FS.xs,
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              letterSpacing: '0.08em',
            }}
          >
            <Plus size={10} />
            NEW PIPELINE
          </button>
        </div>

        {pipelines.length === 0 ? (
          <EmptyState
            icon={GitBranch}
            title="No pipelines yet"
            description="Create a pipeline to start building experiments"
            action={{ label: 'Create Pipeline', onClick: handleCreatePipeline }}
          />
        ) : (
          <div style={{ display: 'grid', gap: 8 }}>
            {pipelines.map((p: any) => (
              <div
                key={p.id}
                onClick={() => handleOpenPipeline(p.id)}
                className="hover-glow"
                style={{
                  padding: '12px 16px',
                  background: T.surface1,
                  border: `1px solid ${T.borderHi}`,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between'
                }}
              >
                <div>
                  <div style={{ fontFamily: FD, fontSize: FS.sm, color: T.text, fontWeight: 600 }}>{p.name}</div>
                  <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, marginTop: 4 }}>
                    {p.block_count} blocks • Updated {new Date(p.updated_at).toLocaleDateString()}
                  </div>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); deletePipeline(p.id) }}
                  style={{
                    padding: '4px 8px',
                    background: 'none',
                    border: `1px solid transparent`,
                    color: T.dim,
                    fontFamily: F,
                    fontSize: FS.xs,
                    transition: 'all 0.2s'
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.color = T.red; e.currentTarget.style.borderColor = T.red }}
                  onMouseLeave={(e) => { e.currentTarget.style.color = T.dim; e.currentTarget.style.borderColor = 'transparent' }}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Papers section */}
      <div
        style={{
          borderTop: `1px solid ${T.border}`,
          paddingTop: 16,
          marginTop: 20,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <span
            style={{
              fontFamily: F,
              fontSize: FS.xs,
              color: T.dim,
              letterSpacing: '0.14em',
              textTransform: 'uppercase',
              fontWeight: 900,
            }}
          >
            PAPERS
          </span>
          <button
            onClick={handleCreatePaper}
            style={{
              padding: '4px 10px',
              background: `${T.purple}14`,
              border: `1px solid ${T.purple}33`,
              color: T.purple,
              fontFamily: F,
              fontSize: FS.xs,
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              letterSpacing: '0.08em',
            }}
          >
            <Plus size={10} />
            NEW PAPER
          </button>
        </div>

        {papers.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="No papers yet"
            description="Create a paper linked to this project"
            action={{ label: 'Create Paper', onClick: handleCreatePaper }}
          />
        ) : (
          <div style={{ display: 'grid', gap: 8 }}>
            {papers.map((p: any) => (
              <div
                key={p.id}
                onClick={() => handleOpenPaper(p.id)}
                className="hover-glow"
                style={{
                  padding: '12px 16px',
                  background: T.surface0,
                  border: `1px solid ${T.border}`,
                  borderRadius: 6,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  transition: 'all 0.2s',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ padding: 6, background: `${T.purple}1a`, borderRadius: 4 }}>
                    <FileText size={14} color={T.purple} />
                  </div>
                  <div>
                    <div
                      style={{
                        fontFamily: F,
                        fontSize: FS.sm,
                        color: T.text,
                        fontWeight: 600,
                        letterSpacing: '0.02em',
                      }}
                    >
                      {p.name}
                    </div>
                    <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 4 }}>
                      Updated {new Date(p.updated_at).toLocaleDateString()}
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <button
                    onClick={(e) => handleDeletePaper(e, p.id)}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: T.dim,
                      cursor: 'pointer',
                      padding: 4,
                      transition: 'color 0.15s',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.color = T.red)}
                    onMouseLeave={(e) => (e.currentTarget.style.color = T.dim)}
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
