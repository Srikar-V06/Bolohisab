import { useEffect, useRef, useState } from 'react'
import { ArrowDownLeft, ArrowRight, ArrowUpRight, Check, LoaderCircle, Mic, Square, Volume2, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api, ApiError } from '../api'
import type { ParseResult, PreviewBalance } from '../api'
import { Loading, Sheet, useLoad } from '../components'
import Dashboard from '../Dashboard'
import { money } from '../format'
import LanguageSelect from '../localization/LanguageSelect'
import { languageNames, readLanguage, saveLanguage, speechLocales } from '../localization/languages'
import type { Locale } from '../localization/languages'
import { createUtterance } from './browserSpeech'
import { useRecognition } from './useRecognition'

type Transcript = { text: string; locale: Locale }
type Review =
  | { state: 'parsing' | 'parseFailed' | 'precision'; transcript: Transcript }
  | { state: 'preview' | 'saving' | 'saved' | 'stale' | 'saveFailed'; transcript: Transcript; result: ParseResult; batchId: string }

function BalanceCard({ balance, queryOnly, language }: { balance: PreviewBalance; queryOnly: boolean; language: Locale }) {
  const { t } = useTranslation()
  const [listenFailed, setListenFailed] = useState(false)
  function listen() {
    const playback = createUtterance(t('home.listenText', { name: balance.customer.name, amount: money(balance.updated_balance_paise) }), language)
    setListenFailed(!playback)
    if (!playback) return
    playback.synthesis.cancel()
    playback.synthesis.speak(playback.utterance)
  }
  return (
    <section className="preview-card card bubble-app">
      <header className="preview-head">
        <h3>{balance.customer.name}</h3>
        <button type="button" className="icon-button listen-button" onClick={listen}
          aria-label={t('home.listenLabel', { name: balance.customer.name })}>
          <Volume2 size={18} aria-hidden="true" />
        </button>
      </header>
      {queryOnly ? (
        <div className="balance-now">
          <span className="subtle">{t('speak.balanceQuery')}</span>
          <strong>{money(balance.updated_balance_paise)}</strong>
        </div>
      ) : <>
        <ul className="action-rows">
          {balance.credit_paise > 0 && <li><span><ArrowUpRight size={16} aria-hidden="true" className="red" />{t('speak.credit')}</span>
            <strong className="red">{money(balance.credit_paise)}</strong></li>}
          {balance.payment_paise > 0 && <li><span><ArrowDownLeft size={16} aria-hidden="true" className="green" />{t('speak.payment')}</span>
            <strong className="green">{money(balance.payment_paise)}</strong></li>}
        </ul>
        <div className="balance-flow">
          <span><span className="subtle">{t('speak.previous')}</span><strong>{money(balance.previous_balance_paise)}</strong></span>
          <ArrowRight size={18} aria-hidden="true" className="text-muted" />
          <span><span className="subtle">{t('speak.updated')}</span><strong>{money(balance.updated_balance_paise)}</strong></span>
        </div>
      </>}
      {listenFailed && <p className="subtle" role="status">{t('voice.errors.voiceUnavailable')}</p>}
    </section>
  )
}

