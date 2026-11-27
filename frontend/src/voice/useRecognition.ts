import { useEffect, useRef, useState } from 'react'
import type { Locale } from '../localization/languages'
import { configureRecognition, recognitionConstructor, recognitionError } from './browserSpeech'

type Status = 'idle' | 'requesting' | 'recording' | 'processing'
type RecognitionError = ReturnType<typeof recognitionError>

/** After speech has started, this much silence ends the capture. */
export const SILENCE_MS = 2500

export function useRecognition(onTranscript: (text: string, locale: Locale) => void) {
  const active = useRef<SpeechRecognition | null>(null)
  const silence = useRef<number>(undefined)
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<RecognitionError>()
  const [interim, setInterim] = useState('')
  const Recognition = recognitionConstructor()

  useEffect(() => () => {
    window.clearTimeout(silence.current)
    const recognition = active.current
    active.current = null
    recognition?.abort()
  }, [])

  function cancel() {
    window.clearTimeout(silence.current)
    const recognition = active.current
    active.current = null
    recognition?.abort()
    setStatus('idle')
    setError(undefined)
    setInterim('')
  }

  function start(locale: Locale) {
    if (!Recognition || active.current) return
    setError(undefined)
    setInterim('')
    setStatus('requesting')
    try {
      const recognition = configureRecognition(Recognition, locale)
      active.current = recognition
      let finished = false
      // Everything heard so far: finalized phrases plus the phrase still being recognized.
      let heard = ''
      recognition.onstart = () => {
        if (active.current === recognition) setStatus('recording')
      }
      recognition.onresult = (event) => {
        if (active.current !== recognition || finished) return
        // Kept exactly as recognized (Chrome prefixes later phrases with a space) for the review record.
        heard = Array.from(event.results, (item) => item[0]?.transcript ?? '').join('')
        setInterim(heard)
        // Pauses between words are normal; only sustained silence ends the capture.
        window.clearTimeout(silence.current)
        if (heard.trim()) silence.current = window.setTimeout(() => {
          if (active.current !== recognition) return
          setStatus('processing')
          recognition.stop()
        }, SILENCE_MS)
      }
      recognition.onerror = (event) => {
        if (active.current !== recognition || finished) return
        // A late no-speech error after we already heard words still submits what was heard.
        if (event.error === 'no-speech' && heard.trim()) return
        finished = true
        window.clearTimeout(silence.current)
        setError(recognitionError(event.error))
        active.current = null
        setStatus('idle')
      }
      recognition.onend = () => {
        if (active.current !== recognition) return
        window.clearTimeout(silence.current)
        active.current = null
        if (finished) return
        finished = true
        setStatus('idle')
        if (heard.trim()) onTranscript(heard, locale)
        else setError('voice.errors.noSpeech')
      }
      recognition.start()
    } catch (cause) {
      active.current = null
      setStatus('idle')
      const denied = cause instanceof DOMException && cause.name === 'NotAllowedError'
      setError(denied ? 'voice.errors.permission' : 'voice.errors.recognition')
    }
  }

  function stop() {
    const recognition = active.current
    if (!recognition || status !== 'recording') return
    setStatus('processing')
    try {
      recognition.stop()
    } catch {
      cancel()
      setError('voice.errors.recognition')
    }
  }

  return { supported: Boolean(Recognition), status, error, interim, start, stop, cancel }
}
