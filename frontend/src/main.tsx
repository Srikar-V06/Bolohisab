import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/inter'
import '@fontsource-variable/noto-sans-devanagari'
import '@fontsource-variable/baloo-2'
import App from './App'
import { localizationReady } from './localization/i18n'
import './styles.css'

void localizationReady.then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})
