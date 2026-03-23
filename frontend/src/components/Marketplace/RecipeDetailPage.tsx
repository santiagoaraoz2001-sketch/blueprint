import { useMemo } from 'react'
import { T, F, FS, FD } from '@/lib/design-tokens'
import { BLOCK_REGISTRY, type BlockDefinition } from '@/lib/block-registry'
import type { Recipe } from '@/lib/recipes'
import { getIcon } from '@/lib/icon-utils'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useUIStore } from '@/stores/uiStore'
import { motion } from 'framer-motion'
import {
  ArrowLeft,
  PlusCircle,
  Layers,
  GitBranch,
  User,
  Tag,
  Zap,
  Settings,
} from 'lucide-react'
import toast from 'react-hot-toast'

interface RecipeDetailPageProps {
  recipe: Recipe
  onBack: () => void
  onSelectBlock?: (block: BlockDefinition) => void
}

export default function RecipeDetailPage({ recipe, onBack, onSelectBlock }: RecipeDetailPageProps) {
  const applyGeneratedWorkflow = usePipelineStore((s) => s.applyGeneratedWorkflow)

  // Resolve block definitions for the nodes in this recipe
  const recipeBlocks = useMemo(() => {
    const blocks: { nodeId: string; label: string; blockDef: BlockDefinition | null; accent: string; icon: string }[] = []
    for (const node of recipe.nodes) {
      const def = BLOCK_REGISTRY.find((b) => b.type === node.data.type) || null
      blocks.push({
        nodeId: node.id,
        label: node.data.label,
        blockDef: def,
        accent: node.data.accent || def?.accent || T.cyan,
        icon: node.data.icon || def?.icon || 'Box',
      })
    }
    return blocks
  }, [recipe])

  // Compute categories used
  const categoriesUsed = useMemo(() => {
    const cats = new Set<string>()
    for (const node of recipe.nodes) {
      cats.add(node.data.category)
    }
    return Array.from(cats)
  }, [recipe])

  // Compute pipeline bounding box for SVG preview
  const pipelinePreview = useMemo(() => {
    if (recipe.nodes.length === 0) return null

    const positions = recipe.nodes.map((n) => n.position)
    const minX = Math.min(...positions.map((p) => p.x))
    const minY = Math.min(...positions.map((p) => p.y))
    const maxX = Math.max(...positions.map((p) => p.x))
    const maxY = Math.max(...positions.map((p) => p.y))

    const nodeWidth = 140
    const nodeHeight = 40
    const padding = 40
    const viewWidth = maxX - minX + nodeWidth + padding * 2
    const viewHeight = maxY - minY + nodeHeight + padding * 2

    // Normalize positions
    const normalizedNodes = recipe.nodes.map((n) => ({
      id: n.id,
      label: n.data.label,
      x: n.position.x - minX + padding,
      y: n.position.y - minY + padding,
      accent: recipeBlocks.find((b) => b.nodeId === n.id)?.accent || T.cyan,
      icon: recipeBlocks.find((b) => b.nodeId === n.id)?.icon || 'Box',
    }))

    // Build edge connections using node positions
    const edgeLines = recipe.edges.map((e) => {
      const srcNode = normalizedNodes.find((n) => n.id === e.source)
      const tgtNode = normalizedNodes.find((n) => n.id === e.target)
      if (!srcNode || !tgtNode) return null
      return {
        id: e.id,
        x1: srcNode.x + nodeWidth / 2,
        y1: srcNode.y + nodeHeight,
        x2: tgtNode.x + nodeWidth / 2,
        y2: tgtNode.y,
      }
    }).filter(Boolean) as { id: string; x1: number; y1: number; x2: number; y2: number }[]

    return { viewWidth, viewHeight, nodes: normalizedNodes, edges: edgeLines, nodeWidth, nodeHeight }
  }, [recipe, recipeBlocks])

  const handleInstall = () => {
    const idSuffix = '_' + Date.now()
    const newNodes = recipe.nodes.map((n) => ({ ...n, id: n.id + idSuffix }))
    const newEdges = recipe.edges.map((e) => ({
      ...e,
      id: e.id + idSuffix,
      source: e.source + idSuffix,
      target: e.target + idSuffix,
    }))
    applyGeneratedWorkflow(newNodes, newEdges)
    useUIStore.getState().setView('editor')
    toast.success(`Installed recipe: ${recipe.name}`)
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: 40 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -40 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Back Navigation */}
      <button
        onClick={onBack}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '10px 20px',
          background: 'none',
          border: 'none',
          color: T.cyan,
          fontFamily: F,
          fontSize: FS.sm,
          fontWeight: 600,
          cursor: 'pointer',
          letterSpacing: '0.04em',
          flexShrink: 0,
          transition: 'color 0.15s',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.color = T.text)}
        onMouseLeave={(e) => (e.currentTarget.style.color = T.cyan)}
      >
        <ArrowLeft size={12} />
        Back to Recipes
      </button>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflow: 'auto', padding: '0 24px 24px' }}>
        {/* Hero Banner */}
        <div
          style={{
            background: `linear-gradient(180deg, ${T.surface2} 0%, ${T.surface0} 100%)`,
            border: `1px solid ${T.border}`,
            borderTop: `4px solid ${T.cyan}`,
            borderRadius: '0 0 8px 8px',
            padding: '24px 28px',
            marginBottom: 24,
            backdropFilter: 'blur(12px)',
            boxShadow: `0 8px 32px ${T.shadow}, 0 0 60px ${T.cyan}08`,
          }}
        >
          <h2
            style={{
              margin: 0,
              fontFamily: FD,
              fontSize: FS.h2,
              color: T.text,
              fontWeight: 700,
              letterSpacing: '0.02em',
            }}
          >
            {recipe.name}
          </h2>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 10, flexWrap: 'wrap' }}>
            {/* Tags */}
            {recipe.tags.map((tag) => (
              <span
                key={tag}
                style={{
                  padding: '2px 8px',
                  background: T.surface3,
                  borderRadius: 10,
                  fontSize: FS.xxs,
                  fontFamily: F,
                  color: T.sec,
                  border: `1px solid ${T.border}`,
                }}
              >
                {tag}
              </span>
            ))}

            {/* Author */}
            {recipe.author && (
              <span
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  color: T.dim,
                }}
              >
                <User size={9} />
                {recipe.author}
              </span>
            )}

            {/* Version */}
            {recipe.version && (
              <span
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  color: T.dim,
                }}
              >
                <Tag size={9} />
                v{recipe.version}
              </span>
            )}
          </div>
        </div>

        {/* Two-column layout */}
        <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
          {/* Main Column (65%) */}
          <div style={{ flex: '0 0 65%', maxWidth: '65%', display: 'flex', flexDirection: 'column', gap: 24 }}>
            {/* Description */}
            <Section title="DESCRIPTION">
              <p
                style={{
                  fontFamily: F,
                  fontSize: FS.sm,
                  color: T.sec,
                  lineHeight: 1.7,
                  margin: 0,
                }}
              >
                {recipe.longDescription || recipe.description}
              </p>
            </Section>

            {/* How It Works (Walkthrough) */}
            {recipe.walkthrough && recipe.walkthrough.length > 0 && (
              <Section title="HOW IT WORKS">
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {recipe.walkthrough.map((step, i) => (
                    <div
                      key={i}
                      style={{
                        display: 'flex',
                        gap: 12,
                        padding: '10px 14px',
                        background: T.surface0,
                        border: `1px solid ${T.border}`,
                        borderRadius: 6,
                        transition: 'all 0.15s',
                      }}
                    >
                      <div
                        style={{
                          width: 24,
                          height: 24,
                          borderRadius: '50%',
                          background: `${T.cyan}18`,
                          border: `1px solid ${T.cyan}40`,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontFamily: FD,
                          fontSize: FS.xs,
                          color: T.cyan,
                          fontWeight: 700,
                          flexShrink: 0,
                        }}
                      >
                        {i + 1}
                      </div>
                      <p
                        style={{
                          fontFamily: F,
                          fontSize: FS.sm,
                          color: T.sec,
                          lineHeight: 1.6,
                          margin: 0,
                        }}
                      >
                        {step}
                      </p>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Blocks Included */}
            <Section title="BLOCKS INCLUDED">
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
                  gap: 8,
                }}
              >
                {recipeBlocks.map(({ nodeId, label, blockDef, accent, icon }) => {
                  const BlockIcon = getIcon(icon)
                  return (
                    <div
                      key={nodeId}
                      onClick={() => blockDef && onSelectBlock?.(blockDef)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        padding: '8px 10px',
                        background: T.surface0,
                        border: `1px solid ${T.border}`,
                        borderLeft: `3px solid ${accent}`,
                        borderRadius: 4,
                        cursor: blockDef && onSelectBlock ? 'pointer' : 'default',
                        transition: 'all 0.15s',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = T.surface2
                        e.currentTarget.style.borderColor = T.borderHi
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = T.surface0
                        e.currentTarget.style.borderColor = T.border
                      }}
                    >
                      <BlockIcon size={14} color={accent} />
                      <span
                        style={{
                          fontFamily: F,
                          fontSize: FS.xs,
                          color: T.text,
                          fontWeight: 600,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {label}
                      </span>
                    </div>
                  )
                })}
              </div>
            </Section>

            {/* Configuration Guide */}
            <Section title="CONFIGURATION GUIDE">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {recipeBlocks.map(({ nodeId, label, accent }) => {
                  const node = recipe.nodes.find((n) => n.id === nodeId)
                  if (!node) return null
                  const configKeys = Object.keys(node.data.config)
                  if (configKeys.length === 0) return null

                  return (
                    <div
                      key={nodeId}
                      style={{
                        background: T.surface0,
                        border: `1px solid ${T.border}`,
                        borderRadius: 6,
                        overflow: 'hidden',
                      }}
                    >
                      <div
                        style={{
                          padding: '6px 10px',
                          background: T.surface2,
                          borderBottom: `1px solid ${T.border}`,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 6,
                        }}
                      >
                        <span
                          style={{
                            width: 6,
                            height: 6,
                            borderRadius: '50%',
                            background: accent,
                            flexShrink: 0,
                          }}
                        />
                        <span
                          style={{
                            fontFamily: F,
                            fontSize: FS.xs,
                            color: T.text,
                            fontWeight: 700,
                          }}
                        >
                          {label}
                        </span>
                      </div>
                      <div style={{ padding: '8px 10px' }}>
                        {configKeys.map((key) => (
                          <div
                            key={key}
                            style={{
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                              padding: '3px 0',
                            }}
                          >
                            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
                              {key}
                            </span>
                            <span
                              style={{
                                fontFamily: "'JetBrains Mono', monospace",
                                fontSize: FS.xxs,
                                color: T.cyan,
                              }}
                            >
                              {String(node.data.config[key]).substring(0, 30) || '""'}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )
                })}
              </div>
            </Section>
          </div>

          {/* Sidebar (35%) */}
          <div style={{ flex: '0 0 35%', maxWidth: '35%', display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Pipeline Preview */}
            {pipelinePreview && (
              <SidebarCard title="PIPELINE PREVIEW" icon={<GitBranch size={10} color={T.cyan} />}>
                <div
                  style={{
                    background: T.surface0,
                    border: `1px solid ${T.border}`,
                    borderRadius: 6,
                    padding: 8,
                    overflow: 'hidden',
                  }}
                >
                  <svg
                    viewBox={`0 0 ${pipelinePreview.viewWidth} ${pipelinePreview.viewHeight}`}
                    style={{
                      width: '100%',
                      height: 'auto',
                      maxHeight: 260,
                    }}
                  >
                    {/* Edges */}
                    <defs>
                      <marker
                        id="arrowhead"
                        markerWidth="6"
                        markerHeight="4"
                        refX="6"
                        refY="2"
                        orient="auto"
                      >
                        <polygon points="0 0, 6 2, 0 4" fill={T.dim} />
                      </marker>
                    </defs>
                    {pipelinePreview.edges.map((edge) => (
                      <line
                        key={edge.id}
                        x1={edge.x1}
                        y1={edge.y1}
                        x2={edge.x2}
                        y2={edge.y2}
                        stroke={T.dim}
                        strokeWidth={1.5}
                        strokeDasharray="4 2"
                        markerEnd="url(#arrowhead)"
                      />
                    ))}
                    {/* Nodes */}
                    {pipelinePreview.nodes.map((node) => (
                      <g key={node.id}>
                        <rect
                          x={node.x}
                          y={node.y}
                          width={pipelinePreview.nodeWidth}
                          height={pipelinePreview.nodeHeight}
                          rx={4}
                          ry={4}
                          fill={T.surface2}
                          stroke={node.accent}
                          strokeWidth={1}
                        />
                        {/* Top accent line */}
                        <rect
                          x={node.x}
                          y={node.y}
                          width={pipelinePreview.nodeWidth}
                          height={2}
                          rx={1}
                          fill={node.accent}
                          opacity={0.7}
                        />
                        <text
                          x={node.x + pipelinePreview.nodeWidth / 2}
                          y={node.y + pipelinePreview.nodeHeight / 2 + 3}
                          textAnchor="middle"
                          fill={T.text}
                          fontSize={10}
                          fontFamily={F}
                          fontWeight={600}
                        >
                          {node.label.length > 16 ? node.label.slice(0, 14) + '..' : node.label}
                        </text>
                      </g>
                    ))}
                  </svg>
                </div>
              </SidebarCard>
            )}

            {/* Quick Stats */}
            <SidebarCard title="QUICK STATS" icon={<Layers size={10} color={T.cyan} />}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <StatRow label="Blocks" value={String(recipe.nodes.length)} />
                <StatRow label="Connections" value={String(recipe.edges.length)} />
                <StatRow
                  label="Categories"
                  value={categoriesUsed.join(', ')}
                />
                {recipe.version && <StatRow label="Version" value={`v${recipe.version}`} />}
                {recipe.author && <StatRow label="Author" value={recipe.author} />}
              </div>
            </SidebarCard>

            {/* Block Details Shortcut */}
            {recipeBlocks.some((b) => b.blockDef) && (
              <SidebarCard title="EXPLORE BLOCKS" icon={<Settings size={10} color={T.cyan} />}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {recipeBlocks.map(({ nodeId, label, blockDef, accent, icon }) => {
                    if (!blockDef) return null
                    const BlockIcon = getIcon(icon)
                    return (
                      <div
                        key={nodeId}
                        onClick={() => onSelectBlock?.(blockDef)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                          padding: '6px 8px',
                          background: T.surface0,
                          border: `1px solid ${T.border}`,
                          borderLeft: `3px solid ${accent}`,
                          borderRadius: 4,
                          cursor: onSelectBlock ? 'pointer' : 'default',
                          transition: 'all 0.15s',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = T.surface2
                          e.currentTarget.style.borderColor = T.borderHi
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = T.surface0
                          e.currentTarget.style.borderColor = T.border
                        }}
                      >
                        <BlockIcon size={12} color={accent} />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div
                            style={{
                              fontFamily: F,
                              fontSize: FS.xs,
                              color: T.text,
                              fontWeight: 600,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {label}
                          </div>
                          <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                            View block details
                          </div>
                        </div>
                        <Zap size={8} color={T.dim} />
                      </div>
                    )
                  })}
                </div>
              </SidebarCard>
            )}
          </div>
        </div>
      </div>

      {/* Footer CTA */}
      <div
        style={{
          padding: '14px 24px',
          borderTop: `1px solid ${T.border}`,
          background: T.surface1,
          flexShrink: 0,
          backdropFilter: 'blur(12px)',
        }}
      >
        <button
          onClick={handleInstall}
          style={{
            width: '100%',
            padding: '12px 20px',
            background: T.cyan,
            border: 'none',
            borderRadius: 6,
            color: '#000',
            fontFamily: FD,
            fontSize: FS.md,
            fontWeight: 700,
            cursor: 'pointer',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            transition: 'all 0.15s',
            boxShadow: `0 0 20px ${T.cyan}30`,
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.boxShadow = `0 0 32px ${T.cyan}50`
            e.currentTarget.style.transform = 'translateY(-1px)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.boxShadow = `0 0 20px ${T.cyan}30`
            e.currentTarget.style.transform = 'translateY(0)'
          }}
        >
          <PlusCircle size={14} />
          INSTALL TO CANVAS
        </button>
      </div>
    </motion.div>
  )
}

// ── Sub-components ──

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      style={{
        background: `linear-gradient(180deg, ${T.surface1} 0%, ${T.surface0} 100%)`,
        border: `1px solid ${T.border}`,
        borderRadius: 8,
        overflow: 'hidden',
        backdropFilter: 'blur(8px)',
      }}
    >
      <div
        style={{
          padding: '8px 16px',
          borderBottom: `1px solid ${T.border}`,
          background: T.surface2,
        }}
      >
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.dim,
            fontWeight: 700,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
          }}
        >
          {title}
        </span>
      </div>
      <div style={{ padding: 16 }}>{children}</div>
    </div>
  )
}

function SidebarCard({
  title,
  icon,
  children,
}: {
  title: string
  icon: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div
      style={{
        background: `linear-gradient(180deg, ${T.surface1} 0%, ${T.surface0} 100%)`,
        border: `1px solid ${T.border}`,
        borderRadius: 8,
        overflow: 'hidden',
        backdropFilter: 'blur(8px)',
      }}
    >
      <div
        style={{
          padding: '8px 12px',
          borderBottom: `1px solid ${T.border}`,
          background: T.surface2,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        {icon}
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.dim,
            fontWeight: 700,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
          }}
        >
          {title}
        </span>
      </div>
      <div style={{ padding: 12 }}>{children}</div>
    </div>
  )
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>{label}</span>
      <span
        style={{
          fontFamily: F,
          fontSize: FS.xs,
          color: T.text,
          fontWeight: 600,
          textTransform: 'capitalize',
          maxWidth: '60%',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          textAlign: 'right',
        }}
      >
        {value}
      </span>
    </div>
  )
}
