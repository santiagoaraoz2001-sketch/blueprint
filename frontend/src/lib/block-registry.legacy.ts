// DEPRECATED — Source of truth is now the backend registry API. See registry-client.ts.
// This file will be removed after full migration validation.
//
// block-registry.legacy.ts — old thin wrapper that re-exported types + generated data
//
// Types & utilities (hand-maintained):  block-registry-types.ts
// Block data (auto-generated):          block-registry.generated.ts
//
// To regenerate: python scripts/generate_block_registry.py

export * from './block-registry-types'
export { BLOCK_REGISTRY } from './block-registry.generated'

import { BLOCK_REGISTRY } from './block-registry.generated'
import type { BlockDefinition } from './block-registry-types'

// Group blocks by category
export function getBlocksByCategory(): Record<string, BlockDefinition[]> {
  const groups: Record<string, BlockDefinition[]> = {}
  for (const block of BLOCK_REGISTRY) {
    if (!groups[block.category]) groups[block.category] = []
    groups[block.category].push(block)
  }
  return groups
}

export function getBlockDefinition(type: string): BlockDefinition | undefined {
  const builtin = BLOCK_REGISTRY.find((b) => b.type === type)
  if (builtin) return builtin
  // Search custom blocks from localStorage
  try {
    const raw = localStorage.getItem('blueprint-custom-blocks')
    if (raw) {
      const customs: BlockDefinition[] = JSON.parse(raw)
      return customs.find((b) => b.type === type)
    }
  } catch { /* ignore parse errors */ }
  return undefined
}
