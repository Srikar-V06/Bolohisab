import { useEffect, useRef, useState } from 'react'
import type { Locale } from '../localization/languages'
import { configureRecognition, recognitionConstructor, recognitionError } from './browserSpeech'

type Status = 'idle' | 'requesting' | 'recording' | 'processing'
type RecognitionError = ReturnType<typeof recognitionError>

export function useRecognition(onTranscript: (text: string, locale: Locale) => void) {
  const active = useRef<SpeechRecognition | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<RecognitionError>()
  const Recognition = recognitionConstructor()

  useEffect(() => () => {
    const recognition = active.current
    active.current = null
    recognition?.abort()
  }, [])

  function cancel() {
    const recognition = active.current
    active.current = null
    recognition?.abort()
    setStatus('idle')
    setError(undefined)
  }

  function start(locale: Locale) {
    if (!Recognition || active.current) return
    setError(undefined)
    setStatus('requesting')
    try {
      const recognition = configureRecognition(Recognition, locale)
      active.current = recognition
      let finished = false
      recognition.onstart = () => {
        if (active.current === recognition) setStatus('recording')
      }
      recognition.onaudioend = () => {
        if (active.current === recognition) setStatus('processing')
      }
      recognition.onresult = (event) => {
        const result = event.results[event.resultIndex]
        if (active.current !== recognition || finished || !result?.isFinal) return
        const text = result[0].transcript
        if (!text.trim()) return
        finished = true
        setStatus('processing')
        onTranscript(text, locale)
      }
      recognition.onerror = (event) => {
        if (active.current !== recognition || finished) return
        finished = true
        setError(recognitionError(event.error))
        active.current = null
        setStatus('idle')
      }
      recognition.onend = () => {
        if (active.current !== recognition) return
        active.current = null
        setStatus('idle')
        if (!finished) setError('voice.errors.noSpeech')
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

  return { supported: Boolean(Recognition), status, error, start, stop, cancel }
}
