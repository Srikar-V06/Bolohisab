import { useEffect, useRef, useState } from 'react'
import {
  BadgeAlert, BookOpen, ChartNoAxesColumnIncreasing, FlaskConical,
  LayoutDashboard, Mic, Store, Users,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import Dashboard, { CustomerAvatar, WeeklySummary } from './Dashboard'
import LanguageSelect from './localization/LanguageSelect'
import { defaultLocale, interfaceLocales, saveLanguage } from './localization/languages'
import { customers, dashboard, disputes, formatRupees, shopName } from './sampleData'
import VoiceEntry from './voice/VoiceEntry'

const navigation = [
  { id: 'dashboard', icon: LayoutDashboard },
  { id: 'customers', icon: Users },
  { id: 'voice-entry', icon: Mic },
  { id: 'disputes', icon: BadgeAlert },
  { id: 'reports', icon: ChartNoAxesColumnIncreasing },
] as const

type PageId = (typeof navigation)[number]['id']

function getPage(): PageId {
  const id = window.location.hash.slice(1)
  return navigation.find((item) => item.id === id)?.id ?? 'dashboard'
}

function Brand() {
  const { t } = useTranslation()

  return (
    <a href="#dashboard" aria-label={t('app.brandLink')} className="brand">
      <span className="brand-mark"><BookOpen size={22} strokeWidth={2.25} aria-hidden="true" /></span>
      <span>Bolo<span className="text-primary">Hisaab</span></span>
    </a>
  )
}

function Customers() {
  const { t } = useTranslation()

  return (
    <section>
      <h1 tabIndex={-1} className="page-heading">{t('nav.customers')}</h1>
      <p className="page-intro">{t('customers.intro')}</p>
      <ul className="panel mt-6 max-w-[46rem] divide-y divide-line px-4 sm:px-6">
        {customers.map((customer) => (
          <li key={customer.name} className="activity-row">
            <CustomerAvatar customer={customer} />
            <p className="text-sm font-extrabold sm:text-base">{customer.name}</p>
            <p className="text-right text-sm font-extrabold tabular-nums sm:text-base">
              {customer.balance ? formatRupees(customer.balance) : t('customers.paidUp')}
            </p>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Disputes() {
  const { t } = useTranslation()

  return (
    <section>
      <h1 tabIndex={-1} className="page-heading">{t('nav.disputes')}</h1>
      <p className="page-intro">{t('disputes.intro', { count: dashboard.openDisputes })}</p>
      <ul className="panel mt-6 max-w-[46rem] divide-y divide-line px-4 sm:px-6">
        {disputes.map(({ customer, amount, issue }) => (
          <li key={customer.name} className="activity-row">
            <CustomerAvatar customer={customer} />
            <div>
              <p className="text-sm font-extrabold sm:text-base">{customer.name}</p>
              <p className="mt-1 text-sm text-muted">{t(`disputes.${issue}`)}</p>
            </div>
            <p className="text-right text-sm font-extrabold tabular-nums sm:text-base">{formatRupees(amount)}</p>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Reports() {
  const { t } = useTranslation()

  return (
    <>
      <div>
        <h1 tabIndex={-1} className="page-heading">{t('nav.reports')}</h1>
        <p className="page-intro">{t('reports.intro')}</p>
      </div>
      <div className="max-w-[40rem]"><WeeklySummary /></div>
    </>
  )
}

const pages = {
  dashboard: Dashboard,
  customers: Customers,
  'voice-entry': VoiceEntry,
  disputes: Disputes,
  reports: Reports,
} satisfies Record<PageId, () => React.ReactNode>

export default function App() {
  const { t, i18n } = useTranslation()
  const [page, setPage] = useState(getPage)
  const previousPage = useRef(page)
  const main = useRef<HTMLElement>(null)
  const language = interfaceLocales.find((locale) => locale === i18n.resolvedLanguage) ?? defaultLocale
  const pageLabel = t(`nav.${page}`)
  const description = t('meta.description')
  const Page = pages[page]

  useEffect(() => {
    const handleHashChange = () => setPage(getPage())
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  useEffect(() => {
    document.documentElement.lang = language
    document.title = `${pageLabel} | BoloHisaab`
    document.querySelector('meta[name="description"]')?.setAttribute('content', description)
    if (previousPage.current !== page) {
      main.current?.querySelector('h1')?.focus({ preventScroll: true })
      window.scrollTo({ top: 0 })
      previousPage.current = page
    }
  }, [description, language, page, pageLabel])

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link" onClick={(event) => {
        event.preventDefault()
        main.current?.focus()
      }}>{t('app.skip')}</a>
      <aside className="sidebar">
        <div className="sidebar-brand"><Brand /></div>
        <nav aria-label={t('app.navigation')} className="navigation">
          {navigation.map(({ id, icon: Icon }) => (
            <a key={id} href={`#${id}`} aria-current={page === id ? 'page' : undefined} className="nav-link">
              <Icon size={20} strokeWidth={1.9} aria-hidden="true" className="shrink-0" />
              <span>{t(`nav.${id}`)}</span>
            </a>
          ))}
        </nav>
        <div className="shop-card hidden md:flex">
          <span className="stat-icon avatar-sage"><Store size={18} aria-hidden="true" /></span>
          <div>
            <p className="text-sm font-extrabold">{shopName}</p>
            <p className="mt-0.5 text-xs text-muted">{t('app.shopWorkspace')}</p>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="md:hidden"><Brand /></div>
          <p className="hidden items-center gap-3 text-sm md:flex">
            <span className="font-semibold text-muted">{t('app.workspace')}</span>
            <span aria-hidden="true" className="text-[#85958d]">/</span>
            <span className="font-extrabold">{pageLabel}</span>
          </p>
          <span className="sample-label topbar-sample"><FlaskConical size={15} aria-hidden="true" /> {t('app.sampleData')}</span>
          <LanguageSelect
            compact
            label={t('app.language')}
            locales={interfaceLocales}
            value={language}
            onChange={(locale) => {
              saveLanguage('interface', locale)
              void i18n.changeLanguage(locale)
            }}
          />
        </header>
        <main ref={main} id="main-content" tabIndex={-1} className="content">
          <Page />
        </main>
      </div>
    </div>
  )
}
