import { useRef, useState } from 'react'
import { ArrowDownUp, ChevronRight, Search } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from './api'
import type { Customer } from './api'
import { initials, money, transactionDate, transactionDays } from './format'
import type { Locale } from './localization/languages'
import { LoadError, Loading, useLoad } from './components'
import ResponsiveDetail from './ResponsiveDetail'
import { useLedgerHistory } from './useLedgerHistory'

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
  const { entries, error, loading, nextCursor, loadNext } = useLedgerHistory(customer.id)
  const currentBalance = entries ? entries[0]?.balance_after_paise ?? 0 : customer.balance_paise

  return (
    <ResponsiveDetail title={customer.name} close={close}>
      <div className="summary-card card">
        <p className="subtle">{t('customerList.total')}</p>
        <p className="summary-value font-display">{money(Math.max(0, currentBalance))}</p>
      </div>
      <h3 className="sheet-section">{t('customerList.history')}</h3>
      {entries === undefined ? !error && <Loading rows={5} text={t('common.loading')} />
        : entries.length === 0 ? <p className="notice">{t('customerList.lastEmpty')}</p>
          : transactionDays(entries, language).map(day => (
          <section key={day.key} className="ledger-day">
            <h4>{day.label}</h4>
            <ul className="history-list">{day.entries.map((entry) => (
              <li key={entry.id}>
                <div>
                  <p>{t(`entry.type.${entry.type}`)}</p>
                  {entry.payment_method && <p className="subtle">{t(`entry.method.${entry.payment_method}`)}</p>}
                  <time className="subtle" dateTime={entry.created_at}>{transactionDate(entry.created_at, language)}</time>
                </div>
                <div className="history-amount"><strong className={entry.balance_effect_paise > 0 ? 'red' : 'green'}>
                  {entry.balance_effect_paise > 0 && <span aria-hidden="true">+</span>}
                  <span>{money(entry.balance_effect_paise)}</span>
                </strong>
                  <p className="subtle tabular-nums">{t('customerList.after', { amount: money(entry.balance_after_paise) })}</p>
                </div>
              </li>
            ))}</ul>
          </section>))}
      {error ? <LoadError error={error} retry={loadNext} /> : nextCursor ? (
        <button className="button button-secondary history-more" type="button" disabled={loading}
          onClick={loadNext}>{t(loading ? 'common.loading' : 'customerList.loadMore')}</button>
      ) : Boolean(entries?.length) && <p className="subtle history-end" role="status">{t('customerList.historyEnd')}</p>}
      <div className="info-row current-total"><span>{t('customerList.current')}</span><strong>{money(currentBalance)}</strong></div>
    </ResponsiveDetail>
  )
}

export default function Customers({ language }: { language: Locale }) {
  const { t } = useTranslation()
  const { data, error, retry } = useLoad(api.customers)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [highestFirst, setHighestFirst] = useState(true)
  const [selected, setSelected] = useState<Customer>()
  const detailTrigger = useRef<HTMLButtonElement>(null)
  const withDues = data?.filter(({ balance_paise }) => balance_paise > 0) ?? []
  const total = withDues.reduce((sum, row) => sum + BigInt(row.balance_paise), 0n)
  const visible = data ? filterCustomers(data, search, filter).sort((a, b) =>
    (highestFirst ? b.balance_paise - a.balance_paise : a.balance_paise - b.balance_paise)
    || a.name.localeCompare(b.name, language) || a.id - b.id) : []

  return (
    <div className="customers-page split-view" data-detail={Boolean(selected)}>
      <div className="split-list">
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
                    <button className="customer-row" type="button" aria-current={selected?.id === customer.id || undefined}
                      onClick={(event) => {
                        detailTrigger.current = event.currentTarget
                        setSelected(customer)
                      }}>
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
      </div>
      {selected && <CustomerDetail key={selected.id} customer={selected} language={language} close={() => {
        setSelected(undefined)
        detailTrigger.current?.focus()
      }} />}
    </div>
  )
}
