import { ChevronDown, ReceiptText } from 'lucide-react'
import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import type { Account } from '../api'
import { LoadError, Loading, useLoad } from '../components'
import { money, receiptDate, transactionLabel } from '../format'
import { useLedgerHistory } from '../useLedgerHistory'
import { AuthLanguage, useInterfaceLanguage } from './AuthFrame'

function CustomerHistory({ id }: { id: number }) {
  const { t } = useTranslation()
  const language = useInterfaceLanguage()
  const { entries, loading, error, nextCursor, loadNext } = useLedgerHistory(id)
  return <div className="customer-account-detail">
    <h3>{t('customerList.history')}</h3>
    {!entries && loading && <Loading rows={2} text={t('common.loading')} />}
    {!loading && !!error && <LoadError error={error} retry={loadNext} />}
    {entries?.length === 0 && <p>{t('auth.noEntries')}</p>}
    {entries && entries.length > 0 && <ul className="customer-account-entries">
      {entries.map(entry => <li key={entry.id}>
        <div>
          <strong>{transactionLabel(t, entry.type, entry.payment_method)}</strong>
          <time dateTime={entry.created_at}>{receiptDate(entry.created_at, language)}</time>
        </div>
        <div className="customer-account-amount">
          <strong className={entry.balance_effect_paise < 0 ? 'green' : 'red'}>
            {entry.balance_effect_paise > 0 ? '+' : ''}{money(entry.balance_effect_paise)}
          </strong>
          <span>{t('auth.receiptBalance')} {money(entry.balance_after_paise)}</span>
        </div>
      </li>)}
    </ul>}
    {entries && nextCursor && !error && <button type="button" className="button button-secondary"
      onClick={loadNext} disabled={loading}>{t(loading ? 'common.loading' : 'customerList.loadMore')}</button>}
  </div>
}

export default function CustomerAccount({ account, actions }: { account: Account; actions: ReactNode }) {
  const { t } = useTranslation()
  const language = useInterfaceLanguage()
  const ledgers = useLoad(api.customers)
  const receipts = useLoad(api.receipts)
  const [selected, setSelected] = useState<number>()
  useEffect(() => {
    document.documentElement.lang = language
    document.title = t('auth.myAccount') + ' · ' + t('screens.brand')
  }, [language, t])

  return <main className="customer-account">
    <header className="customer-account-header">
      <div><h1>{t('auth.myAccount')}</h1><p>{account.full_name}</p></div>
      <div className="account-controls"><AuthLanguage />{actions}</div>
    </header>
    <div className="customer-account-grid">
      <section aria-labelledby="linked-ledgers" className="customer-account-card">
        <h2 id="linked-ledgers">{t('auth.linkedLedgers')}</h2>
        {ledgers.error ? <LoadError error={ledgers.error} retry={ledgers.retry} />
          : !ledgers.data ? <Loading rows={2} text={t('common.loading')} />
            : ledgers.data.length === 0 ? <p>{t('auth.noLinks')}</p>
              : <ul className="customer-account-list">{ledgers.data.map(customer => {
                  const expanded = customer.id === selected
                  return <li key={customer.id}>
                    <button className="customer-account-ledger" type="button" aria-expanded={expanded}
                      onClick={() => setSelected(expanded ? undefined : customer.id)}>
                      <span><strong>{customer.name}</strong>
                        <span>{t('auth.storeNumber', { id: customer.shop_id })}</span></span>
                      <span><strong>{money(customer.balance_paise)}</strong><ChevronDown size={16} aria-hidden="true" /></span>
                    </button>
                    {expanded && <CustomerHistory key={customer.id} id={customer.id} />}
                  </li>
                })}</ul>}
      </section>
      <section aria-labelledby="my-receipts" className="customer-account-card">
        <h2 id="my-receipts"><ReceiptText size={20} aria-hidden="true" /> {t('auth.myReceipts')}</h2>
        {receipts.error ? <LoadError error={receipts.error} retry={receipts.retry} />
          : !receipts.data ? <Loading rows={2} text={t('common.loading')} />
            : receipts.data.length === 0 ? <p>{t('auth.noReceipts')}</p>
              : <ul className="customer-account-list">{receipts.data.map(receipt => <li key={receipt.entry_id}>
                  <details>
                    <summary className="customer-account-receipt">
                      <span><strong>{receipt.shop_name}</strong>
                        <time dateTime={receipt.created_at}>{receiptDate(receipt.created_at, language)}</time></span>
                      <span><strong>{money(receipt.amount_paise)}</strong><ChevronDown size={16} aria-hidden="true" /></span>
                    </summary>
                    <dl className="customer-account-detail">
                      <div className="info-row"><dt>{t('receiptList.id')}</dt><dd>#{receipt.entry_id}</dd></div>
                      <div className="info-row"><dt>{t('receiptList.details')}</dt>
                        <dd>{transactionLabel(t, receipt.type, receipt.payment_method)}</dd></div>
                      <div className="info-row"><dt>{t('receiptList.balance')}</dt><dd>{money(receipt.balance_after_paise)}</dd></div>
                    </dl>
                  </details>
                </li>)}</ul>}
      </section>
    </div>
  </main>
}
