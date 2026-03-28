import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { useMonitorStore } from '@/stores/monitorStore'
import type { LogSeverity } from '@/stores/monitorStore'

// Mock sseManager so startMonitoring doesn't create real EventSources
vi.mock('@/services/sseManager', () => ({
  sseManager: {
    subscribe: vi.fn(() => vi.fn()),
    isStale: vi.fn(() => false),
    getStatus: vi.fn(() => 'connected'),
  },
}))

// Mock framer-motion to avoid animation issues in tests
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, style, ...props }: any) => <div style={style} {...props}>{children}</div>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}))

// Mock api client
vi.mock('@/api/client', () => ({
  api: {
    get: vi.fn().mockResolvedValue(null),
    post: vi.fn().mockResolvedValue(null),
  },
}))

// ── MonitorStore Tests ────────────────────────────────────────────────

describe('monitorStore', () => {
  beforeEach(() => {
    useMonitorStore.getState().reset()
  })

  it('initializes with idle state', () => {
    const state = useMonitorStore.getState()
    expect(state.runId).toBeNull()
    expect(state.runStatus).toBe('idle')
    expect(state.blocks).toEqual({})
    expect(state.logs).toEqual([])
    expect(state.executionOrder).toEqual([])
    expect(state.activeTab).toBe('timeline')
  })

  it('startMonitoring sets run state', () => {
    act(() => {
      useMonitorStore.getState().startMonitoring('run-1')
    })
    const state = useMonitorStore.getState()
    expect(state.runId).toBe('run-1')
    expect(state.runStatus).toBe('running')
    expect(state.runStartTime).toBeGreaterThan(0)
  })

  it('setActiveTab switches tabs', () => {
    act(() => {
      useMonitorStore.getState().setActiveTab('logs')
    })
    expect(useMonitorStore.getState().activeTab).toBe('logs')

    act(() => {
      useMonitorStore.getState().setActiveTab('outputs')
    })
    expect(useMonitorStore.getState().activeTab).toBe('outputs')
  })

  it('reset clears all state', () => {
    act(() => {
      useMonitorStore.getState().startMonitoring('run-1')
      useMonitorStore.getState().setActiveTab('logs')
    })
    act(() => {
      useMonitorStore.getState().reset()
    })
    const state = useMonitorStore.getState()
    expect(state.runId).toBeNull()
    expect(state.runStatus).toBe('idle')
    expect(state.activeTab).toBe('timeline')
  })
})


// ── ExecutionTimeline Component Tests ─────────────────────────────────

describe('ExecutionTimeline', () => {
  beforeEach(() => {
    useMonitorStore.getState().reset()
  })

  it('renders empty state when no blocks', async () => {
    const ExecutionTimeline = (await import('../ExecutionTimeline')).default
    render(<ExecutionTimeline />)
    expect(screen.getByText(/run a pipeline/i)).toBeInTheDocument()
  })

  it('renders bars for completed blocks', async () => {
    const now = Date.now()
    act(() => {
      useMonitorStore.setState({
        runId: 'run-1',
        runStartTime: now - 5000,
        runStatus: 'complete',
        blocks: {
          'node-1': {
            nodeId: 'node-1',
            blockType: 'llm_inference',
            category: 'inference',
            label: 'LLM Inference',
            index: 0,
            total: 2,
            status: 'complete',
            startTime: now - 5000,
            endTime: now - 3000,
            durationMs: 2000,
          },
          'node-2': {
            nodeId: 'node-2',
            blockType: 'data_export',
            category: 'data',
            label: 'Data Export',
            index: 1,
            total: 2,
            status: 'complete',
            startTime: now - 3000,
            endTime: now - 1000,
            durationMs: 2000,
          },
        },
        executionOrder: ['node-1', 'node-2'],
      })
    })

    const ExecutionTimeline = (await import('../ExecutionTimeline')).default
    render(<ExecutionTimeline />)

    // Block labels should be visible
    expect(screen.getByText('LLM Inference')).toBeInTheDocument()
    expect(screen.getByText('Data Export')).toBeInTheDocument()

    // SVG should contain rect elements (bars)
    const rects = document.querySelectorAll('rect')
    expect(rects.length).toBeGreaterThanOrEqual(2)
  })

  it('shows popover on bar click', async () => {
    const now = Date.now()
    act(() => {
      useMonitorStore.setState({
        runId: 'run-1',
        runStartTime: now - 5000,
        runStatus: 'complete',
        blocks: {
          'node-1': {
            nodeId: 'node-1',
            blockType: 'llm_inference',
            category: 'inference',
            label: 'Test Block',
            index: 0,
            total: 1,
            status: 'complete',
            startTime: now - 5000,
            endTime: now - 3000,
            durationMs: 2000,
            primaryOutputType: 'text',
            artifactCount: 3,
          },
        },
        executionOrder: ['node-1'],
      })
    })

    const ExecutionTimeline = (await import('../ExecutionTimeline')).default
    render(<ExecutionTimeline />)

    const bars = document.querySelectorAll('rect[rx="3"]')
    expect(bars.length).toBeGreaterThan(0)
    fireEvent.click(bars[0], { clientX: 300, clientY: 50 })

    // Popover should show details
    expect(screen.getByText('complete')).toBeInTheDocument()
    expect(screen.getByText('llm_inference')).toBeInTheDocument()
  })
})


