import { useCallback, useState } from 'react'
import { ArrowDownUp, ChevronRight, Search } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from './api'
import type { Customer } from './api'
import { initials, money, transactionDate, transactionDays, transactionLabel } from './format'
import type { Locale } from './localization/languages'
import { LoadError, Loading, Sheet, useLoad } from './components'

const filters = ['all', 'outstanding', 'settled'] as const
type Filter = typeof filters[number]

function filterCustomers(customers: Customer[], search: string, filter: Filter) {
  const query = search.trim().normalize().toLocaleLowerCase()
  return customers.filter(({ name, balance_paise }) =>
    name.normalize().toLocaleLowerCase().includes(query)
    && (filter === 'all' || (filter === 'outstanding' ? balance_paise > 0 : balance_paise <= 0)),
  )
}

function avatarTint(name: string) {
  let hash = 0
  for (const letter of name.normalize()) hash = (hash * 31 + letter.codePointAt(0)!) >>> 0
  return ['bg-surface', 'bg-line', 'bg-muted/15'][hash % 3]
}

function CustomerDetail({ customer, language, close }: { customer: Customer; language: Locale; close: () => void }) {
  const { t } = useTranslation()
  const load = useCallback((signal: AbortSignal) => api.ledger(customer.id, signal), [customer.id])
  const { data, error, retry } = useLoad(load)

  let balance = 0n
  const posted = (data ?? []).map(entry => {
    const amount = BigInt(entry.amount_paise)
    balance += entry.type === 'PAYMENT' ? -amount : amount
    return { ...entry, balance }
  })

  return (
    <Sheet title={customer.name} close={close}>
      <div className="summary-card card">
        <p className="subtle">{t('customerList.total')}</p>
        <p className="summary-value font-display">{money(Math.max(0, customer.balance_paise))}</p>
      </div>
      <h3 className="sheet-section">{t('customerList.history')}</h3>
      {error ? <LoadError error={error} retry={retry} /> : !data ? <Loading text={t('common.loading')} />
        : data.length === 0 ? <p className="notice">{t('customerList.lastEmpty')}</p>
          : transactionDays(posted.reverse(), language).map(day => (
          <section key={day.key} className="ledger-day">
            <h4>{day.label}</h4>
            <ul className="history-list">{day.entries.map((entry) => (
              <li key={entry.id}>
                <div>
                  <p>{transactionLabel(t, entry.type, entry.payment_method)}</p>
                  <time className="subtle" dateTime={entry.created_at}>{transactionDate(entry.created_at, language)}</time>
                </div>
                <div className="text-right"><strong className={entry.type === 'CREDIT' ? 'red' : entry.type === 'PAYMENT' ? 'green' : undefined}>
                  {money(entry.amount_paise)}
                </strong>
                  <p className="subtle font-display tabular-nums">{t('customerList.after', { amount: money(entry.balance) })}</p>
                </div>
              </li>
            ))}</ul>
          </section>))}
      <div className="info-row current-total"><span>{t('customerList.current')}</span><strong>{money(customer.balance_paise)}</strong></div>
    </Sheet>
  )
}

export default function Customers({ language }: { language: Locale }) {
  const { t } = useTranslation()
  const { data, error, retry } = useLoad(api.customers)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [highestFirst, setHighestFirst] = useState(true)
  const [selected, setSelected] = useState<Customer>()
  const withDues = data?.filter(({ balance_paise }) => balance_paise > 0) ?? []
  const total = withDues.reduce((sum, row) => sum + BigInt(row.balance_paise), 0n)
  const visible = data ? filterCustomers(data, search, filter).sort((a, b) =>
    (highestFirst ? b.balance_paise - a.balance_paise : a.balance_paise - b.balance_paise)
    || a.name.localeCompare(b.name, language) || a.id - b.id) : []

  return (
    <div className="customers-page">
      {error ? <LoadError error={error} retry={retry} /> : !data ? <Loading text={t('common.loading')} /> : (
        <>
          <section className="summary-card card" aria-label={t('customerList.total')}>
            <p className="subtle">{t('customerList.total')}</p>
            <p className="summary-value font-display">{money(total)}</p>
            <div className="customer-split">
              <span>{t('customerList.count', { count: withDues.length })}</span>
              <span>{t('customerList.settledCount', { count: data.length - withDues.length })}</span>
            </div>
          </section>
          <label className="search-input card">
            <Search size={19} aria-hidden="true" />
            <span className="sr-only">{t('customerList.search')}</span>
            <input type="search" placeholder={t('customerList.search')} value={search}
              onChange={(event) => setSearch(event.target.value)} />
          </label>
          <div className="filter-chips" role="group" aria-label={t('customerList.filters')}>
            {filters.map((option) => (
              <button key={option} type="button" aria-pressed={filter === option} onClick={() => setFilter(option)}>
                {t(`customerList.${option}`)}
              </button>
            ))}
          </div>
          {visible.length > 1 && <button type="button" className="customer-sort" onClick={() => setHighestFirst(!highestFirst)}>
            <ArrowDownUp size={16} aria-hidden="true" />{t(highestFirst ? 'customerList.highest' : 'customerList.lowest')}
          </button>}
          {visible.length === 0 ? <div className="notice">{t(data.length ? 'customerList.noResults' : 'customerList.empty')}
              {data.length > 0 && <button type="button" className="customer-sort" onClick={() => { setSearch(''); setFilter('all') }}>
                {t('customerList.clear')}
              </button>}
            </div>
            : <ul className="customer-register">
              {visible.map((customer) => {
                const outstanding = customer.balance_paise > 0
                return (
                  <li key={customer.id}>
                    <button className="customer-row" type="button" onClick={() => setSelected(customer)}>
                      <span className={'customer-initial ' + avatarTint(customer.name)} aria-hidden="true">{initials(customer.name, language)}</span>
                      <span className="list-copy">
                        <strong>{customer.name}</strong>
                        {customer.last_transaction_at
                          ? <time className="subtle" dateTime={customer.last_transaction_at}>{transactionDate(customer.last_transaction_at, language)}</time>
                          : <span className="subtle">{t('customerList.lastEmpty')}</span>}
                      </span>
                      <span className={outstanding ? 'list-amount red' : 'list-amount text-muted'}>
                        <strong>{money(customer.balance_paise)}</strong>
                        <span>{t(outstanding ? 'customerList.outstanding' : 'customerList.settled')}</span>
                      </span>
                      <ChevronRight size={15} className="text-muted" aria-hidden="true" />
                    </button>
                  </li>
                )
              })}
            </ul>}
        </>
      )}
      {selected && <CustomerDetail customer={selected} language={language} close={() => setSelected(undefined)} />}
    </div>
  )
}
