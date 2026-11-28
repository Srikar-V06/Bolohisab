import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/inter'
import '@fontsource-variable/noto-sans-devanagari'
import '@fontsource-variable/baloo-2'
import AuthenticatedApp from './auth/AuthenticatedApp'
import { localizationReady } from './localization/i18n'
import './styles.css'

void localizationReady.then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <AuthenticatedApp />
    </StrictMode>,
  )
})
