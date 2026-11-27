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

const indiaDay = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit',
})

/** Group newest first, preserving input order for equal timestamps. */
export function transactionDays<T extends { created_at: string }>(entries: T[], language: Locale, now = new Date()) {
  const groups = new Map<string, { key: string; label: string; entries: T[] }>()
  const today = indiaDay.format(now)
  const yesterday = indiaDay.format(now.getTime() - 86_400_000)
  const relative = new Intl.RelativeTimeFormat(language, { numeric: 'auto' })
  const date = new Intl.DateTimeFormat(language, { timeZone: 'Asia/Kolkata', dateStyle: 'long' })
  const sorted = entries.slice().sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
  for (const entry of sorted) {
    const instant = new Date(entry.created_at)
    const key = indiaDay.format(instant)
    let group = groups.get(key)
    if (!group) {
      const label = key === today ? relative.format(0, 'day') : key === yesterday ? relative.format(-1, 'day') : date.format(instant)
      group = { key, label, entries: [] }
      groups.set(key, group)
    }
    group.entries.push(entry)
  }
  return Array.from(groups.values())
}
