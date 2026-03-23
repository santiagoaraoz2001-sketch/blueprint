import PanelCard from '@/components/shared/PanelCard'
import StatusBadge from '@/components/shared/StatusBadge'
import { T, F, FD, FS, STATUS_COLORS } from '@/lib/design-tokens'
import type { Project } from '@/stores/projectStore'
import { Clock } from 'lucide-react'

interface ProjectCardProps {
  project: Project
  onClick: () => void
}

export default function ProjectCard({ project, onClick }: ProjectCardProps) {
  const accent = STATUS_COLORS[project.status] || T.dim
  const updatedDate = new Date(project.updated_at).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  })

  return (
    <PanelCard
      title={project.paper_number || undefined}
      accent={accent}
      onClick={onClick}
      style={{ minHeight: 120 }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '2px 2px' }}>
        {/* Name */}
        <span
          style={{
            fontFamily: FD,
            fontSize: FS.xl,
            fontWeight: 700,
            color: T.text,
            letterSpacing: '0.03em',
          }}
        >
          {project.name}
        </span>

        {/* Description */}
        {project.description && (
          <span
            style={{
              fontFamily: F,
              fontSize: FS.sm,
              color: T.dim,
              lineHeight: 1.5,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
            }}
          >
            {project.description}
          </span>
        )}

        {/* Tags */}
        {project.tags.length > 0 && (
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {project.tags.map((tag) => (
              <span
                key={tag}
                style={{
                  padding: '1px 5px',
                  background: T.surface5,
                  border: `1px solid ${T.border}`,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  color: T.dim,
                }}
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        {/* Footer */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginTop: 'auto',
            paddingTop: 4,
          }}
        >
          <StatusBadge status={project.status} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <Clock size={8} color={T.dim} />
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
              {updatedDate}
            </span>
          </div>
        </div>
      </div>
    </PanelCard>
  )
}
