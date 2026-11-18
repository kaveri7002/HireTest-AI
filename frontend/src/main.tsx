import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'
import './index.css'
import App from './App'

registerSW({
  immediate: true,
  onRegisteredSW(_serviceWorkerUrl, registration) {
    if (!registration) return

    const checkForUpdates = () => {
      if (document.visibilityState === 'visible' && navigator.onLine) {
        registration.update().catch((error: unknown) => {
          console.error('Could not check for a HireTest update.', error)
        })
      }
    }

    window.setInterval(checkForUpdates, 5 * 60 * 1000)
    document.addEventListener('visibilitychange', checkForUpdates)
    window.addEventListener('online', checkForUpdates)
  },
  onRegisterError(error) {
    console.error('Could not register the HireTest service worker.', error)
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
