/**
 * Validation Store unit tests — covers debounced validation calls,
 * error state management, and stale validation handling.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'

// Mock api client with configurable behavior
const mockPost = vi.fn()
vi.mock('@/api/client', () => ({
  api: {
    get: vi.fn(),
    post: (...args: unknown[]) => mockPost(...args),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

// Mock pipelineStore for error attribution
vi.mock('@/stores/pipelineStore', () => ({
  usePipelineStore: {
    getState: () => ({
      nodes: [
        { id: 'n1', data: { label: 'Data Loader', type: 'data_loader' } },
        { id: 'n2', data: { label: 'Preview', type: 'data_preview' } },
      ],
      edges: [
        { id: 'e1', source: 'n1', target: 'n2' },
      ],
    }),
  },
}))

import { useValidationStore } from '@/stores/validationStore'

describe('ValidationStore', () => {
  beforeEach(() => {
    useValidationStore.setState({
      result: null,
      isValidating: false,
      isStale: false,
      _generation: 0,
      _resultGeneration: -1,
      nodeErrors: {},
      edgeErrors: {},
      panelVisible: false,
    })
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('markStale', () => {
    it('increments generation and sets isStale', () => {
      useValidationStore.getState().markStale()

      const state = useValidationStore.getState()
      expect(state.isStale).toBe(true)
      expect(state._generation).toBe(1)
    })

    it('increments generation each call', () => {
      const store = useValidationStore.getState()
      store.markStale()
      store.markStale()
      store.markStale()

      expect(useValidationStore.getState()._generation).toBe(3)
    })
  })

  describe('validate', () => {
    it('sets result on successful validation', async () => {
      const validResult = {
        valid: true,
        errors: [],
        warnings: [],
        estimated_runtime_s: 10,
        block_count: 2,
        edge_count: 1,
      }
      mockPost.mockResolvedValueOnce(validResult)

      const result = await useValidationStore.getState().validate('pipeline-1')

      expect(result).toBeDefined()
      expect(result!.valid).toBe(true)
      const state = useValidationStore.getState()
      expect(state.result).toEqual(validResult)
      expect(state.isValidating).toBe(false)
      expect(state.isStale).toBe(false)
    })

    it('populates nodeErrors from validation errors', async () => {
      const errorResult = {
        valid: false,
        errors: ["Block 'Data Loader' (n1): missing required config field 'source'"],
        warnings: [],
        estimated_runtime_s: 0,
        block_count: 2,
        edge_count: 1,
      }
      mockPost.mockResolvedValueOnce(errorResult)

      await useValidationStore.getState().validate('pipeline-1')

      const state = useValidationStore.getState()
      expect(state.result?.valid).toBe(false)
      expect(state.nodeErrors['n1']).toBeDefined()
      expect(state.nodeErrors['n1'].length).toBeGreaterThan(0)
      expect(state.nodeErrors['n1'][0].severity).toBe('error')
    })

    it('discards stale results when generation advances', async () => {
      // Simulate a slow validation
      let resolveValidation: (value: unknown) => void
      mockPost.mockImplementationOnce(() =>
        new Promise((resolve) => { resolveValidation = resolve })
      )

      // Start validation at generation 0
      const promise = useValidationStore.getState().validate('pipeline-1')
      expect(useValidationStore.getState().isValidating).toBe(true)

      // Graph changes while validation is in-flight (generation advances)
      useValidationStore.getState().markStale()
      expect(useValidationStore.getState()._generation).toBe(1)

      // Resolve the stale validation
      resolveValidation!({
        valid: true,
        errors: [],
        warnings: [],
        estimated_runtime_s: 5,
        block_count: 2,
        edge_count: 1,
      })

      const result = await promise

      // Result should be discarded (null) because generation advanced
      expect(result).toBeNull()
      // Result state should NOT have been updated
      expect(useValidationStore.getState().result).toBeNull()
    })

    it('returns null for empty pipelineId', async () => {
      const result = await useValidationStore.getState().validate('')
      expect(result).toBeNull()
      expect(useValidationStore.getState().isValidating).toBe(false)
    })

    it('handles API errors gracefully', async () => {
      mockPost.mockRejectedValueOnce(new Error('Server error'))

      const result = await useValidationStore.getState().validate('pipeline-1')

      expect(result).toBeNull()
      expect(useValidationStore.getState().isValidating).toBe(false)
    })

    it('handles null API response', async () => {
      mockPost.mockResolvedValueOnce(null)

      const result = await useValidationStore.getState().validate('pipeline-1')

      expect(result).toBeNull()
      expect(useValidationStore.getState().isValidating).toBe(false)
    })
  })

  describe('clearValidation', () => {
    it('resets all validation state', async () => {
      // First set some state
      useValidationStore.setState({
        result: {
          valid: false,
          errors: ['error'],
          warnings: [],
          estimated_runtime_s: 0,
          block_count: 1,
          edge_count: 0,
        },
        isValidating: true,
        isStale: true,
        _generation: 5,
        _resultGeneration: 3,
        nodeErrors: { n1: [{ nodeId: 'n1', message: 'err', severity: 'error' }] },
        panelVisible: true,
      })

      useValidationStore.getState().clearValidation()

      const state = useValidationStore.getState()
      expect(state.result).toBeNull()
      expect(state.isValidating).toBe(false)
      expect(state.isStale).toBe(false)
      expect(state._generation).toBe(0)
      expect(state._resultGeneration).toBe(-1)
      expect(state.nodeErrors).toEqual({})
      expect(state.edgeErrors).toEqual({})
    })
  })

  describe('Panel visibility', () => {
    it('sets panel visible', () => {
      useValidationStore.getState().setPanelVisible(true)
      expect(useValidationStore.getState().panelVisible).toBe(true)

      useValidationStore.getState().setPanelVisible(false)
      expect(useValidationStore.getState().panelVisible).toBe(false)
    })

    it('toggles panel visibility', () => {
      expect(useValidationStore.getState().panelVisible).toBe(false)

      useValidationStore.getState().togglePanel()
      expect(useValidationStore.getState().panelVisible).toBe(true)

      useValidationStore.getState().togglePanel()
      expect(useValidationStore.getState().panelVisible).toBe(false)
    })
  })
})
