import type { Locale } from '../localization/languages'

type SpeechWindow = Window & {
  SpeechRecognition?: typeof SpeechRecognition
  webkitSpeechRecognition?: typeof SpeechRecognition
}

export function recognitionConstructor() {
  const browser = window as SpeechWindow
  return browser.SpeechRecognition ?? browser.webkitSpeechRecognition
}

export function configureRecognition(Recognition: typeof SpeechRecognition, locale: Locale) {
  const recognition = new Recognition()
  recognition.lang = locale
  recognition.continuous = false
  recognition.interimResults = false
  return recognition
}

export function recognitionError(code: string) {
  switch (code) {
    case 'not-allowed':
    case 'service-not-allowed':
      return 'voice.errors.permission' as const
    case 'audio-capture':
      return 'voice.errors.microphone' as const
    case 'no-speech':
      return 'voice.errors.noSpeech' as const
    case 'network':
      return 'voice.errors.network' as const
    case 'language-not-supported':
      return 'voice.errors.language' as const
    default:
      return 'voice.errors.recognition' as const
  }
}

export function selectSpeechVoice(voices: readonly SpeechSynthesisVoice[], locale: Locale) {
  const requested = locale.toLowerCase()
  const language = requested.split('-')[0]
  return voices.find((voice) => voice.lang.toLowerCase() === requested)
    ?? voices.find((voice) => voice.lang.toLowerCase().split('-')[0] === language)
}

export function createUtterance(text: string, locale: Locale) {
  const synthesis = window.speechSynthesis
  if (!synthesis || typeof SpeechSynthesisUtterance !== 'function') return undefined

  const voice = selectSpeechVoice(synthesis.getVoices(), locale)
  if (!voice) return undefined

  const utterance = new SpeechSynthesisUtterance(text)
  utterance.voice = voice
  utterance.lang = voice.lang
  return { synthesis, utterance }
}
