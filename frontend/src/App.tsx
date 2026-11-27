import { useEffect, useRef, useState } from 'react'
import { BookOpenText, Mic, ReceiptText, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import Customers from './Customers'
import Receipts from './Receipts'
import LanguageSelect from './localization/LanguageSelect'
import { defaultLocale, interfaceLocales, saveLanguage } from './localization/languages'
import VoiceEntry from './voice/VoiceEntry'

const pages = [
  { id: 'speak', Icon: Mic, Page: VoiceEntry },
  { id: 'customers', Icon: Users, Page: Customers },
  { id: 'receipts', Icon: ReceiptText, Page: Receipts },
] as const

function getPage() {
  return pages.find(({ id }) => window.location.hash === '#' + id) ?? pages[0]
}

export default function App() {
  const { t, i18n } = useTranslation()
  const [page, setPage] = useState(getPage)
  const main = useRef<HTMLElement>(null)
  const previous = useRef(page)
  const language = interfaceLocales.find((locale) => locale === i18n.resolvedLanguage) ?? defaultLocale
  const title = t(`screens.${page.id}`)
  const { Page } = page

  useEffect(() => {
    const handleHash = () => setPage(getPage())
    window.addEventListener('hashchange', handleHash)
    return () => window.removeEventListener('hashchange', handleHash)
  }, [])

  useEffect(() => {
    document.documentElement.lang = language
    document.title = title + ' | BoloHisaab'
    if (previous.current !== page) {
      main.current?.focus({ preventScroll: true })
      window.scrollTo({ top: 0 })
      previous.current = page
    }
  }, [language, page, title])

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link" onClick={(event) => {
        event.preventDefault()
        main.current?.focus()
      }}>{t('app.skip')}</a>
      <header className="app-header">
        {page.id === 'speak' ? (
          <div className="brand">
            <span className="brand-mark"><BookOpenText size={20} aria-hidden="true" /></span>
            <div><p>{t('screens.brand')}</p><p className="tagline" lang="en-IN">{t('screens.tagline')}</p></div>
          </div>
        ) : <h1>{title}</h1>}
        <LanguageSelect compact label={t('common.language')} locales={interfaceLocales} value={language}
          onChange={(locale) => {
            saveLanguage('interface', locale)
            void i18n.changeLanguage(locale)
          }} />
      </header>
      <main className="page-content" id="main-content" ref={main} tabIndex={-1}>
        <Page language={language} />
      </main>
      <nav aria-label={t('app.navigation')} className="bottom-nav">
        {pages.map(({ id, Icon }) => (
          <a key={id} href={'#' + id} aria-current={page.id === id ? 'page' : undefined}>
            <span className="nav-icon"><Icon size={19} strokeWidth={1.85} aria-hidden="true" /></span>
            <span>{t(`screens.${id}`)}</span>
          </a>
        ))}
      </nav>
    </div>
  )
}
