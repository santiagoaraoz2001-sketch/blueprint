import { memo, useRef, useState, useEffect } from 'react'
import { NodeResizeControl } from '@xyflow/react'
import { T, F, FS } from '@/lib/design-tokens'
import { usePipelineStore } from '@/stores/pipelineStore'
import { Maximize2, X } from 'lucide-react'

// Simple markdown-to-html converter for sticky notes
function renderMarkdown(text: string) {
  if (!text) return '<span style="opacity: 0.5; font-style: italic;">Double click to edit note...</span>'
  return text
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
    .replace(/\*\*(.*)\*\*/gim, '<strong>$1</strong>')
    .replace(/\*(.*)\*/gim, '<em>$1</em>')
    .replace(/!\[(.*?)\]\((.*?)\)/gim, "<img alt='$1' src='$2' />")
    .replace(/\[(.*?)\]\((.*?)\)/gim, "<a href='$2'>$1</a>")
    .replace(/\n$/gim, '<br />')
}

// Colors for sticky notes
const STICKY_COLORS: Record<string, { bg: string; border: string }> = {
  yellow: { bg: 'rgba(250, 204, 21, 0.15)', border: 'rgba(250, 204, 21, 0.4)' },
  blue: { bg: 'rgba(56, 189, 248, 0.15)', border: 'rgba(56, 189, 248, 0.4)' },
  green: { bg: 'rgba(74, 222, 128, 0.15)', border: 'rgba(74, 222, 128, 0.4)' },
  purple: { bg: 'rgba(192, 132, 252, 0.15)', border: 'rgba(192, 132, 252, 0.4)' },
  red: { bg: 'rgba(248, 113, 113, 0.15)', border: 'rgba(248, 113, 113, 0.4)' },
}

function StickyNote({ id, data, selected }: any) {
  const [isEditing, setIsEditing] = useState(false)
  const [text, setText] = useState(data.text || '')
  const updateStickyNote = usePipelineStore((s) => s.updateStickyNote)
  const removeNode = usePipelineStore((s) => s.removeNode)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const colorConfig = STICKY_COLORS[data.color] || STICKY_COLORS.yellow

  useEffect(() => {
    if (isEditing && textareaRef.current) {
      textareaRef.current.focus()
    }
  }, [isEditing])

  const handleBlur = () => {
    setIsEditing(false)
    if (text !== data.text) {
      updateStickyNote(id, { text })
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setIsEditing(false)
      setText(data.text || '')
    }
  }

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        minWidth: 150,
        minHeight: 100,
        background: colorConfig.bg,
        border: `1px solid ${selected ? '#ffffff' : colorConfig.border}`,
        borderRadius: 8,
        backdropFilter: 'blur(8px)',
        position: 'relative',
        boxShadow: selected ? `0 0 0 1px rgba(255,255,255,0.2), 0 8px 24px ${T.shadow}` : `0 4px 12px ${T.shadowLight}`,
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
      }}
      onDoubleClick={() => setIsEditing(true)}
    >
      <NodeResizeControl
        minWidth={150}
        minHeight={100}
        style={{
          background: 'transparent',
          border: 'none',
          position: 'absolute',
          right: 2,
          bottom: 2,
          width: 14,
          height: 14,
          cursor: 'nwse-resize',
          display: selected ? 'flex' : 'none',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Maximize2 size={10} color={T.sec} style={{ transform: 'rotate(90deg)' }} />
      </NodeResizeControl>

      {/* Close button - visible only when selected */}
      {selected && !isEditing && (
        <button
          onClick={() => removeNode(id)}
          style={{
            position: 'absolute',
            top: 6,
            right: 6,
            background: T.shadow,
            border: `1px solid ${T.borderHi}`,
            borderRadius: '50%',
            width: 20,
            height: 20,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: T.sec,
            cursor: 'pointer',
            zIndex: 10,
          }}
          title="Delete Note"
        >
          <X size={10} />
        </button>
      )}

      {/* Color picker - visible only when selected */}
      {selected && !isEditing && (
        <div style={{ position: 'absolute', top: -30, left: 0, display: 'flex', gap: 6, background: T.surface2, padding: '4px 8px', borderRadius: 4, border: `1px solid ${T.borderHi}`, boxShadow: `0 4px 12px ${T.shadow}` }}>
          {Object.keys(STICKY_COLORS).map((c) => (
            <button
              key={c}
              onClick={(e) => { e.stopPropagation(); updateStickyNote(id, { color: c }) }}
              style={{
                width: 12,
                height: 12,
                borderRadius: '50%',
                background: STICKY_COLORS[c].border,
                border: data.color === c ? '2px solid white' : 'none',
                cursor: 'pointer',
              }}
            />
          ))}
        </div>
      )}

      <div style={{ flex: 1, overflow: 'hidden' }}>
        {isEditing ? (
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onBlur={handleBlur}
            onKeyDown={handleKeyDown}
            className="nodrag nopan"
            style={{
              width: '100%',
              height: '100%',
              background: 'transparent',
              border: 'none',
              color: T.text,
              fontFamily: F,
              fontSize: FS.sm,
              resize: 'none',
              outline: 'none',
              lineHeight: 1.5,
            }}
            placeholder="Type your note here..."
          />
        ) : (
          <div
            className="markdown-body"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(data.text) }}
            style={{
              fontFamily: F,
              fontSize: FS.sm,
              color: T.text,
              lineHeight: 1.5,
              wordBreak: 'break-word',
              userSelect: 'none',
              pointerEvents: 'none', // pass clicks to the node
            }}
          />
        )}
      </div>

      <style dangerouslySetInnerHTML={{
        __html: `
        .markdown-body h1 { font-size: 1.4em; font-weight: bold; margin-bottom: 0.5em; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 0.2em; }
        .markdown-body h2 { font-size: 1.2em; font-weight: bold; margin-bottom: 0.4em; }
        .markdown-body h3 { font-size: 1.1em; font-weight: bold; margin-bottom: 0.3em; }
        .markdown-body p { margin-bottom: 0.5em; }
        .markdown-body strong { color: white; font-weight: bold; }
        .markdown-body em { font-style: italic; opacity: 0.9; }
      `}} />
    </div>
  )
}

export default memo(StickyNote)
