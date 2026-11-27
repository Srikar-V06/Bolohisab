import type { TFunction } from 'i18next'
import type { EntryType, PaymentMethod } from './api'
import type { Locale } from './localization/languages'

const rupees = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })

export function money(paise: number | bigint) {
  const value = BigInt(paise)
  const absolute = value < 0n ? -value : value
  const fraction = absolute % 100n
  return (value < 0n ? '−' : '') + '₹' + rupees.format(absolute / 100n)
    + (fraction ? '.' + String(fraction).padStart(2, '0') : '')
}

export function transactionDate(value: string, language: Locale) {
  return new Intl.DateTimeFormat(language, {
    timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit',
  }).format(new Date(value))
}

export function transactionLabel(t: TFunction, type: EntryType, method: PaymentMethod | null) {
  return method ? t(`entry.method.${method}`) : t(`entry.type.${type}`)
}

export function initials(name: string, language: Locale) {
  const segmenter = new Intl.Segmenter(language, { granularity: 'grapheme' })
  return name.trim().split(/\s+/).slice(0, 2)
    .map((word) => [...segmenter.segment(word)][0]?.segment.toLocaleUpperCase(language) ?? '').join('')
}