// ── LogViewer Component Tests ─────────────────────────────────────────

describe('LogViewer', () => {
  beforeEach(() => {
    useMonitorStore.getState().reset()
  })

  it('renders empty state when no logs', async () => {
    const LogViewer = (await import('../LogViewer')).default
    render(<LogViewer />)
    expect(screen.getByText(/waiting for log output/i)).toBeInTheDocument()
  })

  it('renders log lines with node badges and severity', async () => {
    const now = Date.now()
    act(() => {
      useMonitorStore.setState({
        logs: [
          { timestamp: now, nodeId: 'n1', nodeName: 'Block A', severity: 'info' as LogSeverity, message: 'Processing started' },
          { timestamp: now + 100, nodeId: 'n1', nodeName: 'Block A', severity: 'warn' as LogSeverity, message: 'Slow operation' },
          { timestamp: now + 200, nodeId: 'n2', nodeName: 'Block B', severity: 'error' as LogSeverity, message: 'Connection failed' },
        ],
        blocks: {
          'n1': { nodeId: 'n1', blockType: 'test', category: 'test', label: 'Block A', index: 0, total: 2, status: 'complete', startTime: now, endTime: now + 200, durationMs: 200 },
          'n2': { nodeId: 'n2', blockType: 'test', category: 'test', label: 'Block B', index: 1, total: 2, status: 'failed', startTime: now + 100, endTime: now + 300, durationMs: 200 },
        },
      })
    })

    const LogViewer = (await import('../LogViewer')).default
    render(<LogViewer />)

    expect(screen.getByText('Processing started')).toBeInTheDocument()
    expect(screen.getByText('Slow operation')).toBeInTheDocument()
    expect(screen.getByText('Connection failed')).toBeInTheDocument()
  })

  it('filters logs by node selection', async () => {
    const now = Date.now()
    act(() => {
      useMonitorStore.setState({
        logs: [
          { timestamp: now, nodeId: 'n1', nodeName: 'Block A', severity: 'info' as LogSeverity, message: 'Message from A' },
          { timestamp: now + 100, nodeId: 'n2', nodeName: 'Block B', severity: 'info' as LogSeverity, message: 'Message from B' },
        ],
        blocks: {},
      })
    })

    const LogViewer = (await import('../LogViewer')).default
    render(<LogViewer />)

    expect(screen.getByText('Message from A')).toBeInTheDocument()
    expect(screen.getByText('Message from B')).toBeInTheDocument()

    // Open dropdown and select Block A
    fireEvent.click(screen.getByText('All Nodes'))
    // The dropdown options are buttons — find the one in the dropdown menu
    const dropdownButtons = screen.getAllByRole('button')
    const blockABtn = dropdownButtons.find(
      (btn) => btn.textContent === 'Block A' && btn.tagName === 'BUTTON'
    )!
    fireEvent.click(blockABtn)

    expect(screen.getByText('Message from A')).toBeInTheDocument()
    expect(screen.queryByText('Message from B')).not.toBeInTheDocument()
  })

  it('filters logs by severity toggle', async () => {
    const now = Date.now()
    act(() => {
      useMonitorStore.setState({
        logs: [
          { timestamp: now, nodeId: 'n1', nodeName: 'Block A', severity: 'info' as LogSeverity, message: 'Info message' },
          { timestamp: now + 100, nodeId: 'n1', nodeName: 'Block A', severity: 'error' as LogSeverity, message: 'Error message' },
        ],
        blocks: {},
      })
    })

    const LogViewer = (await import('../LogViewer')).default
    render(<LogViewer />)

    expect(screen.getByText('Info message')).toBeInTheDocument()
    expect(screen.getByText('Error message')).toBeInTheDocument()

    // Uncheck info checkbox (index 1: debug=0, info=1, warn=2, error=3)
    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[1]) // info checkbox

    expect(screen.queryByText('Info message')).not.toBeInTheDocument()
    expect(screen.getByText('Error message')).toBeInTheDocument()
  })

  it('filters by text search', async () => {
    const now = Date.now()
    act(() => {
      useMonitorStore.setState({
        logs: [
          { timestamp: now, nodeId: 'n1', nodeName: 'Block A', severity: 'info' as LogSeverity, message: 'Loading dataset' },
          { timestamp: now + 100, nodeId: 'n1', nodeName: 'Block A', severity: 'info' as LogSeverity, message: 'Training model' },
        ],
        blocks: {},
      })
    })

    const LogViewer = (await import('../LogViewer')).default
    render(<LogViewer />)

    const searchInput = screen.getByPlaceholderText('Search logs...')
    fireEvent.change(searchInput, { target: { value: 'dataset' } })

    expect(screen.getByText('Loading dataset')).toBeInTheDocument()
    expect(screen.queryByText('Training model')).not.toBeInTheDocument()
  })
})
