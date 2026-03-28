// block-registry.ts — Facade that delegates to registry-client.ts (backend API)
//
// All types & pure utility functions remain in block-registry-types.ts.
// Block DATA now comes from the backend registry, loaded at startup
// via registry-client.ts.  This file preserves the same export surface
// so existing imports across the codebase continue to work.
//
// NOTE: The old `BLOCK_REGISTRY` constant is replaced by `getAllBlocks()`.
// All consumer files have been updated.  Do not re-introduce BLOCK_REGISTRY.

export * from './block-registry-types'

export {
  getBlockDefinition,
  getBlocksByCategory,
  getAllBlocks,
  registry,
} from './registry-client'
