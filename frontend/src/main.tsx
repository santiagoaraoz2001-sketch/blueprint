import React from 'react'
import ReactDOM from 'react-dom/client'
import { Toaster } from 'react-hot-toast'
import App from './App'
import './index.css'
import { useSettingsStore } from '@/stores/settingsStore'
import { getTheme } from '@/lib/design-tokens'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const queryClient = new QueryClient()

/** Reactive toast styles that respect current theme */
function ThemedToaster() {
  const theme = useSettingsStore((s) => s.theme)
  const t = getTheme(theme)
  return (
    <Toaster
      position="bottom-right"
      toastOptions={{
        style: {
          background: t.surface3,
          color: t.sec,
          border: `1px solid ${t.borderHi}`,
          borderRadius: '0px',
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: '11px',
        },
      }}
    />
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
      <ThemedToaster />
    </QueryClientProvider>
  </React.StrictMode>
)