export default function VoiceEntry({ language }: { language: Locale }) {
  const { t } = useTranslation()
  const [speechLanguage, setSpeechLanguage] = useState(() => readLanguage('speech'))
  const [settings, setSettings] = useState(false)
  const [review, setReview] = useState<Review>()
  const parsing = useRef<AbortController>(null)
  const saving = useRef(false)
  const capture = useRecognition((text, locale) => void parse({ text, locale }))
  const { data: customers, retry: reloadCustomers } = useLoad(api.customers)
  const { data: receipts, retry: reloadReceipts } = useLoad(api.receipts)

  useEffect(() => () => parsing.current?.abort(), [])

  async function parse(transcript: Transcript) {
    parsing.current?.abort()
    const controller = new AbortController()
    parsing.current = controller
    setReview({ state: 'parsing', transcript })
    try {
      const result = await api.parse(transcript.text, language, transcript.locale, controller.signal)
      if (!controller.signal.aborted) {
        setReview({ state: 'preview', transcript, result, batchId: crypto.randomUUID() })
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        setReview({ state: error instanceof ApiError && error.code === 'PRECISION' ? 'precision' : 'parseFailed', transcript })
      }
    }
  }

  function closeReview() {
    parsing.current?.abort()
    capture.cancel()
    if (review?.state === 'saved') {
      reloadCustomers()
      reloadReceipts()
    }
    setReview(undefined)
  }

  async function confirm() {
    if (!review || !('result' in review) || saving.current) return
    saving.current = true
    setReview({ ...review, state: 'saving' })
    try {
      await api.confirm(review.result, review.batchId)
      setReview({ ...review, state: 'saved' })
    } catch (error) {
      const stale = error instanceof ApiError && (error.code === 'STALE_REVIEW' || error.code === 'BATCH_CONFLICT')
      setReview({ ...review, state: stale ? 'stale' : 'saveFailed' })
    } finally {
      saving.current = false
    }
  }

  const status = capture.status
  const micLabel = status === 'recording' ? t('speak.stop') : status === 'idle' ? t('speak.button') : t('speak.cancelCapture')
  const micAction = status === 'recording' ? capture.stop : status === 'idle' ? () => capture.start(speechLanguage) : capture.cancel
  const result = review && 'result' in review ? review.result : undefined
  const queryOnly = result?.actions.every(({ intent }) => intent === 'BALANCE_QUERY') ?? false

  return (
    <div className="speak-page">
      {Array.isArray(customers) && customers.length > 0
        ? <Dashboard customers={customers} receipts={Array.isArray(receipts) ? receipts : undefined} language={language}>
      <section className="bolo-card card" data-state={status} aria-labelledby="bolo-title">
        <div className="mic-stage" data-state={status}>
          <span className="mic-ring" aria-hidden="true" />
          <span className="mic-ring mic-ring-late" aria-hidden="true" />
          <button type="button" className="mic-control" aria-label={micLabel} onClick={micAction} disabled={!capture.supported}
            data-recording={status === 'recording'}>
            {status === 'recording' ? <Square size={30} fill="currentColor" aria-hidden="true" />
              : status === 'requesting' || status === 'processing' ? <LoaderCircle size={40} className="spinner" aria-hidden="true" />
                : <Mic size={44} strokeWidth={2} aria-hidden="true" />}
          </button>
        </div>
        <h1 id="bolo-title">{t('speak.instruction')}</h1>
        {status === 'idle' ? <p className="speak-support">{t('speak.support')}</p>
          : <p className="speak-status" role="status">
            {status === 'recording' && <span className="listen-bars" aria-hidden="true"><span /><span /><span /><span /><span /></span>}
            {t(status === 'requesting' ? 'speak.permission' : status === 'recording' ? 'speak.recording' : 'speak.finishing')}
          </p>}
        {status === 'idle' ? (
          <p className="example-line"><span>{t('speak.exampleLabel')}</span> “{t('speak.example')}”</p>
        ) : (
          <p className="live-transcript" lang={speechLanguage} aria-live="polite" data-empty={!capture.interim}>
            {capture.interim}
          </p>
        )}
        <button type="button" className="speech-setting" onClick={() => setSettings(true)} disabled={status !== 'idle'}>
          {t('speak.speechSetting', { language: languageNames[speechLanguage].speech })}
        </button>
      </section>
        </Dashboard>
        : <>
          <p className="speak-greeting">{t('speak.greeting')}</p>
      <section className="bolo-card card" data-state={status} aria-labelledby="bolo-title">
        <div className="mic-stage" data-state={status}>
          <span className="mic-ring" aria-hidden="true" />
          <span className="mic-ring mic-ring-late" aria-hidden="true" />
          <button type="button" className="mic-control" aria-label={micLabel} onClick={micAction} disabled={!capture.supported}
            data-recording={status === 'recording'}>
            {status === 'recording' ? <Square size={30} fill="currentColor" aria-hidden="true" />
              : status === 'requesting' || status === 'processing' ? <LoaderCircle size={40} className="spinner" aria-hidden="true" />
                : <Mic size={44} strokeWidth={2} aria-hidden="true" />}
          </button>
        </div>
        <h1 id="bolo-title">{t('speak.instruction')}</h1>
        {status === 'idle' ? <p className="speak-support">{t('speak.support')}</p>
          : <p className="speak-status" role="status">
            {status === 'recording' && <span className="listen-bars" aria-hidden="true"><span /><span /><span /><span /><span /></span>}
            {t(status === 'requesting' ? 'speak.permission' : status === 'recording' ? 'speak.recording' : 'speak.finishing')}
          </p>}
        {status === 'idle' ? (
          <p className="example-line"><span>{t('speak.exampleLabel')}</span> “{t('speak.example')}”</p>
        ) : (
          <p className="live-transcript" lang={speechLanguage} aria-live="polite" data-empty={!capture.interim}>
            {capture.interim}
          </p>
        )}
        <button type="button" className="speech-setting" onClick={() => setSettings(true)} disabled={status !== 'idle'}>
          {t('speak.speechSetting', { language: languageNames[speechLanguage].speech })}
        </button>
      </section>
        </>}
      {!capture.supported && <p className="notice" role="status">{t('speak.unsupported')}</p>}
      {capture.error && <p className="notice notice-error" role="alert">{t(capture.error)}</p>}
      {settings && <Sheet title={t('voice.speechLanguage')} close={() => setSettings(false)}>
        <LanguageSelect label={t('voice.speechLanguage')} locales={speechLocales} value={speechLanguage}
          onChange={(locale) => {
            setSpeechLanguage(locale)
            saveLanguage('speech', locale)
            setSettings(false)
          }} />
        <p className="notice">{t('speak.speechPrivacy')}</p>
      </Sheet>}
      {review && <Sheet title={t(review.state === 'saved' ? 'speak.saved' : 'speak.review')}
        close={closeReview} locked={review.state === 'saving'}>
        {review.state === 'saved' ? (
          <div className="saved-state">
            <span className="saved-mark"><Check size={36} strokeWidth={2.5} aria-hidden="true" /></span>
            <p role="status">{t('speak.savedDetail')}</p>
            <button className="button button-primary" type="button" onClick={closeReview}>{t('common.done')}</button>
          </div>
        ) : (
          <>
            <div className="chat-thread">
              <figure className="bubble-user">
                <figcaption className="label">{t('speak.original')}</figcaption>
                <blockquote lang={result?.detected_language ?? review.transcript.locale}>{review.transcript.text}</blockquote>
                {result && <p className="subtle">{t('speak.detected')}: {t(
                  result.detected_language ? `detected.${result.detected_language}` : 'speak.unknown',
                )}</p>}
              </figure>
            </div>
            {review.state === 'parsing' && <>
              <p className="subtle">{t('speak.received')}</p>
              <Loading text={t('speak.parsing')} rows={2} />
            </>}
            {(review.state === 'parseFailed' || review.state === 'precision') && (
              <p className="notice notice-error" role="alert">{t(review.state === 'precision' ? 'common.precision' : 'speak.parseFailed')}</p>
            )}
            {result?.clarification && (
              <div className="notice notice-error bubble-app" role="alert">
                <p><strong>{t('clarify.heading')}</strong></p>
                <p>{t(`clarify.${result.clarification.code}`)}</p>
                {result.clarification.candidates.length > 0 && (
                  <ul className="candidate-pills">{result.clarification.candidates.map((customer) => <li key={customer.id}>{customer.name}</li>)}</ul>
                )}
              </div>
            )}
            {result?.balances.map((balance) => <BalanceCard key={balance.customer.id} balance={balance}
              queryOnly={!result.actions.some((action) => action.customer.id === balance.customer.id && action.intent !== 'BALANCE_QUERY')}
              language={language} />)}
            {result?.english_interpretation && (
              <details className="interpretation card">
                <summary>{t('speak.interpretation')}</summary>
                <p lang="en-IN">{result.english_interpretation}</p>
              </details>
            )}
            {review.state === 'stale' && <p className="notice notice-error" role="alert">{t('speak.stale')}</p>}
            {review.state === 'saveFailed' && <p className="notice notice-error" role="alert">{t('speak.saveFailed')}</p>}
            {result?.status === 'REVIEW_REQUIRED' && !queryOnly && review.state === 'preview' &&
              <p className="status-chip amber">{t('speak.awaiting')}</p>}
            <div className="sheet-actions">
              <button className="button button-secondary" type="button" onClick={closeReview} disabled={review.state === 'saving'}>
                <X size={17} aria-hidden="true" />{t(queryOnly && !result?.clarification ? 'common.done' : 'common.cancel')}
              </button>
              {review.state === 'stale' || review.state === 'parseFailed' ? (
                <button className="button button-primary" type="button" onClick={() => void parse(review.transcript)}>{t('speak.reviewAgain')}</button>
              ) : result?.clarification && capture.supported ? (
                <button className="button button-primary" type="button"
                  onClick={() => { closeReview(); capture.start(speechLanguage) }}>{t('clarify.recordAgain')}</button>
              ) : result?.status === 'REVIEW_REQUIRED' && !queryOnly && (
                <button className="button button-primary" type="button" disabled={review.state === 'saving'} onClick={() => void confirm()}>
                  {review.state === 'saving' ? <LoaderCircle size={17} className="spinner" aria-hidden="true" /> : <Check size={17} aria-hidden="true" />}
                  {t(review.state === 'saving' ? 'speak.saving' : 'common.confirm')}
                </button>
              )}
            </div>
          </>
        )}
      </Sheet>}
    </div>
  )
}
