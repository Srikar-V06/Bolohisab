import { ArrowDownLeft, ArrowUpRight, ChevronRight, MessageCircle } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { Customer, Receipt } from './api'
import { initials, money } from './format'
import type { Locale } from './localization/languages'

const DAY = 86_400_000
const indiaDay = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' })

function daysSince(value: string | null, now: number) {
  return value ? Math.max(0, Math.floor((now - Date.parse(value)) / DAY)) : 0
}

/** Shop overview: dues by last activity, top debtors, today's totals and who to ask for payment. */
export default function Dashboard({ customers, receipts, language, children }: {
  customers: Customer[]; receipts?: Receipt[]; language: Locale; children: ReactNode
}) {
  const { t } = useTranslation()
  const now = Date.now()
  const owing = customers.filter(({ balance_paise }) => balance_paise > 0)
  const total = owing.reduce((sum, { balance_paise }) => sum + BigInt(balance_paise), 0n)
  // ponytail: ages dues by the customer's last entry, not by the oldest unpaid credit; needs per-entry ageing from the API to be exact.
  const buckets = [0n, 0n, 0n]
  for (const row of owing) {
    const days = daysSince(row.last_transaction_at, now)
    buckets[days <= 7 ? 0 : days <= 30 ? 1 : 2] += BigInt(row.balance_paise)
  }
  const top = owing.slice().sort((a, b) => b.balance_paise - a.balance_paise).slice(0, 8)
  const ask = owing.slice()
    .sort((a, b) => daysSince(b.last_transaction_at, now) - daysSince(a.last_transaction_at, now) || b.balance_paise - a.balance_paise)
    .slice(0, 3)
  const today = indiaDay.format(now)
  const todays = (receipts ?? []).filter(({ created_at }) => indiaDay.format(new Date(created_at)) === today)
  const sum = (type: Receipt['type']) => todays.filter((row) => row.type === type).reduce((s, row) => s + row.amount_paise, 0)

  return (
    <div className="dashboard">
      <section className="khata-page" aria-labelledby="khata-title">
        <header className="khata-head">
          <h2 id="khata-title">{t('home.owedToYou')}</h2>
          <p className="khata-count">{t('customerList.count', { count: owing.length })}</p>
        </header>
        <strong className="khata-total">{money(total)}</strong>
        {total > 0n && <dl className="khata-lines" aria-label={t('home.ageing')}>
          {buckets.map((amount, index) => (
            <div key={index} data-age={index}>
              <dt>{t(`home.age${index as 0 | 1 | 2}`)}</dt>
              <dd className={index === 2 && amount > 0n ? 'red' : undefined}>{money(amount)}</dd>
            </div>
          ))}
        </dl>}
        {receipts && <dl className="khata-lines khata-today" aria-label={t('home.today')}>
          <div><dt><ArrowUpRight size={15} aria-hidden="true" className="red" />{t('home.creditToday')}</dt>
            <dd className="red">{money(sum('CREDIT'))}</dd></div>
          <div><dt><ArrowDownLeft size={15} aria-hidden="true" className="green" />{t('home.paidToday')}</dt>
            <dd className="green">{money(sum('PAYMENT'))}</dd></div>
        </dl>}
      </section>

      {children}

      {top.length > 0 && <section className="dash-section">
        <header className="dash-heading">
          <h2>{t('home.topDues')}</h2>
          <a href="#customers">{t('home.seeAll')}<ChevronRight size={15} aria-hidden="true" /></a>
        </header>
        <ul className="people-strip">
          {top.map((row) => (
            <li key={row.id}><a href="#customers">
              <span className="people-avatar" aria-hidden="true">{initials(row.name, language)}</span>
              <span className="people-name">{row.name.split(/\s+/)[0]}</span>
              <strong className="red">{money(row.balance_paise)}</strong>
            </a></li>
          ))}
        </ul>
      </section>}

      {ask.length > 0 && <section className="dash-section">
        <h2>{t('home.askToday')}</h2>
        <ul className="ask-list card">
          {ask.map((row) => {
            const days = daysSince(row.last_transaction_at, now)
            const message = t('home.remindText', { name: row.name, amount: money(row.balance_paise) })
            return (
              <li key={row.id}>
                <span className="customer-initial bg-surface" aria-hidden="true">{initials(row.name, language)}</span>
                <span className="list-copy">
                  <strong>{row.name}</strong>
                  <span className={days > 30 ? 'status-chip overdue' : 'status-chip amber'}>{days ? t('home.daysSince', { count: days }) : t('home.lastToday')}</span>
                </span>
                <span className="ask-actions">
                  <strong className="red">{money(row.balance_paise)}</strong>
                  <a className="remind-pill" target="_blank" rel="noreferrer"
                    href={'https://wa.me/?text=' + encodeURIComponent(message)}
                    aria-label={t('home.remindLabel', { name: row.name })}>
                    <MessageCircle size={14} aria-hidden="true" />{t('home.remind')}
                  </a>
                </span>
              </li>
            )
          })}
        </ul>
      </section>}
    </div>
  )
}
