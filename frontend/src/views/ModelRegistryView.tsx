import { T } from '@/lib/design-tokens'
import ModelRegistry from '@/components/Models/ModelRegistry'

export default function ModelRegistryView() {
  const t = T

  return (
    <div style={{
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      background: t.bg,
    }}>
      <ModelRegistry />
    </div>
  )
}
