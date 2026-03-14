import { useState } from 'react'
import { T, F, FS, FD } from '@/lib/design-tokens'
import {
  X, Star, Download, Package, LayoutTemplate, Puzzle,
  MessageSquare, Send,
} from 'lucide-react'
import { motion } from 'framer-motion'
import type { MarketplaceItem, Review } from '@/stores/marketplaceStore'

const TYPE_CONFIG: Record<string, { icon: typeof Package; color: string; label: string }> = {
  block: { icon: Package, color: '#22D3EE', label: 'Block' },
  template: { icon: LayoutTemplate, color: '#A78BFA', label: 'Template' },
  plugin: { icon: Puzzle, color: '#F97316', label: 'Plugin' },
}

interface ItemDetailModalProps {
  item: MarketplaceItem
  onClose: () => void
  onInstall: () => void
  onUninstall: () => void
  onSubmitReview: (rating: number, text: string) => void
}

export default function ItemDetailModal({
  item, onClose, onInstall, onUninstall, onSubmitReview,
}: ItemDetailModalProps) {
  const [reviewRating, setReviewRating] = useState(5)
  const [reviewText, setReviewText] = useState('')
  const [hoveredStar, setHoveredStar] = useState(0)

  const config = TYPE_CONFIG[item.item_type] || TYPE_CONFIG.block
  const Icon = config.icon

  const handleSubmitReview = () => {
    if (reviewText.trim()) {
      onSubmitReview(reviewRating, reviewText.trim())
      setReviewText('')
      setReviewRating(5)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
        zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.98 }}
        transition={{ duration: 0.25 }}
        onClick={e => e.stopPropagation()}
        style={{
          width: '90%', maxWidth: 720, maxHeight: '85vh',
          background: T.surface0, border: `1px solid ${T.border}`,
          borderTop: `3px solid ${config.color}`,
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div style={{
          padding: '20px 24px', borderBottom: `1px solid ${T.border}`,
          background: T.surface1, flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{
              width: 48, height: 48, display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: `${config.color}14`, border: `1px solid ${config.color}33`, borderRadius: 12,
            }}>
              <Icon size={22} color={config.color} />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <h2 style={{
                  margin: 0, fontFamily: FD, fontSize: FS.h2, color: T.text,
                  fontWeight: 700, letterSpacing: '0.02em',
                }}>
                  {item.name}
                </h2>
                <span style={{
                  padding: '2px 8px', background: `${config.color}15`,
                  border: `1px solid ${config.color}30`, borderRadius: 4,
                  fontFamily: F, fontSize: FS.xxs, color: config.color,
                  fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
                }}>
                  {config.label}
                </span>
              </div>
              <div style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, marginTop: 2 }}>
                by {item.author} &middot; v{item.version} &middot; {item.license}
              </div>
            </div>
            <button
              onClick={onClose}
              style={{
                background: 'none', border: `1px solid ${T.border}`, borderRadius: 4,
                padding: 6, cursor: 'pointer', color: T.dim,
              }}
            >
              <X size={14} />
            </button>
          </div>

          {/* Stats bar */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 16, marginTop: 12,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <Star size={12} color="#F59E0B" fill="#F59E0B" />
              <span style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 700 }}>
                {item.avg_rating.toFixed(1)}
              </span>
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                ({item.rating_count} reviews)
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <Download size={11} color={T.dim} />
              <span style={{ fontFamily: F, fontSize: FS.sm, color: T.sec }}>
                {item.downloads.toLocaleString()} downloads
              </span>
            </div>
          </div>
        </div>

        {/* Scrollable content */}
        <div style={{ flex: 1, overflow: 'auto', padding: 24 }}>
          {/* Description */}
          <div style={{ marginBottom: 24 }}>
            <SectionTitle>Description</SectionTitle>
            <p style={{
              fontFamily: F, fontSize: FS.sm, color: T.sec, lineHeight: 1.7, margin: 0,
            }}>
              {item.description}
            </p>
          </div>

          {/* Tags */}
          {item.tags.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <SectionTitle>Tags</SectionTitle>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {item.tags.map(tag => (
                  <span key={tag} style={{
                    padding: '3px 10px', background: T.surface3, borderRadius: 12,
                    fontSize: FS.xs, fontFamily: F, color: T.sec, border: `1px solid ${T.border}`,
                  }}>
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Reviews */}
          <div style={{ marginBottom: 24 }}>
            <SectionTitle>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <MessageSquare size={10} color={T.dim} />
                Reviews ({item.reviews?.length || 0})
              </div>
            </SectionTitle>

            {(item.reviews || []).length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {item.reviews.map(review => (
                  <ReviewCard key={review.id} review={review} />
                ))}
              </div>
            ) : (
              <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, margin: 0 }}>
                No reviews yet. Be the first!
              </p>
            )}
          </div>

          {/* Write a review */}
          <div>
            <SectionTitle>Write a Review</SectionTitle>
            <div style={{
              background: T.surface2, border: `1px solid ${T.border}`,
              borderRadius: 6, padding: 14,
            }}>
              {/* Star rating input */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>Rating:</span>
                <div style={{ display: 'flex', gap: 2 }}>
                  {[1, 2, 3, 4, 5].map(n => (
                    <button
                      key={n}
                      onClick={() => setReviewRating(n)}
                      onMouseEnter={() => setHoveredStar(n)}
                      onMouseLeave={() => setHoveredStar(0)}
                      style={{
                        background: 'none', border: 'none', cursor: 'pointer', padding: 2,
                      }}
                    >
                      <Star
                        size={14}
                        color="#F59E0B"
                        fill={n <= (hoveredStar || reviewRating) ? '#F59E0B' : 'none'}
                      />
                    </button>
                  ))}
                </div>
              </div>
              <textarea
                value={reviewText}
                onChange={e => setReviewText(e.target.value)}
                placeholder="Share your experience..."
                rows={3}
                style={{
                  width: '100%', background: T.surface0, border: `1px solid ${T.border}`,
                  borderRadius: 4, padding: '8px 10px', color: T.text, fontFamily: F,
                  fontSize: FS.sm, resize: 'vertical', outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
              <button
                onClick={handleSubmitReview}
                disabled={!reviewText.trim()}
                style={{
                  marginTop: 8, display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 14px', background: reviewText.trim() ? `${T.cyan}20` : T.surface3,
                  border: `1px solid ${reviewText.trim() ? T.cyan + '40' : T.border}`,
                  borderRadius: 4, fontFamily: F, fontSize: FS.xs,
                  color: reviewText.trim() ? T.cyan : T.dim,
                  fontWeight: 700, cursor: reviewText.trim() ? 'pointer' : 'default',
                  letterSpacing: '0.06em',
                }}
              >
                <Send size={10} /> SUBMIT REVIEW
              </button>
            </div>
          </div>
        </div>

        {/* Footer with install/uninstall button */}
        <div style={{
          padding: '14px 24px', borderTop: `1px solid ${T.border}`,
          background: T.surface1, flexShrink: 0,
        }}>
          {item.installed ? (
            <button
              onClick={onUninstall}
              style={{
                width: '100%', padding: '10px 20px',
                background: `${T.red}15`, border: `1px solid ${T.red}40`,
                borderRadius: 6, color: T.red, fontFamily: FD, fontSize: FS.md,
                fontWeight: 700, cursor: 'pointer', letterSpacing: '0.08em',
                textTransform: 'uppercase', display: 'flex', alignItems: 'center',
                justifyContent: 'center', gap: 8,
              }}
            >
              <X size={14} /> UNINSTALL
            </button>
          ) : (
            <button
              onClick={onInstall}
              style={{
                width: '100%', padding: '10px 20px',
                background: T.cyan, border: 'none', borderRadius: 6,
                color: '#000', fontFamily: FD, fontSize: FS.md, fontWeight: 700,
                cursor: 'pointer', letterSpacing: '0.08em', textTransform: 'uppercase',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                boxShadow: `0 0 20px ${T.cyan}30`,
                transition: 'all 0.15s',
              }}
              onMouseEnter={e => { e.currentTarget.style.boxShadow = `0 0 32px ${T.cyan}50` }}
              onMouseLeave={e => { e.currentTarget.style.boxShadow = `0 0 20px ${T.cyan}30` }}
            >
              <Download size={14} /> INSTALL
            </button>
          )}
        </div>
      </motion.div>
    </motion.div>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 700,
      letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 8,
    }}>
      {children}
    </div>
  )
}

function ReviewCard({ review }: { review: Review }) {
  return (
    <div style={{
      padding: '10px 12px', background: T.surface1, border: `1px solid ${T.border}`,
      borderRadius: 6,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <div style={{ display: 'flex', gap: 1 }}>
          {[1, 2, 3, 4, 5].map(n => (
            <Star key={n} size={10} color="#F59E0B" fill={n <= review.rating ? '#F59E0B' : 'none'} />
          ))}
        </div>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          {review.author}
        </span>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginLeft: 'auto' }}>
          {new Date(review.created_at).toLocaleDateString()}
        </span>
      </div>
      <p style={{ fontFamily: F, fontSize: FS.sm, color: T.sec, margin: 0, lineHeight: 1.5 }}>
        {review.text}
      </p>
    </div>
  )
}
