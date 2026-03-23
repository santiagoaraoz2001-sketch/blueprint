import { T, F, FS } from '@/lib/design-tokens'
import { File, Database, Box, FileText, Image, Activity } from 'lucide-react'
import type { ArtifactItem } from '@/hooks/useOutputs'

const TYPE_CONFIG: Record<string, { icon: typeof File; color: string }> = {
  dataset:    { icon: Database, color: T.cyan },
  model:      { icon: Box,     color: T.purple },
  adapter:    { icon: Box,     color: T.blue },
  log:        { icon: FileText, color: T.dim },
  figure:     { icon: Image,   color: T.pink },
  checkpoint: { icon: Activity, color: T.amber },
  metrics:    { icon: Activity, color: T.green },
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(i > 1 ? 1 : 0)} ${sizes[i]}`
}

export default function ArtifactRow({ artifact }: { artifact: ArtifactItem }) {
  const cfg = TYPE_CONFIG[artifact.artifact_type] || TYPE_CONFIG.log
  const Icon = cfg.icon

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '5px 0',
        transition: 'background 0.1s',
      }}
    >
      <Icon size={11} color={cfg.color} strokeWidth={1.5} style={{ flexShrink: 0 }} />

      <span style={{ fontFamily: F, fontSize: FS.xs, color: T.text, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {artifact.name}
      </span>

      <span
        style={{
          fontFamily: F,
          fontSize: FS.xxs,
          color: cfg.color,
          padding: '1px 6px',
          background: `${cfg.color}14`,
          border: `1px solid ${cfg.color}22`,
          flexShrink: 0,
          letterSpacing: '0.04em',
          textTransform: 'uppercase',
        }}
      >
        {artifact.artifact_type}
      </span>

      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, flexShrink: 0 }}>
        {formatBytes(artifact.size_bytes)}
      </span>

      {artifact.hash && (
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.muted,
            flexShrink: 0,
            opacity: 0.7,
          }}
          title={artifact.hash}
        >
          {artifact.hash.slice(0, 8)}
        </span>
      )}
    </div>
  )
}
