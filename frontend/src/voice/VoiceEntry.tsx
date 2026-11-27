import { Mic, Square, Volume2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import LanguageSelect from '../localization/LanguageSelect'
import {
  englishLocale, languageNames, readLanguage, saveLanguage, speechLocales,
} from '../localization/languages'
import type { Locale } from '../localization/languages'
import { transactionText } from '../localization/transactionText'
import { translateTranscript } from '../localization/transcriptTranslation'
import { formatRupees, sampleVoice } from '../sampleData'
import { createUtterance } from './browserSpeech'
import { useRecognition } from './useRecognition'

function Transcript({ text, locale, english, lang = locale }: {
  text: string
  locale: Locale
  english?: string
  lang?: string
}) {
  const { t } = useTranslation()
  const translation = english ?? translateTranscript(text, locale)

  return (
    <div className="mt-4">
      <h3 className="text-sm font-extrabold">{t('voice.original')}</h3>
      <blockquote lang={lang} className="transcript mt-2">{text}</blockquote>
      {locale !== englishLocale && (
        <details className="mt-1">
          <summary className="detail-toggle">{t('voice.showEnglish')}</summary>
          {translation
            ? <p lang={englishLocale} className="transcript">{translation}</p>
            : <p className="text-sm text-muted">{t('voice.translationUnavailable')}</p>}
        </details>
      )}
    </div>
  )
}

function VoiceRecording() {
  const { t } = useTranslation()
  const [language, setLanguage] = useState(() => readLanguage('speech'))
  const { supported, status, error, transcript, start, stop } = useRecognition()
  const busy = status !== 'idle'

  return (
    <section className="panel p-5 sm:p-6" aria-labelledby="record-heading">
      <span className="stat-icon avatar-sage"><Mic size={20} aria-hidden="true" /></span>
      <h2 id="record-heading" className="section-heading mt-4">{t('voice.recordHeading')}</h2>
      <div className="mt-4">
        <LanguageSelect
          label={t('voice.speechLanguage')}
          locales={speechLocales}
          value={language}
          disabled={busy}
          onChange={(locale) => {
            setLanguage(locale)
            saveLanguage('speech', locale)
          }}
        />
      </div>
      {supported ? (
        <>
          <p className="mt-3 text-sm text-muted">{t('voice.browserService')}</p>
          <button
            type="button"
            className="button button-primary mt-4"
            disabled={status === 'finishing'}
            onClick={busy ? stop : () => start(language)}
          >
            {busy ? <Square size={17} aria-hidden="true" /> : <Mic size={17} aria-hidden="true" />}
            {t(busy ? 'voice.stop' : 'voice.start')}
          </button>
          <div role="status">
            {busy && <p className="mt-2 text-sm font-bold text-primary">{t(`voice.${status}`)}</p>}
            {error && <p className="mt-2 text-sm text-muted">{t(error)}</p>}
          </div>
        </>
      ) : (
        <p className="mt-3 text-sm text-muted">{t('voice.errors.unsupported')}</p>
      )}
      {transcript && <Transcript key={transcript.locale} {...transcript} />}
    </section>
  )
}

function ConfirmationPlayback() {
  const { t, i18n } = useTranslation()
  const current = useRef<SpeechSynthesisUtterance | null>(null)
  const [playing, setPlaying] = useState<Locale>()
  const [error, setError] = useState<'voiceUnavailable' | 'playback'>()

  useEffect(() => {
    window.speechSynthesis?.getVoices()
    return () => {
      if (!current.current) return
      current.current = null
      window.speechSynthesis.cancel()
    }
  }, [])

  function stop() {
    if (!current.current) return
    current.current = null
    window.speechSynthesis.cancel()
    setPlaying(undefined)
  }

  function play(locale: Locale) {
    stop()
    setError(undefined)
    try {
      const { confirmation } = transactionText(i18n.getFixedT(locale), sampleTransaction)
      const playback = createUtterance(confirmation, locale)
      if (!playback) {
        setError('voiceUnavailable')
        return
      }

      const { synthesis, utterance } = playback
      current.current = utterance
      setPlaying(locale)
      utterance.onend = () => {
        if (current.current !== utterance) return
        current.current = null
        setPlaying(undefined)
      }
      utterance.onerror = () => {
        if (current.current !== utterance) return
        current.current = null
        setPlaying(undefined)
        setError('playback')
      }
      synthesis.speak(utterance)
    } catch {
      current.current = null
      setPlaying(undefined)
      setError('playback')
    }
  }

  return (
    <>
      <fieldset className="mt-4">
        <legend className="text-sm font-extrabold">{t('voice.listen')}</legend>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {speechLocales.map((locale) => (
            <button
              type="button"
              className="button button-outline"
              key={locale}
              lang={locale}
              onClick={() => play(locale)}
            >
              <Volume2 size={17} aria-hidden="true" /> {languageNames[locale].speech}
            </button>
          ))}
          {playing && (
            <button type="button" className="button button-outline" onClick={stop}>
              <Square size={15} aria-hidden="true" /> {t('voice.stopPlayback')}
            </button>
          )}
        </div>
      </fieldset>
      <div role="status">{error && <p className="mt-2 text-sm text-muted">{t(`voice.errors.${error}`)}</p>}</div>
    </>
  )
}

const sampleTransaction = { ...sampleVoice, amount: formatRupees(sampleVoice.amount) }

function SampleEntry() {
  const [showPreview, setShowPreview] = useState(false)
  const { t } = useTranslation()
  const { confirmation, receipt } = transactionText(t, sampleTransaction)

  return (
    <section className="panel p-5 sm:p-6" aria-labelledby="sample-heading">
      <span className="stat-icon avatar-sage"><Mic size={20} aria-hidden="true" /></span>
      <h2 id="sample-heading" className="section-heading mt-4">{t('voice.samplePhrase')}</h2>
      <Transcript text={sampleVoice.transcript} locale="hi-IN" lang="hi-Latn-IN" english={sampleVoice.english} />
      <button
        type="button"
        className="button button-primary mt-4"
        aria-expanded={showPreview}
        aria-controls="entry-preview"
        onClick={() => setShowPreview((visible) => !visible)}
      >
        {t(showPreview ? 'voice.hidePreview' : 'voice.preview')}
      </button>
      <div id="entry-preview" hidden={!showPreview} className="mt-5 border-t border-line pt-4">
        {showPreview && (
          <>
            <h3 className="font-extrabold">{t('voice.samplePayment')}</h3>
            <dl className="mt-2 divide-y divide-line">
              <div className="summary-row"><dt>{t('transaction.customer')}</dt><dd>{sampleVoice.customerName}</dd></div>
              <div className="summary-row"><dt>{t('transaction.amountReceived')}</dt><dd>{sampleTransaction.amount}</dd></div>
            </dl>
            <p className="transcript mt-2">{confirmation}</p>
            <ConfirmationPlayback />
            <details className="mt-2">
              <summary className="detail-toggle">{t('voice.receiptPreview')}</summary>
              <p className="transcript">{receipt}</p>
            </details>
          </>
        )}
      </div>
    </section>
  )
}

export default function VoiceEntry() {
  const { t } = useTranslation()

  return (
    <>
      <div>
        <h1 tabIndex={-1} className="page-heading">{t('nav.voice-entry')}</h1>
        <p className="page-intro">{t('voice.intro')}</p>
      </div>
      <div className="grid max-w-[68rem] items-start gap-4 lg:grid-cols-2">
        <VoiceRecording />
        <SampleEntry />
      </div>
    </>
  )
}
