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
import { motion } from 'framer-motion'

// Injected at build time by vite.config.ts define
const APP_VERSION: string = __APP_VERSION__

interface NavItem {
  id: View
  label: string
  icon: LucideIcon
}

const NAV_ITEMS: NavItem[] = [
  { id: 'research', label: 'Research', icon: Home },
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'editor', label: 'Pipelines', icon: GitBranch },
  { id: 'datasets', label: 'Datasets', icon: Database },
  { id: 'data', label: 'Data', icon: Table2 },
  { id: 'marketplace', label: 'Blocks', icon: Blocks },
  { id: 'workshop', label: 'Workshop', icon: Wrench },
  { id: 'monitor', label: 'Monitor', icon: Activity },
  { id: 'output', label: 'Output', icon: Terminal },
  { id: 'results', label: 'Results', icon: BarChart3 },
  { id: 'visualization', label: 'Charts', icon: LineChart },
  { id: 'paper', label: 'Paper', icon: FileText },
  { id: 'settings', label: 'Settings', icon: Settings },
  { id: 'help', label: 'Help', icon: HelpCircle },
]

const SIMPLE_HIDDEN_VIEWS: Set<View> = new Set(['paper', 'workshop'])

export default function Sidebar() {
  const { activeView, setView, sidebarCollapsed, toggleSidebar, selectedProjectId } = useUIStore()
  const projects = useProjectStore((s) => s.projects)
  const features = useSettingsStore((s) => s.features)
  const isSimple = useIsSimpleMode()
  const width = sidebarCollapsed ? 48 : 180

  const activeProject = projects.find((p) => p.id === selectedProjectId)

  return (
    <div
      style={{
        width,
        minWidth: width,
        height: '100%',
        background: T.surface1,
        borderRight: `1px solid ${T.border}`,
        display: 'flex',
        flexDirection: 'column',
        transition: 'width 0.15s ease',
        overflow: 'hidden',
      }}
    >
      {/* Collapse / Expand toggle */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: sidebarCollapsed ? 'center' : 'flex-end',
          padding: sidebarCollapsed ? '8px 0' : '8px 8px',
          borderBottom: `1px solid ${T.border}`,
        }}
      >
        <motion.button
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.95 }}
          onClick={toggleSidebar}
          aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 28,
            height: 28,
            background: 'none',
            border: `1px solid ${T.border}`,
            borderRadius: 6,
            color: T.dim,
            cursor: 'pointer',
            transition: 'color 0.15s, border-color 0.15s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = T.text
            e.currentTarget.style.borderColor = T.borderHi
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = T.dim
            e.currentTarget.style.borderColor = T.border
          }}
        >
          {sidebarCollapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
        </motion.button>
      </div>

      <nav style={{ flex: 1, paddingTop: 6 }}>
        {(isSimple ? NAV_ITEMS.filter((item) => !SIMPLE_HIDDEN_VIEWS.has(item.id)) : NAV_ITEMS)
          .filter((item) => item.id !== 'marketplace' || features?.marketplace)
          .map((item, index) => {
          const active = activeView === item.id || (item.id === 'research' && activeView === 'research-detail')
          const Icon = item.icon
          return (
            <motion.button
              key={item.id}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.06, duration: 0.3 }}
              whileHover={{ scale: 1.02, x: 3 }}
              onClick={() => setView(item.id)}
              aria-label={item.label}
              aria-current={active ? 'page' : undefined}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                width: '100%',
                padding: sidebarCollapsed ? '9px 0' : '9px 12px',
                justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
                background: active ? `${T.cyan}08` : 'transparent',
                border: 'none',
                borderLeft: active ? `2px solid ${T.cyan}` : '2px solid transparent',
                color: active ? T.text : T.dim,
                fontFamily: F,
                fontSize: FS.sm,
                fontWeight: active ? 900 : 500,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                transition: 'all 0.15s ease',
                position: 'relative',
                cursor: 'pointer',
                boxShadow: active
                  ? `0 0 8px ${T.cyan}30, inset 0 0 4px ${T.cyan}15`
                  : 'none',
                animation: active ? 'sidebar-active-glow 2.5s ease-in-out infinite' : 'none',
              }}
              onMouseEnter={(e) => {
                if (!active) {
                  e.currentTarget.style.background = T.surface2
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
              <Icon size={13} strokeWidth={active ? 2.5 : 1.5} />
              {!sidebarCollapsed && <span>{item.label}</span>}

              {/* Injected keyframes for active glow pulse */}
              {active && (
                <style>{`
                  @keyframes sidebar-active-glow {
                    0%, 100% { box-shadow: 0 0 6px ${T.cyan}20, inset 0 0 3px ${T.cyan}10; }
                    50% { box-shadow: 0 0 12px ${T.cyan}40, inset 0 0 6px ${T.cyan}25; }
                  }
                `}</style>
              )}
            </motion.button>
          )
        })}
      </nav>

      {/* Active Project Indicator */}
      <div
        role="button"
        tabIndex={0}
        aria-label={activeProject ? `Active project: ${activeProject.name}` : 'No active project'}
        onClick={() => setView('dashboard')}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setView('dashboard') }}
        style={{
          padding: sidebarCollapsed ? '8px 4px' : '8px 12px',
          borderTop: `1px solid ${T.border}`,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          transition: 'background 0.15s ease',
        }}
        onMouseEnter={(e) => { e.currentTarget.style.background = T.surface2 }}
        onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
      >
        <FolderOpen size={12} color={activeProject ? T.cyan : T.dim} />
        {!sidebarCollapsed && (
          <span style={{
            fontFamily: F, fontSize: FS.xxs, color: activeProject ? T.sec : T.dim,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            flex: 1, letterSpacing: '0.04em',
          }}>
            {activeProject ? activeProject.name : 'No project'}
          </span>
        )}
      </div>

      {/* Version */}
      <div
        style={{
          padding: sidebarCollapsed ? '8px 0' : '8px 14px',
          textAlign: sidebarCollapsed ? 'center' : 'left',
          borderTop: `1px solid ${T.border}`,
        }}
      >
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>
          {sidebarCollapsed ? `v${APP_VERSION.split('.').slice(0, 2).join('.')}` : `v${APP_VERSION}`}
        </span>
      </div>
    </div>
  )
}
