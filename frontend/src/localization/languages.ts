export const languageNames = {
  'hi-IN': { interface: 'हिन्दी', speech: 'हिन्दी' },
  'en-IN': { interface: 'English', speech: 'English (India)' },
} as const

export type Locale = keyof typeof languageNames

export const interfaceLocales = Object.keys(languageNames) as Locale[]
export const speechLocales = ['hi-IN', 'en-IN'] as const satisfies readonly Locale[]
export const defaultLocale: Locale = 'hi-IN'
export const englishLocale: Locale = 'en-IN'

const preferences = {
  interface: { key: 'bolohisaab.interface-language', locales: interfaceLocales },
  speech: { key: 'bolohisaab.speech-language', locales: speechLocales },
  receipt: { key: 'bolohisaab.receipt-language', locales: interfaceLocales },
} as const

type Preference = keyof typeof preferences

export function readLanguage(preference: Preference): Locale {
  const { key, locales } = preferences[preference]
  try {
    const stored = window.localStorage.getItem(key)
    return locales.find((locale) => locale === stored) ?? defaultLocale
  } catch {
    return defaultLocale
  }
}

export function saveLanguage(preference: Preference, locale: Locale) {
  try {
    window.localStorage.setItem(preferences[preference].key, locale)
  } catch {
    // Language switching remains available when browser storage is blocked.
  }
}
