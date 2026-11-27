import { afterEach, describe, expect, it, vi } from 'vitest'
import english from './en-IN.json'
import hindi from './hi-IN.json'
import { i18n, localizationReady } from './i18n'
import { readLanguage, saveLanguage } from './languages'
import { transactionText } from './transactionText'
import { translateTranscript } from './transcriptTranslation'

function keys(catalog: Record<string, unknown>): string[] {
  return Object.entries(catalog).flatMap(([key, value]) =>
    typeof value === 'string' ? [key] : keys(value as Record<string, unknown>).map((subkey) => key + '.' + subkey),
  ).sort()
}

afterEach(() => vi.unstubAllGlobals())

describe('language preferences', () => {
  it('defaults to Hindi and persists independent choices', () => {
    const values = new Map<string, string>()
    vi.stubGlobal('window', { localStorage: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    } })

    expect(readLanguage('interface')).toBe('hi-IN')
    expect(readLanguage('speech')).toBe('hi-IN')
    saveLanguage('interface', 'en-IN')
    expect(readLanguage('interface')).toBe('en-IN')
    expect(readLanguage('speech')).toBe('hi-IN')
    saveLanguage('speech', 'en-IN')
    saveLanguage('interface', 'hi-IN')
    expect(readLanguage('speech')).toBe('en-IN')
  })

  it('uses Hindi when storage is blocked or the persisted value is unsupported', () => {
    vi.stubGlobal('window', { get localStorage() { throw new Error('Blocked') } })
    expect(readLanguage('interface')).toBe('hi-IN')
    expect(() => saveLanguage('interface', 'en-IN')).not.toThrow()

    vi.stubGlobal('window', { localStorage: { getItem: () => 'fr-FR' } })
    expect(readLanguage('interface')).toBe('hi-IN')
  })
})

describe('localized text', () => {
  it('ships matching catalogs and switches labels using bundled translations', async () => {
    await localizationReady
    expect(keys(hindi)).toEqual(keys(english))
    expect(i18n.resolvedLanguage).toBe('hi-IN')
    expect(i18n.t('dashboard.outstanding')).toBe('कुल बकाया')
    await i18n.changeLanguage('en-IN')
    expect(i18n.t('dashboard.outstanding')).toBe('Outstanding balance')
    expect(i18n.t('dashboard.balanceCount', { count: 18 })).toBe('18 customers owe money')
    await i18n.changeLanguage('hi-IN')
  })

  it('preserves opaque customer, amount, date and ID strings in both locales', async () => {
    await localizationReady
    const fields = {
      customerName: 'Asha $& {{surname}} <Store>',
      amount: '₹1,23,456.70',
      date: '01/02/2026 10:42 am',
      transactionId: 'BH-001/25',
    }
    const hindiPayment = transactionText(i18n.getFixedT('hi-IN'), { kind: 'payment', ...fields })
    const englishCredit = transactionText(i18n.getFixedT('en-IN'), { kind: 'credit', ...fields })

    for (const text of [hindiPayment, englishCredit]) {
      for (const field of Object.values(fields)) expect(text.receipt).toContain(field)
      expect(text.confirmation).toContain(fields.customerName)
      expect(text.confirmation).toContain(fields.amount)
    }
    expect(hindiPayment.confirmation).toContain('भुगतान')
    expect(englishCredit.receipt).toContain('Credit added')
  })
})

describe('offline transcript translation', () => {
  it('copies matched names and amounts verbatim into the English phrase', () => {
    expect(translateTranscript('Priya  Sharma ने १,२३४.५० रुपये दिए।', 'hi-IN'))
      .toBe('Priya  Sharma paid १,२३४.५० rupees.')
    expect(translateTranscript('सीमा ने ₹750 रुपये उधार लिए।', 'hi-IN'))
      .toBe('सीमा received credit for ₹750.')
  })

  it('leaves other statements unavailable and English input unchanged', () => {
    expect(translateTranscript('Priya ने 750 रुपये दिए। तारीख 01/02/2026।', 'hi-IN')).toBeUndefined()
    const original = ' Priya Sharma paid ₹750 on 01/02/2026 (BH-01). '
    expect(translateTranscript(original, 'en-IN')).toBe(original)
  })
})
