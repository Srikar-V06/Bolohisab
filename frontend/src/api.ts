import type { Locale } from './localization/languages'

export type EntryType = 'CREDIT' | 'PAYMENT' | 'ADJUSTMENT'
export type PaymentMethod = 'CASH' | 'UPI'
export type SpeechLanguage = Locale | 'hi-Latn-IN'
export type CustomerIdentity = { id: number; name: string }
export type Customer = CustomerIdentity & { balance_paise: number; last_transaction_at: string | null }
export type LedgerEntry = {
  id: number
  type: EntryType
  amount_paise: number
  payment_method: PaymentMethod | null
  created_at: string
}
export type PreviewBalance = {
  customer: CustomerIdentity
  previous_balance_paise: number
  updated_balance_paise: number
  credit_paise: number
  payment_paise: number
}
export type VoiceAction = {
  intent: 'CREDIT' | 'PAYMENT' | 'BALANCE_QUERY'
  customer: CustomerIdentity
  amount_paise: number | null
  payment_method: PaymentMethod | null
}
export type ClarificationCode = 'MISSING_INTENT' | 'MISSING_AMOUNT' | 'INVALID_AMOUNT' | 'MISSING_CUSTOMER'
  | 'CUSTOMER_NOT_FOUND' | 'AMBIGUOUS_CUSTOMER'
export type ParseResult = {
  original_transcript: string
  detected_language: SpeechLanguage | null
  status: 'REVIEW_REQUIRED' | 'CLARIFICATION_REQUIRED'
  actions: VoiceAction[]
  balances: PreviewBalance[]
  english_interpretation: string | null
  clarification: { code: ClarificationCode; candidates: CustomerIdentity[] } | null
}
export type Receipt = Omit<LedgerEntry, 'id'> & {
  entry_id: number
  shop_name: string
  customer_name: string
  balance_after_paise: number
  issued_at: string | null
  sent_at: string | null
  share_token: string | null
}

export class ApiError extends Error {
  constructor(readonly code: string) {
    super(code)
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch('/api' + path, options)
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new ApiError(typeof error.detail === 'string' ? error.detail : 'REQUEST_FAILED')
  }
  const body = await response.text()
  return JSON.parse(body, (_, value: unknown) => {
    if (typeof value === 'number' && !Number.isSafeInteger(value)) throw new ApiError('PRECISION')
    return value
  }) as T
}

function post<T>(path: string, body: object, signal?: AbortSignal) {
  return request<T>(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body), signal,
  })
}

export const api = {
  customers: (signal?: AbortSignal) => request<Customer[]>('/customers', { signal }),
  ledger: (id: number, signal?: AbortSignal) => request<LedgerEntry[]>(`/customers/${id}/ledger`, { signal }),
  parse: (original_transcript: string, interface_language: Locale, speech_language: Locale, signal: AbortSignal) =>
    post<ParseResult>('/voice/parse', { original_transcript, interface_language, speech_language }, signal),
  confirm: (result: ParseResult, batch_id: string) => {
    const actions = result.actions.flatMap(({ customer, intent, amount_paise, payment_method }) =>
      intent === 'BALANCE_QUERY' ? [] : [{ customer_id: customer.id, intent, amount_paise, payment_method }],
    )
    const ids = new Set(actions.map(({ customer_id }) => customer_id))
    const previous_balances = Object.fromEntries(result.balances
      .filter(({ customer }) => ids.has(customer.id))
      .map(({ customer, previous_balance_paise }) => [customer.id, previous_balance_paise]))
    return post<void>('/voice/confirm', { original_transcript: result.original_transcript, batch_id, actions, previous_balances })
  },
  receipts: (signal?: AbortSignal) => request<Receipt[]>('/receipts', { signal }),
  generate: (id: number, language: Locale) => post<Receipt>(`/receipts/${id}`, { language }),
  markSent: (id: number) => post<Receipt>(`/receipts/${id}/sent`, {}),
}
