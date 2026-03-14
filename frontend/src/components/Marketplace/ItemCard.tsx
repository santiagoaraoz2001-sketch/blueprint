import { T, F, FS } from '@/lib/design-tokens'
import { Download, Star, Package, LayoutTemplate, Puzzle, Check } from 'lucide-react'
import PanelCard from '@/components/shared/PanelCard'
import type { MarketplaceItem } from '@/stores/marketplaceStore'

const TYPE_CONFIG: Record<string, { icon: typeof Package; color: string; label: string }> = {
  block: { icon: Package, color: '#22D3EE', label: 'BLOCK' },
  template: { icon: LayoutTemplate, color: '#A78BFA', label: 'TEMPLATE' },
  plugin: { icon: Puzzle, color: '#F97316', label: 'PLUGIN' },
}

interface ItemCardProps {
  item: MarketplaceItem
  onClick: () => void
  onInstall: (e: React.MouseEvent) => void
  isInstalling?: boolean
}

export default function ItemCard({ item, onClick, onInstall, isInstalling }: ItemCardProps) {
  const config = TYPE_CONFIG[item.item_type] || TYPE_CONFIG.block
  const Icon = config.icon

  return (
    <PanelCard accent={config.color} onClick={onClick}>
      <div style={{ padding: '14px 16px' }}>
        {/* Header row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 36, height: 36, display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: `${config.color}14`, border: `1px solid ${config.color}33`, borderRadius: 8,
          }}>
            <Icon size={18} color={config.color} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontFamily: F, fontSize: FS.md, fontWeight: 700, color: T.text,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {item.name}
              </span>
              <span style={{
                padding: '1px 5px', background: `${config.color}15`, border: `1px solid ${config.color}30`,
                borderRadius: 3, fontFamily: F, fontSize: '7px', fontWeight: 700,
                color: config.color, letterSpacing: '0.08em',
              }}>
                {config.label}
              </span>
            </div>
            <div style={{
              fontFamily: F, fontSize: FS.xxs, color: T.dim,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              by {item.author} &middot; v{item.version}
            </div>
          </div>
        </div>

        {/* Description */}
        <p style={{
          fontFamily: F, fontSize: FS.sm, color: T.sec, margin: '8px 0',
          lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical', overflow: 'hidden',
        }}>
          {item.description}
        </p>

        {/* Tags */}
        {item.tags.length > 0 && (
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 8 }}>
            {item.tags.slice(0, 4).map(tag => (
              <span key={tag} style={{
                padding: '1px 6px', background: T.surface3, borderRadius: 10,
                fontSize: FS.xxs, fontFamily: F, color: T.sec, border: `1px solid ${T.border}`,
              }}>
                {tag}
              </span>
            ))}
          </div>
        )}

        {/* Footer: rating, downloads, install button */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 8 }}>
          {/* Rating */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
            <Star size={10} color="#F59E0B" fill="#F59E0B" />
            <span style={{ fontFamily: F, fontSize: FS.xs, color: T.sec, fontWeight: 600 }}>
              {item.avg_rating.toFixed(1)}
            </span>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
              ({item.rating_count})
            </span>
          </div>

          {/* Downloads */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
            <Download size={9} color={T.dim} />
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
              {item.downloads.toLocaleString()}
            </span>
          </div>

          <div style={{ flex: 1 }} />

          {/* Install button */}
          {item.installed ? (
            <span style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '4px 10px', background: `${T.green}15`, border: `1px solid ${T.green}40`,
              borderRadius: 4, fontFamily: F, fontSize: FS.xxs, color: T.green,
              fontWeight: 700, letterSpacing: '0.06em',
            }}>
              <Check size={10} /> INSTALLED
            </span>
          ) : (
            <button
              onClick={(e) => { e.stopPropagation(); onInstall(e) }}
              disabled={isInstalling}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '4px 10px', background: `${T.cyan}15`, border: `1px solid ${T.cyan}40`,
                borderRadius: 4, fontFamily: F, fontSize: FS.xxs, color: T.cyan,
                fontWeight: 700, letterSpacing: '0.06em',
                cursor: isInstalling ? 'wait' : 'pointer',
                opacity: isInstalling ? 0.6 : 1,
                transition: 'all 0.15s',
              }}
              onMouseEnter={e => { if (!isInstalling) e.currentTarget.style.background = `${T.cyan}25` }}
              onMouseLeave={e => { e.currentTarget.style.background = `${T.cyan}15` }}
            >
              <Download size={10} /> {isInstalling ? 'INSTALLING...' : 'INSTALL'}
            </button>
          )}
        </div>
      </div>
    </PanelCard>
  )
}
