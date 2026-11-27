import type { Locale } from './languages'

// Accept only complete, unambiguous Hindi phrases with a name and numeric amount.
const hindiTransaction = /^([\p{L}\p{M}][\p{L}\p{M} .’'-]*?) ने (₹?[0-9०-९]+(?:,[0-9०-९]+)*(?:\.[0-9०-९]+)?) रुपये (दिए|उधार लिए)[।.]?$/u

export function translateTranscript(text: string, locale: Locale): string | undefined {
  if (locale === 'en-IN') return text
  if (locale !== 'hi-IN') return undefined

  const match = hindiTransaction.exec(text)
  if (!match) return undefined

  const [, customerName, amount, action] = match
  const amountWithCurrency = amount.startsWith('₹') ? amount : amount + ' rupees'
  const verb = action === 'दिए' ? ' paid ' : ' received credit for '
  return customerName + verb + amountWithCurrency + '.'
}
