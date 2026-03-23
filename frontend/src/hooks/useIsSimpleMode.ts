import { useSettingsStore } from '@/stores/settingsStore'

export function useIsSimpleMode(): boolean {
  return useSettingsStore((s) => s.uiMode === 'simple')
}
