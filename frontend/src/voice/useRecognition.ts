import { useEffect, useRef, useState } from 'react'
import type { Locale } from '../localization/languages'
import { configureRecognition, recognitionConstructor, recognitionError } from './browserSpeech'

type Status = 'idle' | 'listening' | 'finishing'
type RecognitionError = ReturnType<typeof recognitionError>

export function useRecognition() {
  const active = useRef<SpeechRecognition | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<RecognitionError>()
  const [transcript, setTranscript] = useState<{ text: string; locale: Locale }>()
  const Recognition = recognitionConstructor()

  useEffect(() => () => {
    const recognition = active.current
    active.current = null
    recognition?.abort()
  }, [])

  function start(locale: Locale) {
    if (!Recognition || active.current) return

    setError(undefined)
    try {
      const recognition = configureRecognition(Recognition, locale)
      active.current = recognition
      recognition.onresult = (event) => {
        const result = event.results[event.resultIndex]
        if (active.current === recognition && result?.isFinal) {
          setTranscript({ text: result[0].transcript, locale })
        }
      }
      recognition.onerror = (event) => {
        if (active.current === recognition) setError(recognitionError(event.error))
      }
      recognition.onend = () => {
        if (active.current !== recognition) return
        active.current = null
        setStatus('idle')
      }
      recognition.start()
      setStatus('listening')
    } catch (cause) {
      active.current = null
      setStatus('idle')
      const denied = cause instanceof DOMException && cause.name === 'NotAllowedError'
      setError(denied ? 'voice.errors.permission' : 'voice.errors.recognition')
    }
  }

  function stop() {
    const recognition = active.current
    if (!recognition || status !== 'listening') return

    setStatus('finishing')
    try {
      recognition.stop()
    } catch {
      active.current = null
      setStatus('idle')
      setError('voice.errors.recognition')
    }
  }

  return { supported: Boolean(Recognition), status, error, transcript, start, stop }
}
