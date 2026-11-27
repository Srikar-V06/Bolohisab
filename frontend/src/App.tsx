import { useEffect, useRef, useState } from 'react'
import {
  BadgeAlert, BookOpen, ChartNoAxesColumnIncreasing, FlaskConical,
  LayoutDashboard, Mic, Store, Users,
} from 'lucide-react'
import Dashboard, { CustomerAvatar, WeeklySummary } from './Dashboard'
import { customers, dashboard, disputes, formatRupees } from './sampleData'

const navigation = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'customers', label: 'Customers', icon: Users },
  { id: 'voice-entry', label: 'Voice Entry', icon: Mic },
  { id: 'disputes', label: 'Disputes', icon: BadgeAlert },
  { id: 'reports', label: 'Reports', icon: ChartNoAxesColumnIncreasing },
] as const

type PageId = (typeof navigation)[number]['id']

function getPage(): PageId {
  const id = window.location.hash.slice(1)
  return navigation.find((item) => item.id === id)?.id ?? 'dashboard'
}

function Brand() {
  return (
    <a href="#dashboard" aria-label="BoloHisaab dashboard" className="brand">
      <span className="brand-mark"><BookOpen size={22} strokeWidth={2.25} aria-hidden="true" /></span>
      <span>Bolo<span className="text-primary">Hisaab</span></span>
    </a>
  )
}

function Customers() {
  return (
    <section>
      <h1 tabIndex={-1} className="page-heading">Customers</h1>
      <p className="page-intro">A sample of customers and their current khata balances.</p>
      <ul className="panel mt-6 max-w-[46rem] divide-y divide-line px-4 sm:px-6">
        {customers.map((customer) => (
          <li key={customer.name} className="activity-row">
            <CustomerAvatar customer={customer} />
            <p className="text-sm font-extrabold sm:text-base">{customer.name}</p>
            <p className="text-right text-sm font-extrabold tabular-nums sm:text-base">
              {customer.balance ? formatRupees(customer.balance) : 'Paid up'}
            </p>
          </li>
        ))}
      </ul>
    </section>
  )
}

function VoiceEntry() {
  const [showPreview, setShowPreview] = useState(false)

  return (
    <section>
      <h1 tabIndex={-1} className="page-heading">Voice Entry</h1>
      <p className="page-intro">Try reviewing a sample khata entry.</p>
      <div className="panel mt-6 max-w-[40rem] p-5 sm:p-6">
        <span className="stat-icon avatar-sage"><Mic size={20} aria-hidden="true" /></span>
        <h2 className="section-heading mt-4">Sample phrase</h2>
        <blockquote lang="hi-Latn" className="mt-3 rounded-xl bg-surface px-4 py-3 font-bold">
          “Priya Sharma ne 750 rupaye diye.”
        </blockquote>
        <button
          type="button"
          className="button button-primary mt-4"
          aria-expanded={showPreview}
          aria-controls="entry-preview"
          onClick={() => setShowPreview((visible) => !visible)}
        >
          {showPreview ? 'Hide entry preview' : 'Preview entry'}
        </button>
        <div id="entry-preview" hidden={!showPreview} className="mt-5 border-t border-line pt-4">
          <h3 className="font-extrabold">Sample payment</h3>
          <dl className="mt-2 divide-y divide-line">
            <div className="summary-row"><dt>Customer</dt><dd>Priya Sharma</dd></div>
            <div className="summary-row"><dt>Amount received</dt><dd>{formatRupees(750)}</dd></div>
          </dl>
        </div>
      </div>
    </section>
  )
}

function Disputes() {
  return (
    <section>
      <h1 tabIndex={-1} className="page-heading">Disputes</h1>
      <p className="page-intro">{dashboard.openDisputes} sample entries awaiting review.</p>
      <ul className="panel mt-6 max-w-[46rem] divide-y divide-line px-4 sm:px-6">
        {disputes.map(({ customer, amount, issue }) => (
          <li key={customer.name} className="activity-row">
            <CustomerAvatar customer={customer} />
            <div>
              <p className="text-sm font-extrabold sm:text-base">{customer.name}</p>
              <p className="mt-1 text-sm text-muted">{issue}</p>
            </div>
            <p className="text-right text-sm font-extrabold tabular-nums sm:text-base">{formatRupees(amount)}</p>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Reports() {
  return (
    <>
      <div>
        <h1 tabIndex={-1} className="page-heading">Reports</h1>
        <p className="page-intro">Review a sample week of payments and new credit.</p>
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
  const [page, setPage] = useState(getPage)
  const previousPage = useRef(page)
  const main = useRef<HTMLElement>(null)
  const currentItem = navigation.find((item) => item.id === page)!
  const Page = pages[page]

  useEffect(() => {
    const handleHashChange = () => setPage(getPage())
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  useEffect(() => {
    document.title = `${currentItem.label} | BoloHisaab`
    if (previousPage.current !== page) {
      main.current?.querySelector('h1')?.focus({ preventScroll: true })
      window.scrollTo({ top: 0 })
      previousPage.current = page
    }
  }, [currentItem.label, page])

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link" onClick={(event) => {
        event.preventDefault()
        main.current?.focus()
      }}>Skip to content</a>
      <aside className="sidebar">
        <div className="sidebar-brand"><Brand /></div>
        <nav aria-label="Main navigation" className="navigation">
          {navigation.map(({ id, label, icon: Icon }) => (
            <a key={id} href={`#${id}`} aria-current={page === id ? 'page' : undefined} className="nav-link">
              <Icon size={20} strokeWidth={1.9} aria-hidden="true" />
              <span>{label}</span>
            </a>
          ))}
        </nav>
        <div className="shop-card hidden md:flex">
          <span className="stat-icon avatar-sage"><Store size={18} aria-hidden="true" /></span>
          <div>
            <p className="text-sm font-extrabold">Sharma Kirana</p>
            <p className="mt-0.5 text-xs text-muted">Shop workspace</p>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="md:hidden"><Brand /></div>
          <p className="hidden items-center gap-3 text-sm md:flex">
            <span className="font-semibold text-muted">Workspace</span>
            <span aria-hidden="true" className="text-[#85958d]">/</span>
            <span className="font-extrabold">{currentItem.label}</span>
          </p>
          <span className="sample-label"><FlaskConical size={15} aria-hidden="true" /> Sample data</span>
        </header>
        <main ref={main} id="main-content" tabIndex={-1} className="content">
          <Page />
        </main>
      </div>
    </div>
  )
}
