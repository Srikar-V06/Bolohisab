import { useCallback, useState } from 'react'
import { ChevronRight, Search } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from './api'
import type { Customer } from './api'
import { initials, money, transactionDate, transactionLabel } from './format'
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

function CustomerDetail({ customer, language, close }: { customer: Customer; language: Locale; close: () => void }) {
  const { t } = useTranslation()
  const load = useCallback((signal: AbortSignal) => api.ledger(customer.id, signal), [customer.id])
  const { data, error, retry } = useLoad(load)

  return (
    <Sheet title={customer.name} close={close}>
      <div className="summary-card card">
        <p className="subtle">{t('customerList.total')}</p>
        <p className="summary-value">{money(Math.max(0, customer.balance_paise))}</p>
      </div>
      <h3 className="sheet-section">{t('customerList.history')}</h3>
      {error ? <LoadError error={error} retry={retry} /> : !data ? <Loading text={t('common.loading')} />
        : data.length === 0 ? <p className="notice">{t('customerList.lastEmpty')}</p>
          : <ul className="history-list">
            {data.slice().reverse().map((entry) => (
              <li key={entry.id}>
                <div>
                  <p>{transactionLabel(t, entry.type, entry.payment_method)}</p>
                  <time className="subtle" dateTime={entry.created_at}>{transactionDate(entry.created_at, language)}</time>
                </div>
                <strong className={entry.type === 'CREDIT' ? 'red' : entry.type === 'PAYMENT' ? 'green' : undefined}>
                  {money(entry.amount_paise)}
                </strong>
              </li>
            ))}
          </ul>}
      <div className="info-row current-total"><span>{t('customerList.current')}</span><strong>{money(customer.balance_paise)}</strong></div>
    </Sheet>
  )
}

export default function Customers({ language }: { language: Locale }) {
  const { t } = useTranslation()
  const { data, error, retry } = useLoad(api.customers)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [selected, setSelected] = useState<Customer>()
  const withDues = data?.filter(({ balance_paise }) => balance_paise > 0) ?? []
  const total = withDues.reduce((sum, row) => sum + BigInt(row.balance_paise), 0n)
  const visible = data ? filterCustomers(data, search, filter) : []

  return (
    <div className="customers-page">
      <label className="search-input card">
        <Search size={19} aria-hidden="true" />
        <span className="sr-only">{t('customerList.search')}</span>
        <input type="search" placeholder={t('customerList.search')} value={search}
          onChange={(event) => setSearch(event.target.value)} />
      </label>
      {error ? <LoadError error={error} retry={retry} /> : !data ? <Loading text={t('common.loading')} /> : (
        <>
          <section className="summary-card card" aria-label={t('customerList.total')}>
            <div className="summary-heading">
              <p className="subtle">{t('customerList.total')}</p>
              <span className="status-chip amber">{t('customerList.count', { count: withDues.length })}</span>
            </div>
            <p className="summary-value">{money(total)}</p>
          </section>
          <div className="filter-chips" role="group" aria-label={t('customerList.filters')}>
            {filters.map((option) => (
              <button key={option} type="button" aria-pressed={filter === option} onClick={() => setFilter(option)}>
                {t(`customerList.${option}`)}
              </button>
            ))}
          </div>
          {visible.length === 0 ? <p className="notice">{t(data.length ? 'customerList.noResults' : 'customerList.empty')}</p>
            : <ul className="stack-list">
              {visible.map((customer) => {
                const outstanding = customer.balance_paise > 0
                return (
                  <li key={customer.id}>
                    <button className="customer-row card" type="button" onClick={() => setSelected(customer)}>
                      <span className={outstanding ? 'avatar' : 'avatar avatar-settled'} aria-hidden="true">{initials(customer.name, language)}</span>
                      <span className="list-copy">
                        <strong>{customer.name}</strong>
                        {customer.last_transaction_at
                          ? <time className="subtle" dateTime={customer.last_transaction_at}>{transactionDate(customer.last_transaction_at, language)}</time>
                          : <span className="subtle">{t('customerList.lastEmpty')}</span>}
                      </span>
                      <span className={outstanding ? 'list-amount red' : 'list-amount green'}>
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
