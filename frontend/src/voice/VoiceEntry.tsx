import { useEffect, useRef, useState } from 'react'
import { Check, LoaderCircle, Mic, Square, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api, ApiError } from '../api'
import type { ParseResult, PreviewBalance } from '../api'
import { Loading, Sheet } from '../components'
import { money } from '../format'
import LanguageSelect from '../localization/LanguageSelect'
import { languageNames, readLanguage, saveLanguage, speechLocales } from '../localization/languages'
import type { Locale } from '../localization/languages'
import { useRecognition } from './useRecognition'

type Transcript = { text: string; locale: Locale }
type Review =
  | { state: 'parsing' | 'parseFailed' | 'precision'; transcript: Transcript }
  | { state: 'preview' | 'saving' | 'saved' | 'stale' | 'saveFailed'; transcript: Transcript; result: ParseResult; batchId: string }

function BalanceCard({ balance, queryOnly }: { balance: PreviewBalance; queryOnly: boolean }) {
  const { t } = useTranslation()
  return (
    <section className="preview-card card">
      <h3>{balance.customer.name}</h3>
      <dl>
        {!queryOnly && <>
          <div className="info-row"><dt>{t('speak.credit')}</dt><dd className="red">{money(balance.credit_paise)}</dd></div>
          <div className="info-row"><dt>{t('speak.payment')}</dt><dd className="green">{money(balance.payment_paise)}</dd></div>
          <div className="info-row"><dt>{t('speak.previous')}</dt><dd>{money(balance.previous_balance_paise)}</dd></div>
        </>}
        <div className="info-row current-total">
          <dt>{t(queryOnly ? 'speak.balanceQuery' : 'speak.updated')}</dt>
          <dd>{money(balance.updated_balance_paise)}</dd>
        </div>
      </dl>
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
      <p className="speak-greeting">{t('speak.greeting')}</p>
      <button type="button" className="mic-control" aria-label={micLabel} onClick={micAction} disabled={!capture.supported}
        data-recording={status === 'recording'}>
        {status === 'recording' ? <Square size={38} aria-hidden="true" />
          : status === 'requesting' || status === 'processing' ? <LoaderCircle size={44} className="spinner" aria-hidden="true" />
            : <Mic size={53} strokeWidth={2} aria-hidden="true" />}
      </button>
      <h1>{t('speak.instruction')}</h1>
      {status === 'idle' ? <p className="speak-support">{t('speak.support')}</p>
        : <p className="speak-support green" role="status">
          {t(status === 'requesting' ? 'speak.permission' : status === 'recording' ? 'speak.recording' : 'speak.finishing')}
        </p>}
      <div className="example-card card">
        <p>{t('speak.exampleLabel')}</p>
        <blockquote>“{t('speak.example')}”</blockquote>
      </div>
      {!capture.supported && <p className="notice" role="status">{t('speak.unsupported')}</p>}
      {capture.error && <p className="notice notice-error" role="alert">{t(capture.error)}</p>}
      <button type="button" className="speech-setting" onClick={() => setSettings(true)} disabled={status !== 'idle'}>
        {t('speak.speechSetting', { language: languageNames[speechLanguage].speech })}
      </button>
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
            <Check size={34} aria-hidden="true" />
            <p role="status">{t('speak.savedDetail')}</p>
            <button className="button button-primary" type="button" onClick={closeReview}>{t('common.done')}</button>
          </div>
        ) : (
          <>
            <div className="transcript-card card">
              <p className="label">{t('speak.original')}</p>
              <blockquote lang={result?.detected_language ?? review.transcript.locale}>{review.transcript.text}</blockquote>
              {result && <p className="subtle">{t('speak.detected')} · {t(
                result.detected_language ? `detected.${result.detected_language}` : 'speak.unknown',
              )}</p>}
            </div>
            {review.state === 'parsing' && <>
              <p className="subtle">{t('speak.received')}</p>
              <Loading text={t('speak.parsing')} rows={2} />
            </>}
            {(review.state === 'parseFailed' || review.state === 'precision') && (
              <p className="notice notice-error" role="alert">{t(review.state === 'precision' ? 'common.precision' : 'speak.parseFailed')}</p>
            )}
            {result?.clarification && (
              <div className="notice notice-error" role="alert">
                <p><strong>{t('clarify.heading')}</strong></p>
                <p>{t(`clarify.${result.clarification.code}`)}</p>
                {result.clarification.candidates.length > 0 && (
                  <ul>{result.clarification.candidates.map((customer) => <li key={customer.id}>{customer.name}</li>)}</ul>
                )}
              </div>
            )}
            {result?.english_interpretation && (
              <details className="interpretation card">
                <summary>{t('speak.interpretation')}</summary>
                <p lang="en-IN">{result.english_interpretation}</p>
              </details>
            )}
            {result?.balances.map((balance) => <BalanceCard key={balance.customer.id} balance={balance}
              queryOnly={!result.actions.some((action) => action.customer.id === balance.customer.id && action.intent !== 'BALANCE_QUERY')} />)}
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
