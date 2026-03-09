import { useState } from 'react'
import { T, F, FD, FS } from '@/lib/design-tokens'
import { useProjectStore } from '@/stores/projectStore'
import { X } from 'lucide-react'
import toast from 'react-hot-toast'

interface CreateProjectModalProps {
  onClose: () => void
}

export default function CreateProjectModal({ onClose }: CreateProjectModalProps) {
  const createProject = useProjectStore((s) => s.createProject)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [paperNumber, setPaperNumber] = useState('')
  const [githubRepo, setGithubRepo] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async () => {
    if (!name.trim()) return
    setLoading(true)
    try {
      await createProject({
        name: name.trim(),
        description: description.trim(),
        paper_number: paperNumber.trim() || null,
        github_repo: githubRepo.trim() || null,
        status: 'planning',
      })
      toast.success('Project created')
      onClose()
    } catch (e: any) {
      toast.error(e?.message || 'Failed to create project — is the backend running?')
    } finally {
      setLoading(false)
    }
  }

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '6px 10px',
    background: T.surface4,
    border: `1px solid ${T.border}`,
    color: T.text,
    fontFamily: F,
    fontSize: FS.md,
    outline: 'none',
  }

  const labelStyle: React.CSSProperties = {
    fontFamily: F,
    fontSize: FS.xs,
    color: T.dim,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
    fontWeight: 600,
    marginBottom: 4,
    display: 'block',
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: T.shadowHeavy,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        style={{
          width: 420,
          background: T.surface2,
          border: `1px solid ${T.borderHi}`,
          borderTop: `2px solid ${T.cyan}`,
        }}
        className="animate-fadeSlideUp"
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '10px 14px',
            borderBottom: `1px solid ${T.border}`,
          }}
        >
          <span
            style={{
              fontFamily: FD,
              fontSize: FS.xl,
              fontWeight: 700,
              color: T.text,
              letterSpacing: '0.04em',
            }}
          >
            NEW PROJECT
          </span>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: T.dim, display: 'flex' }}
          >
            <X size={14} />
          </button>
        </div>

        {/* Form */}
        <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label style={labelStyle}>Project Name *</label>
            <input
              style={inputStyle}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., BALLAST Fine-Tuning"
              autoFocus
            />
          </div>

          <div>
            <label style={labelStyle}>Description</label>
            <textarea
              style={{ ...inputStyle, minHeight: 60, resize: 'vertical' }}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief description of the research project"
            />
          </div>

          <div style={{ display: 'flex', gap: 10 }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Paper Number</label>
              <input
                style={inputStyle}
                value={paperNumber}
                onChange={(e) => setPaperNumber(e.target.value)}
                placeholder="e.g., P1 PL"
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>GitHub Repo</label>
              <input
                style={inputStyle}
                value={githubRepo}
                onChange={(e) => setGithubRepo(e.target.value)}
                placeholder="owner/repo"
              />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 8,
            padding: '10px 14px',
            borderTop: `1px solid ${T.border}`,
          }}
        >
          <button
            onClick={onClose}
            style={{
              padding: '5px 14px',
              background: T.surface3,
              border: `1px solid ${T.border}`,
              color: T.sec,
              fontFamily: F,
              fontSize: FS.md,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!name.trim() || loading}
            style={{
              padding: '5px 14px',
              background: `${T.cyan}14`,
              border: `1px solid ${T.cyan}33`,
              color: T.cyan,
              fontFamily: F,
              fontSize: FS.md,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              opacity: !name.trim() || loading ? 0.5 : 1,
            }}
          >
            {loading ? 'Creating...' : 'Create Project'}
          </button>
        </div>
      </div>
    </div>
  )
}
