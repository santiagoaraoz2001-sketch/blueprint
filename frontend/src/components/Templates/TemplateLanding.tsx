/**
 * TemplateLanding — shown as the landing page when no pipelines exist.
 * Displays the TemplateGallery in embedded mode with an option to create
 * a blank pipeline or pick a template.
 */
import { useState, useCallback } from 'react'
import { T, F, FS, FD } from '@/lib/design-tokens'
import { motion } from 'framer-motion'
import TemplateGallery from './TemplateGallery'
import TemplatePreview from './TemplatePreview'
import { usePipelineStore } from '@/stores/pipelineStore'

export default function TemplateLanding({ onDismiss }: { onDismiss?: () => void } = {}) {
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null)
  const newPipeline = usePipelineStore((s) => s.newPipeline)

  const handleBlankCanvas = useCallback(() => {
    newPipeline()
    onDismiss?.()
  }, [newPipeline, onDismiss])

  const handleSelectTemplate = useCallback((templateId: string) => {
    setSelectedTemplateId(templateId)
  }, [])

  const handleClosePreview = useCallback(() => {
    setSelectedTemplateId(null)
  }, [])

  return (
    <div style={{
      height: '100%',
      overflow: 'auto',
      background: T.bg,
      padding: '0 32px 32px',
    }}>
      {/* Logo header */}
      <div style={{ textAlign: 'center', padding: '40px 0 8px' }}>
        <motion.svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 120 120"
          width="32"
          height="32"
          style={{ margin: '0 auto 10px', display: 'block' }}
          animate={{
            filter: [
              'drop-shadow(0 0 4px rgba(74, 246, 195, 0.0))',
              'drop-shadow(0 0 12px rgba(74, 246, 195, 0.4))',
              'drop-shadow(0 0 4px rgba(74, 246, 195, 0.0))',
            ],
          }}
          transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
        >
          <path fill={T.text} d="M 0,0 H 120 V 120 H 96 V 24 H 0 Z" />
          <circle fill={T.cyan} cx="36" cy="84" r="36" />
        </motion.svg>
        <h1 style={{
          fontFamily: FD, fontSize: 16, fontWeight: 700,
          color: T.text, letterSpacing: '0.14em', margin: '0 0 4px',
        }}>
          BLUEPRINT
        </h1>
        <p style={{
          fontFamily: F, fontSize: FS.xs, color: T.dim, margin: 0,
        }}>
          No pipelines yet
        </p>
      </div>

      <TemplateGallery
        onSelectTemplate={handleSelectTemplate}
        onBlankCanvas={handleBlankCanvas}
        embedded
      />

      {/* Template preview modal */}
      {selectedTemplateId && (
        <TemplatePreview
          templateId={selectedTemplateId}
          onBack={handleClosePreview}
          onClose={handleClosePreview}
        />
      )}
    </div>
  )
}
