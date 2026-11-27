import { afterEach, expect, it, vi } from 'vitest'
import { configureRecognition, createUtterance, recognitionConstructor, recognitionError } from './browserSpeech'

afterEach(() => vi.unstubAllGlobals())

it('recognizes standard and prefixed browser support and passes through both exact locales', () => {
  const Recognition = vi.fn(function () {})
  const WebkitRecognition = vi.fn(function () {})
  vi.stubGlobal('window', { SpeechRecognition: Recognition, webkitSpeechRecognition: WebkitRecognition })
  expect(recognitionConstructor()).toBe(Recognition)

  vi.stubGlobal('window', { webkitSpeechRecognition: WebkitRecognition })
  const constructor = recognitionConstructor()!
  expect(constructor).toBe(WebkitRecognition)
  for (const locale of ['hi-IN', 'en-IN'] as const) {
    expect(configureRecognition(constructor, locale)).toMatchObject({
      lang: locale, continuous: true, interimResults: true,
    })
  }

  vi.stubGlobal('window', {})
  expect(recognitionConstructor()).toBeUndefined()
  expect(recognitionError('language-not-supported')).toBe('voice.errors.language')
  expect(recognitionError('not-allowed')).toBe('voice.errors.permission')
})

it('plays the exact voice when present, otherwise uses only a same-language voice', () => {
  const voices = [{ lang: 'en-US' }, { lang: 'hi-IN' }, { lang: 'en-IN' }]
  const synthesis = { getVoices: () => voices }
  vi.stubGlobal('window', { speechSynthesis: synthesis })
  vi.stubGlobal('SpeechSynthesisUtterance', class {
    constructor(readonly text: string) {}
  })
  expect(createUtterance('₹750 का भुगतान।', 'hi-IN')?.utterance).toMatchObject({
    text: '₹750 का भुगतान।', lang: 'hi-IN', voice: voices[1],
  })
  expect(createUtterance('Payment of ₹750.', 'en-IN')?.utterance).toMatchObject({
    text: 'Payment of ₹750.', lang: 'en-IN', voice: voices[2],
  })

  voices.splice(1)
  expect(createUtterance('अनुपलब्ध', 'hi-IN')).toBeUndefined()
  expect(createUtterance('Payment of ₹750.', 'en-IN')?.utterance.lang).toBe('en-US')
  vi.stubGlobal('window', {})
  expect(createUtterance('Payment of ₹750.', 'en-IN')).toBeUndefined()
})
