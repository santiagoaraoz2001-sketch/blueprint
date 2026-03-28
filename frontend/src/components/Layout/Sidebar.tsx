import { T, F, FS, BRAND_TEAL } from '@/lib/design-tokens'
import { useUIStore, type View } from '@/stores/uiStore'
import { useProjectStore } from '@/stores/projectStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { useIsSimpleMode } from '@/hooks/useIsSimpleMode'
import {
  LayoutDashboard,
  GitBranch,
  BarChart3,
  Database,
  Blocks,
  FileText,
  Settings,
  HelpCircle,
  FolderOpen,
  Wrench,
  Terminal,
  Table2,
  LineChart,
  PanelLeftClose,
  PanelLeftOpen,
  Home,
  Activity,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

const APP_VERSION: string = __APP_VERSION__

interface NavItem {
  id: View
  label: string
  icon: LucideIcon
  group: 'build' | 'run' | 'analyze' | 'write' | 'system'
}

const NAV_ITEMS: NavItem[] = [
  { id: 'research',      label: 'Workspace', icon: Home,            group: 'build'   },
  { id: 'dashboard',     label: 'Projects',  icon: LayoutDashboard, group: 'build'   },
  { id: 'editor',        label: 'Pipeline',  icon: GitBranch,       group: 'build'   },
  { id: 'datasets',      label: 'Datasets',  icon: Database,        group: 'build'   },
  { id: 'marketplace',   label: 'Blocks',    icon: Blocks,          group: 'build'   },
  { id: 'monitor',       label: 'Mission',   icon: Activity,        group: 'run'     },
  { id: 'output',        label: 'Outputs',   icon: Terminal,        group: 'run'     },
  { id: 'results',       label: 'Results',   icon: BarChart3,       group: 'analyze' },
  { id: 'data',          label: 'Data Grid', icon: Table2,          group: 'analyze' },
  { id: 'visualization', label: 'Charts',    icon: LineChart,       group: 'analyze' },
  { id: 'paper',         label: 'Paper',     icon: FileText,        group: 'write'   },
  { id: 'workshop',      label: 'Workshop',  icon: Wrench,          group: 'write'   },
  { id: 'settings',      label: 'Settings',  icon: Settings,        group: 'system'  },
  { id: 'help',          label: 'Help',      icon: HelpCircle,      group: 'system'  },
]

const SIMPLE_HIDDEN_VIEWS: Set<View> = new Set(['paper', 'workshop'])
const GROUP_LABELS: Record<NavItem['group'], string> = {
  build:   'Build',
  run:     'Run',
  analyze: 'Analyze',
  write:   'Write',
  system:  'System',
}

export default function Sidebar() {
  const { activeView, setView, sidebarCollapsed, toggleSidebar, selectedProjectId } = useUIStore()
  const projects  = useProjectStore((s) => s.projects)
  const features  = useSettingsStore((s) => s.features)
  const isSimple  = useIsSimpleMode()
  const width     = sidebarCollapsed ? 64 : 236

  const activeProject = projects.find((p) => p.id === selectedProjectId)
  const navItems = (
    isSimple
      ? NAV_ITEMS.filter((item) => !SIMPLE_HIDDEN_VIEWS.has(item.id))
      : NAV_ITEMS
  ).filter((item) => item.id !== 'marketplace' || features?.marketplace)

  return (
    <aside
      style={{
        width,
        minWidth: width,
        height: '100%',
        // Slightly deeper, less blue sidebar
        background: `linear-gradient(180deg, ${T.surface1}f0 0%, ${T.surface0}e8 100%)`,
        // Hairline border + inner glow for depth
        borderRight: `0.5px solid ${T.border}`,
        boxShadow: `inset -1px 0 0 ${T.border}44`,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        transition: 'width 0.22s cubic-bezier(0.16, 1, 0.3, 1)',
        backdropFilter: 'blur(14px)',
      }}
    >
      {/* Header row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: sidebarCollapsed ? 'center' : 'space-between',
          padding: '10px 10px 8px',
          borderBottom: `0.5px solid ${T.border}`,
        }}
      >
        {!sidebarCollapsed && (
          <span
            style={{
              fontFamily: F,
              fontSize: FS.xxs,
              color: T.dim,
              letterSpacing: '0.16em',
              textTransform: 'uppercase',
              opacity: 0.55,
            }}
          >
            Navigation
          </span>
        )}
        <button
          onClick={toggleSidebar}
          aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          style={{
            width: 28,
            height: 28,
            borderRadius: 8,
            border: `0.5px solid ${T.border}`,
            background: `${T.surface2}cc`,
            color: T.dim,
            cursor: 'pointer',
            display: 'grid',
            placeItems: 'center',
            transition: 'background 0.14s ease, color 0.14s ease',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = `${T.surface3}cc`
            e.currentTarget.style.color = T.sec
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = `${T.surface2}cc`
            e.currentTarget.style.color = T.dim
          }}
        >
          {sidebarCollapsed ? <PanelLeftOpen size={13} /> : <PanelLeftClose size={13} />}
        </button>
      </div>

      {/* Nav items */}
      <nav style={{ flex: 1, overflowY: 'auto', padding: '6px 8px 10px' }}>
        {(['build', 'run', 'analyze', 'write', 'system'] as NavItem['group'][]).map((group) => {
          const items = navItems.filter((item) => item.group === group)
          if (items.length === 0) return null

          return (
            <div key={group} style={{ marginBottom: 8 }}>
              {!sidebarCollapsed && (
                <div
                  style={{
                    padding: '5px 10px',
                    fontFamily: F,
                    fontSize: FS.xxs,
                    color: T.dim,
                    letterSpacing: '0.16em',
                    textTransform: 'uppercase',
                    opacity: 0.40,
                  }}
                >
                  {GROUP_LABELS[group]}
                </div>
              )}
              {items.map((item) => {
                const active = activeView === item.id || (item.id === 'research' && activeView === 'research-detail')
                const Icon   = item.icon

                return (
                  <button
                    key={item.id}
                    onClick={() => setView(item.id)}
                    style={{
                      width: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 9,
                      padding: sidebarCollapsed ? '9px 0' : '8px 10px 8px 14px',
                      justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
                      borderRadius: 9,
                      border: active ? `1px solid ${T.cyan}30` : '1px solid transparent',
                      marginBottom: 3,
                      position: 'relative',
                      overflow: 'hidden',
                      background: active
                        ? `linear-gradient(135deg, ${T.cyan}18 0%, ${T.cyan}08 100%)`
                        : 'transparent',
                      boxShadow: active ? `0 0 12px ${T.cyan}14, inset 0 1px 0 ${T.cyan}18` : 'none',
                      color: active ? T.text : T.dim,
                      cursor: 'pointer',
                      transition: 'all 0.16s ease',
                      fontFamily: F,
                      fontSize: FS.sm,
                      letterSpacing: '0.03em',
                    }}
                    onMouseEnter={(e) => {
                      if (!active) {
                        e.currentTarget.style.background = `${T.surface2}cc`
                        e.currentTarget.style.color = T.sec
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!active) {
                        e.currentTarget.style.background = 'transparent'
                        e.currentTarget.style.color = T.dim
                      }
                    }}
                  >
                    {/* Active left-bar indicator */}
                    {active && !sidebarCollapsed && (
                      <>
                        <div
                          style={{
                            position: 'absolute',
                            left: 3,
                            top: '50%',
                            transform: 'translateY(-50%)',
                            width: 2.5,
                            height: 20,
                            borderRadius: 999,
                            background: BRAND_TEAL,
                            boxShadow: `0 0 8px ${BRAND_TEAL}88, 0 0 16px ${BRAND_TEAL}44`,
                          }}
                        />
                        {/* Shimmer sweep on active item */}
                        <div
                          style={{
                            position: 'absolute',
                            inset: 0,
                            borderRadius: 9,
                            background: `linear-gradient(90deg, transparent 0%, ${T.cyan}18 50%, transparent 100%)`,
                            animation: 'nav-active-shimmer 3s ease-in-out infinite',
                            pointerEvents: 'none',
                          }}
                        />
                      </>
                    )}
                    <Icon
                      size={14}
                      color={active ? BRAND_TEAL : T.dim}
                      style={{ flexShrink: 0 }}
                    />
                    {!sidebarCollapsed && (
                      <span
                        style={{
                          color: active ? T.sec : 'inherit',
                        }}
                      >
                        {item.label}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          )
        })}
      </nav>

      {/* Active project — click navigates to ProjectView */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => {
          if (selectedProjectId) {
            setView('project' as any)
          } else {
            setView('dashboard')
          }
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            if (selectedProjectId) {
              setView('project' as any)
            } else {
              setView('dashboard')
            }
          }
        }}
        style={{
          borderTop:    `0.5px solid ${T.border}`,
          borderBottom: `0.5px solid ${T.border}`,
          padding: sidebarCollapsed ? '9px 4px' : '9px 12px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
          gap: 7,
          cursor: 'pointer',
          transition: 'background 0.14s ease',
        }}
        onMouseEnter={(e) => { e.currentTarget.style.background = `${T.surface2}88` }}
        onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
      >
        <FolderOpen size={12} color={activeProject ? T.cyan : T.dim} />
        {!sidebarCollapsed && (
          <span
            style={{
              fontFamily: F,
              fontSize: FS.xs,
              color: activeProject ? T.sec : T.dim,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {activeProject?.name || 'No project selected'}
          </span>
        )}
      </div>

      {/* Version */}
      <div
        style={{
          padding: sidebarCollapsed ? '9px 0' : '9px 12px',
          textAlign: sidebarCollapsed ? 'center' : 'left',
        }}
      >
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.dim,
            letterSpacing: '0.06em',
            opacity: 0.30,
          }}
        >
          v{APP_VERSION}
        </span>
      </div>
    </aside>
  )
}
