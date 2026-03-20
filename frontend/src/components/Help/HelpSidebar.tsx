import { useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { ChevronDown, ChevronRight } from 'lucide-react'

export interface TocSection {
  id: string
  title: string
  children?: { id: string; title: string }[]
}

interface HelpSidebarProps {
  sections: TocSection[]
  activeId: string
  onNavigate: (id: string) => void
}

export default function HelpSidebar({ sections, activeId, onNavigate }: HelpSidebarProps) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})

  const toggle = (id: string) =>
    setCollapsed((prev) => ({ ...prev, [id]: !prev[id] }))

  const isActive = (id: string) => activeId === id

  return (
    <nav
      style={{
        width: 260,
        minWidth: 260,
        height: '100%',
        overflowY: 'auto',
        borderRight: `1px solid ${T.border}`,
        padding: '16px 0',
        background: T.surface1,
      }}
    >
      <div
        style={{
          fontFamily: F,
          fontSize: FS.xxs,
          fontWeight: 900,
          letterSpacing: '0.14em',
          textTransform: 'uppercase',
          color: T.dim,
          padding: '0 16px',
          marginBottom: 12,
        }}
      >
        Contents
      </div>

      {sections.map((section) => {
        const isOpen = !collapsed[section.id]
        const hasChildren = section.children && section.children.length > 0

        return (
          <div key={section.id}>
            <div
              onClick={() => {
                if (hasChildren) toggle(section.id)
                onNavigate(section.id)
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '7px 16px',
                cursor: 'pointer',
                fontFamily: F,
                fontSize: FS.sm,
                fontWeight: isActive(section.id) ? 700 : 500,
                color: isActive(section.id) ? T.cyan : T.sec,
                background: isActive(section.id) ? T.surface2 : 'transparent',
                borderLeft: isActive(section.id) ? `2px solid ${T.cyan}` : '2px solid transparent',
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => {
                if (!isActive(section.id)) {
                  e.currentTarget.style.background = T.surface2
                  e.currentTarget.style.color = T.text
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive(section.id)) {
                  e.currentTarget.style.background = 'transparent'
                  e.currentTarget.style.color = T.sec
                }
              }}
            >
              {hasChildren && (
                <span style={{ display: 'flex', flexShrink: 0 }}>
                  {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                </span>
              )}
              <span style={{ lineHeight: 1.3 }}>{section.title}</span>
            </div>

            {hasChildren && isOpen && (
              <div>
                {section.children!.map((child) => (
                  <div
                    key={child.id}
                    onClick={() => onNavigate(child.id)}
                    style={{
                      padding: '5px 16px 5px 38px',
                      cursor: 'pointer',
                      fontFamily: F,
                      fontSize: FS.xs,
                      fontWeight: isActive(child.id) ? 600 : 400,
                      color: isActive(child.id) ? T.cyan : T.dim,
                      background: isActive(child.id) ? T.surface2 : 'transparent',
                      borderLeft: isActive(child.id) ? `2px solid ${T.cyan}` : '2px solid transparent',
                      transition: 'all 0.15s ease',
                    }}
                    onMouseEnter={(e) => {
                      if (!isActive(child.id)) {
                        e.currentTarget.style.background = T.surface2
                        e.currentTarget.style.color = T.sec
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!isActive(child.id)) {
                        e.currentTarget.style.background = 'transparent'
                        e.currentTarget.style.color = T.dim
                      }
                    }}
                  >
                    {child.title}
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </nav>
  )
}
