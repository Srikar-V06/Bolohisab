import { createInstance } from 'i18next'
import { initReactI18next } from 'react-i18next'
import english from './en-IN.json'
import hindi from './hi-IN.json'
import { englishLocale, interfaceLocales, readLanguage } from './languages'
import type { Locale } from './languages'

const resources = {
  'hi-IN': { translation: hindi },
  'en-IN': { translation: english },
} satisfies Record<Locale, { translation: typeof english }>

export const i18n = createInstance()

export const localizationReady = i18n.use(initReactI18next).init({
  resources,
  lng: readLanguage('interface'),
  supportedLngs: interfaceLocales,
  fallbackLng: englishLocale,
  load: 'currentOnly',
  interpolation: { escapeValue: false, skipOnVariables: true },
})
