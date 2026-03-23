import { T, F, FS } from '@/lib/design-tokens'
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
  { id: 'research', label: 'Workspace', icon: Home, group: 'build' },
  { id: 'dashboard', label: 'Projects', icon: LayoutDashboard, group: 'build' },
  { id: 'editor', label: 'Pipeline', icon: GitBranch, group: 'build' },
  { id: 'datasets', label: 'Datasets', icon: Database, group: 'build' },
  { id: 'marketplace', label: 'Blocks', icon: Blocks, group: 'build' },
  { id: 'monitor', label: 'Mission', icon: Activity, group: 'run' },
  { id: 'output', label: 'Outputs', icon: Terminal, group: 'run' },
  { id: 'results', label: 'Results', icon: BarChart3, group: 'analyze' },
  { id: 'data', label: 'Data Grid', icon: Table2, group: 'analyze' },
  { id: 'visualization', label: 'Charts', icon: LineChart, group: 'analyze' },
  { id: 'paper', label: 'Paper', icon: FileText, group: 'write' },
  { id: 'workshop', label: 'Workshop', icon: Wrench, group: 'write' },
  { id: 'settings', label: 'Settings', icon: Settings, group: 'system' },
  { id: 'help', label: 'Help', icon: HelpCircle, group: 'system' },
]

const SIMPLE_HIDDEN_VIEWS: Set<View> = new Set(['paper', 'workshop'])
const GROUP_LABELS: Record<NavItem['group'], string> = {
  build: 'Build',
  run: 'Run',
  analyze: 'Analyze',
  write: 'Write',
  system: 'System',
}

export default function Sidebar() {
  const { activeView, setView, sidebarCollapsed, toggleSidebar, selectedProjectId } = useUIStore()
  const projects = useProjectStore((s) => s.projects)
  const features = useSettingsStore((s) => s.features)
  const isSimple = useIsSimpleMode()
  const width = sidebarCollapsed ? 64 : 236

  const activeProject = projects.find((p) => p.id === selectedProjectId)
  const navItems = (isSimple ? NAV_ITEMS.filter((item) => !SIMPLE_HIDDEN_VIEWS.has(item.id)) : NAV_ITEMS).filter(
    (item) => item.id !== 'marketplace' || features?.marketplace,
  )

  return (
    <aside
      style={{
        width,
        minWidth: width,
        height: '100%',
        background: `linear-gradient(180deg, ${T.surface1}ee 0%, ${T.surface0}d8 100%)`,
        borderRight: `1px solid ${T.border}`,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        transition: 'width 0.2s ease',
        backdropFilter: 'blur(12px)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: sidebarCollapsed ? 'center' : 'space-between', padding: '12px 10px 8px', borderBottom: `1px solid ${T.border}` }}>
        {!sidebarCollapsed && (
          <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            Navigation
          </span>
        )}
        <button
          onClick={toggleSidebar}
          aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          style={{
            width: 30,
            height: 30,
            borderRadius: 9,
            border: `1px solid ${T.borderHi}`,
            background: `${T.surface2}cc`,
            color: T.sec,
            cursor: 'pointer',
            display: 'grid',
            placeItems: 'center',
          }}
        >
          {sidebarCollapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
        </button>
      </div>

      <nav style={{ flex: 1, overflowY: 'auto', padding: '8px 8px 12px' }}>
        {(['build', 'run', 'analyze', 'write', 'system'] as NavItem['group'][]).map((group) => {
          const items = navItems.filter((item) => item.group === group)
          if (items.length === 0) return null

          return (
            <div key={group} style={{ marginBottom: 10 }}>
              {!sidebarCollapsed && (
                <div style={{ padding: '6px 10px', fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.09em', textTransform: 'uppercase' }}>
                  {GROUP_LABELS[group]}
                </div>
              )}
              {items.map((item) => {
                const active = activeView === item.id || (item.id === 'research' && activeView === 'research-detail')
                const Icon = item.icon

                return (
                  <button
                    key={item.id}
                    onClick={() => setView(item.id)}
                    style={{
                      width: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      padding: sidebarCollapsed ? '10px 0' : '10px 12px',
                      justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
                      borderRadius: 10,
                      border: `1px solid ${active ? `${T.cyan}66` : 'transparent'}`,
                      marginBottom: 4,
                      background: active ? `${T.cyan}1c` : 'transparent',
                      color: active ? T.text : T.dim,
                      cursor: 'pointer',
                      transition: 'all 0.16s ease',
                      fontFamily: F,
                      fontSize: FS.sm,
                      letterSpacing: '0.04em',
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
                    <Icon size={15} />
                    {!sidebarCollapsed && <span>{item.label}</span>}
                  </button>
                )
              })}
            </div>
          )
        })}
      </nav>

      <div
        role="button"
        tabIndex={0}
        onClick={() => setView('dashboard')}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') setView('dashboard')
        }}
        style={{
          borderTop: `1px solid ${T.border}`,
          borderBottom: `1px solid ${T.border}`,
          padding: sidebarCollapsed ? '10px 4px' : '10px 12px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
          gap: 8,
          cursor: 'pointer',
        }}
      >
        <FolderOpen size={13} color={activeProject ? T.cyan : T.dim} />
        {!sidebarCollapsed && (
          <span style={{ fontFamily: F, fontSize: FS.xs, color: activeProject ? T.sec : T.dim, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {activeProject?.name || 'No project selected'}
          </span>
        )}
      </div>

      <div style={{ padding: sidebarCollapsed ? '10px 0' : '10px 12px', textAlign: sidebarCollapsed ? 'center' : 'left' }}>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>v{APP_VERSION}</span>
      </div>
    </aside>
  )
}
