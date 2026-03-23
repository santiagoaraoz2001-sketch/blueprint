import * as Icons from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

/**
 * Type-safe icon lookup from lucide-react.
 * Returns the matching icon component or fallback (Box).
 */
export function getIcon(name: string): LucideIcon {
  const icon = (Icons as Record<string, unknown>)[name]
  if (typeof icon === 'function') return icon as LucideIcon
  // Try PascalCase conversion: 'cpu' -> 'Cpu', 'file-text' -> 'FileText'
  const pascal = name
    .split(/[-_]/)
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase())
    .join('')
  const pascalIcon = (Icons as Record<string, unknown>)[pascal]
  if (typeof pascalIcon === 'function') return pascalIcon as LucideIcon
  return Icons.Box
}
