import { useEffect, useRef, useState } from 'react'
import { ArrowDownLeft, ArrowUpRight, Check, Clock3, Link2, SlidersHorizontal, ReceiptText, Volume2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from './api'
import type { Receipt } from './api'
import { LoadError, Loading, useLoad } from './components'
import ResponsiveDetail from './ResponsiveDetail'
import { money, transactionDate, transactionDays, transactionLabel } from './format'
import LanguageSelect from './localization/LanguageSelect'
import { interfaceLocales, readLanguage, saveLanguage } from './localization/languages'
import type { Locale } from './localization/languages'
import { createUtterance } from './voice/browserSpeech'

function ReceiptPreview({ item, close, update }: { item: Receipt; close: () => void; update: (item: Receipt) => void }) {
  const { t, i18n } = useTranslation()
  const [language, setLanguage] = useState(() => readLanguage('receipt'))
  const [pending, setPending] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [showLink, setShowLink] = useState(false)
  const [message, setMessage] = useState<
    'receiptList.copied' | 'receiptList.manualCopy' | 'receiptList.shared' | 'receiptList.actionFailed'
    | 'receiptList.ready' | 'receiptList.shareFailed' | 'voice.errors.voiceUnavailable' | 'voice.errors.playback'
  >()
  const utterance = useRef<SpeechSynthesisUtterance | null>(null)
  const label = i18n.getFixedT(language)
  const details = [
    [label('receiptList.shop'), item.shop_name],
    [label('receiptList.customer'), item.customer_name],
    [label('receiptList.id'), String(item.entry_id)],
    [label('receiptList.when'), transactionDate(item.created_at, language)],
    [label('receiptList.details'), transactionLabel(label, item.type, item.payment_method)],
    [label('receiptList.amount'), money(item.amount_paise)],
    [label('receiptList.balance'), money(item.balance_after_paise)],
  ]
  const link = item.share_token
    ? new URL(`/api/receipts/share/${encodeURIComponent(item.share_token)}?language=${language}`, window.location.origin).href
    : undefined

  useEffect(() => {
    window.speechSynthesis?.getVoices()
    return () => {
      if (!utterance.current) return
      utterance.current = null
      window.speechSynthesis?.cancel()
    }
  }, [])

  function stopReading() {
    if (!utterance.current) return
    utterance.current = null
    window.speechSynthesis.cancel()
    setPlaying(false)
  }

  function listen() {
    setMessage(undefined)
    try {
      const text = details.map(([key, value]) => key + ', ' + value).join('. ')
      const playback = createUtterance(text, language)
      if (!playback) {
        setMessage('voice.errors.voiceUnavailable')
        return
      }
      const current = playback.utterance
      utterance.current = current
      setPlaying(true)
      const end = () => {
        if (utterance.current !== current) return
        utterance.current = null
        setPlaying(false)
      }
      current.onend = end
      current.onerror = () => {
        if (utterance.current === current) setMessage('voice.errors.playback')
        end()
      }
      playback.synthesis.speak(current)
    } catch {
      utterance.current = null
      setPlaying(false)
      setMessage('voice.errors.playback')
    }
  }

  async function changeReceipt(save: () => Promise<Receipt>, sent = false) {
    setPending(true)
    setMessage(undefined)
    try {
      update(await save())
      setMessage(sent ? 'receiptList.shared' : 'receiptList.ready')
    } catch {
      setMessage('receiptList.actionFailed')
    } finally {
      setPending(false)
    }
  }

  async function share() {
    if (!link) return
    setMessage(undefined)
    setPending(true)
    try {
      if (typeof navigator.share === 'function') {
        await navigator.share({ title: label('receiptList.preview'), url: link })
        if (!item.sent_at) await changeReceipt(() => api.markSent(item.entry_id), true)
      } else {
        setShowLink(true)
        if (navigator.clipboard) {
          await navigator.clipboard.writeText(link)
          setMessage('receiptList.copied')
        } else {
          setMessage('receiptList.manualCopy')
        }
      }
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        setShowLink(true)
        setMessage('receiptList.shareFailed')
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <ResponsiveDetail title={t('receiptList.preview')} close={close} locked={pending}>
      <LanguageSelect label={t('receiptList.language')} locales={interfaceLocales} value={language} disabled={pending}
        onChange={(locale) => {
          stopReading()
          setLanguage(locale)
          saveLanguage('receipt', locale)
        }} />
      <article className="receipt-paper" lang={language}>
        <header>
          <h3>{item.shop_name}</h3>
          <p>{label('receiptList.id')} #{item.entry_id}</p>
          <time dateTime={item.created_at}>{transactionDate(item.created_at, language)}</time>
        </header>
        <dl>
          <div className="info-row"><dt>{label('receiptList.customer')}</dt><dd>{item.customer_name}</dd></div>
          <div className="info-row"><dt>{label('receiptList.details')}</dt><dd>{transactionLabel(label, item.type, item.payment_method)}</dd></div>
          <div className="info-row receipt-face-amount"><dt>{label('receiptList.amount')}</dt><dd>{money(item.amount_paise)}</dd></div>
          <div className="info-row receipt-balance"><dt>{label('receiptList.balance')}</dt><dd>{money(item.balance_after_paise)}</dd></div>
        </dl>
      </article>
      <div className="sheet-actions receipt-actions">
        {!link && <button className="button button-primary" type="button" disabled={pending}
          onClick={() => void changeReceipt(() => api.generate(item.entry_id, language))}>
          <ReceiptText size={17} aria-hidden="true" /> {t(pending ? 'receiptList.generating' : 'receiptList.generate')}
        </button>}
        <button className="button button-secondary" type="button" disabled={pending} onClick={playing ? stopReading : listen}>
          <Volume2 size={17} aria-hidden="true" /> {t(playing ? 'receiptList.stop' : 'receiptList.listen')}
        </button>
        {link && <button className="button button-primary" type="button" disabled={pending} onClick={() => void share()}>
          <Link2 size={17} aria-hidden="true" /> {t('receiptList.share')}
        </button>}
      </div>
      {showLink && link && (
        <div className="receipt-share">
          <label>
            <span className="sr-only">{t('receiptList.share')}</span>
            <input readOnly value={link} onFocus={(event) => event.currentTarget.select()} />
          </label>
          {!item.sent_at && <button className="button button-secondary" type="button" disabled={pending}
            onClick={() => void changeReceipt(() => api.markSent(item.entry_id), true)}>{t('receiptList.markSent')}</button>}
        </div>
      )}
      {message && <p className="notice" role="status">{t(message)}</p>}
    </ResponsiveDetail>
  )
}

export default function Receipts({ language }: { language: Locale }) {
  const { t } = useTranslation()
  const { data, error, retry, setData } = useLoad(api.receipts)
  const [tab, setTab] = useState<'awaiting' | 'sent'>('awaiting')
  const [selectedId, setSelectedId] = useState<number>()
  const detailTrigger = useRef<HTMLButtonElement>(null)
  const awaiting = data?.filter((item) => !item.sent_at).length ?? 0
  const selected = data?.find((item) => item.entry_id === selectedId)
  const items = data?.filter((item) => Boolean(item.sent_at) === (tab === 'sent')) ?? []

  return (
    <div className="receipts-page split-view" data-detail={Boolean(selected)}>
      <div className="split-list">
      <div className="receipt-tabs" role="group" aria-label={t('receiptList.tabs')}>
        <button type="button" aria-pressed={tab === 'awaiting'} onClick={() => setTab('awaiting')}>
          {t('receiptList.awaiting')} {awaiting > 0 && <span className="count-dot">{awaiting}</span>}
        </button>
        <button type="button" aria-pressed={tab === 'sent'} onClick={() => setTab('sent')}>{t('receiptList.sent')}</button>
      </div>
      {error ? <LoadError error={error} retry={retry} /> : !data ? <Loading text={t('common.loading')} />
        : items.length === 0 ? <p className="notice">{t(tab === 'awaiting' ? 'receiptList.emptyAwaiting' : 'receiptList.emptySent')}</p>
          : transactionDays(items, language).map(day => (
          <section className="receipt-day" key={day.key}>
            <h2>{day.label}</h2>
            <ul>{day.entries.map((item) => {
              const Icon = item.type === 'CREDIT' ? ArrowUpRight : item.type === 'PAYMENT' ? ArrowDownLeft : SlidersHorizontal
              return (
              <li key={item.entry_id}>
                <button className="receipt-row" type="button" aria-current={selectedId === item.entry_id || undefined}
                  onClick={(event) => {
                    detailTrigger.current = event.currentTarget
                    setSelectedId(item.entry_id)
                  }}>
                  <span className="receipt-kind"><Icon size={19} aria-hidden="true" /></span>
                  <span className="list-copy">
                    <strong>{item.customer_name}</strong>
                    <span className="subtle">{transactionLabel(t, item.type, item.payment_method)} ·{' '}
                      <time dateTime={item.created_at}>{transactionDate(item.created_at, language)}</time></span>
                  </span>
                  <span className="list-amount">
                    <strong className={item.type === 'CREDIT' ? 'red' : item.type === 'PAYMENT' ? 'green' : undefined}>
                      {money(item.amount_paise)}
                    </strong>
                    <span className={item.sent_at ? 'status-chip settled' : 'status-chip amber'}>
                      {item.sent_at ? <Check size={12} aria-hidden="true" /> : <Clock3 size={12} aria-hidden="true" />}
                      {t(item.sent_at ? 'receiptList.sent' : item.share_token ? 'receiptList.ready' : 'receiptList.pending')}
                    </span>
                  </span>
                </button>
              </li>
              )
            })}</ul>
          </section>))}
      </div>
      {selected && <ReceiptPreview key={selected.entry_id} item={selected} close={() => {
        setSelectedId(undefined)
        detailTrigger.current?.focus()
      }}
        update={(item) => setData((rows) => rows?.map((row) => row.entry_id === item.entry_id ? item : row))} />}
    </div>
  )
}
