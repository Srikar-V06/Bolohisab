import { BookOpenText } from 'lucide-react'
import type { ReactNode } from 'react'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import LanguageSelect from '../localization/LanguageSelect'
import { defaultLocale, interfaceLocales, saveLanguage } from '../localization/languages'

export function useInterfaceLanguage() {
  const { i18n } = useTranslation()
  return interfaceLocales.find(locale => locale === i18n.resolvedLanguage) ?? defaultLocale
}

export function AuthLanguage() {
  const { t, i18n } = useTranslation()
  const locale = useInterfaceLanguage()
  return <LanguageSelect compact label={t('common.language')} locales={interfaceLocales} value={locale}
    onChange={language => { saveLanguage('interface', language); void i18n.changeLanguage(language) }} />
}

export default function AuthFrame({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const language = useInterfaceLanguage()
  useEffect(() => {
    document.documentElement.lang = language
    document.title = t('screens.brand') + ' · ' + t('auth.login')
  }, [language, t])

  return <main className="auth-shell">
    <div className="auth-container">
      <header className="auth-header">
        <div className="auth-brand">
          <span className="auth-brand-icon"><BookOpenText size={24} aria-hidden="true" /></span>
          <div>
            <p className="auth-brand-name">{t('screens.brand')}</p>
            <p className="auth-tagline" lang="en-IN">{t('screens.tagline')}</p>
          </div>
        </div>
        <AuthLanguage />
      </header>
      <section className="auth-card">{children}</section>
    </div>
  </main>
}
