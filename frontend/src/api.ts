import type { Locale } from './localization/languages'

export type EntryType = 'CREDIT' | 'PAYMENT' | 'ADJUSTMENT'
export type PaymentMethod = 'CASH' | 'UPI'
export type SpeechLanguage = Locale | 'hi-Latn-IN'
export type CustomerIdentity = { id: number; name: string }
export type Customer = CustomerIdentity & { shop_id: number; balance_paise: number; last_transaction_at: string | null }
export type LedgerEntry = {
  id: number
  type: EntryType
  amount_paise: number
  payment_method: PaymentMethod | null
  created_at: string
}
export type HistoryEntry = LedgerEntry & {
  balance_effect_paise: number
  balance_after_paise: number
}
export type LedgerPage = {
  items: HistoryEntry[]
  next_cursor: string | null
  has_more: boolean
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
export type ReceiptStatus = 'AWAITING' | 'GENERATED' | 'SENT' | 'CONFIRMED' | 'DISPUTED'
export type DisputeDecision = 'APPROVED' | 'REJECTED'
export type ReceiptDispute = {
  id: number
  claimed_amount_paise: number | string
  adjustment_paise: number | string
  reason: string
  status: 'PENDING' | DisputeDecision
  created_at: string
  reviewed_by: string | null
  reviewed_at: string | null
  adjustment_entry_id: number | null
}
export type Receipt = Omit<LedgerEntry, 'id' | 'amount_paise'> & {
  entry_id: number
  receipt_id: number | null
  customer_id: number
  shop_name: string
  customer_name: string
  amount_paise: number | string
  balance_after_paise: number | string
  issued_at: string | null
  sent_at: string | null
  confirmed_at: string | null
  language: Locale | null
  status: ReceiptStatus
  share_token: string | null
  share_url: string | null
  dispute: ReceiptDispute | null
}

export class ApiError extends Error {
  constructor(readonly code: string, readonly status?: number) {
    super(code)
  }
}

export type Role = 'SHOPKEEPER' | 'CUSTOMER'
export type Account = {
  id: number
  full_name: string
  normalized_phone_number: string
  role: Role
  shop_id: number | null
}
export type Registration = {
  full_name: string
  phone_number: string
  password: string
  shop_name?: string
  shop_address?: string
}

type SessionEvent = 'expired' | 'csrfRefreshed'
const sessionListeners = new Set<(event: SessionEvent) => void>()
let csrf: string | undefined
let generation = 0
let refresh: Promise<void> | undefined

export function setSessionCsrf(token?: string) {
  generation += 1
  csrf = token
  refresh = undefined
}

export function onSessionEvent(listener: (event: SessionEvent) => void) {
  sessionListeners.add(listener)
  return () => { sessionListeners.delete(listener) }
}

function expireSession() {
  setSessionCsrf()
  sessionListeners.forEach(listener => listener('expired'))
}

function refreshCsrf(session: number) {
  refresh ??= authApi.csrf().then(token => {
    if (generation !== session) return
    csrf = token
    sessionListeners.forEach(listener => listener('csrfRefreshed'))
  }).catch((error: unknown) => {
    if (generation === session && error instanceof ApiError && error.status === 401) expireSession()
  }).finally(() => {
    if (generation === session) refresh = undefined
  })
  return refresh
}

async function request<T>(path: string, options?: RequestInit, authRequest = false): Promise<T> {
  const session = generation
  const headers = new Headers(options?.headers)
  if (!authRequest && csrf && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(options?.method ?? 'GET')) {
    headers.set('X-CSRF-Token', csrf)
  }
  const response = await fetch('/api' + path, { ...options, headers, credentials: 'include', cache: 'no-store' })
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    const code = typeof error.detail === 'string' ? error.detail : 'REQUEST_FAILED'
    if (!authRequest && !options?.signal?.aborted && csrf && session === generation) {
      if (response.status === 401) expireSession()
      if (response.status === 403 && code === 'CSRF_INVALID') await refreshCsrf(session)
    }
    throw new ApiError(code, response.status)
  }
  if (response.status === 204) return undefined as T
  const body = await response.text()
  return JSON.parse(body, (_, value: unknown) => {
    if (typeof value === 'number' && !Number.isSafeInteger(value)) throw new ApiError('PRECISION')
    return value
  }) as T
}

function post<T>(path: string, body: object, signal?: AbortSignal, authRequest = false) {
  return request<T>(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body), signal,
  }, authRequest)
}

export const authApi = {
  register: (role: Role, body: Registration) =>
    post<Account>(role === 'SHOPKEEPER' ? '/auth/register/shopkeeper' : '/auth/register/customer', body, undefined, true),
  login: (phone_number: string, password: string) =>
    post<Account>('/auth/login', { phone_number, password }, undefined, true),
  me: (signal?: AbortSignal) => request<Account>('/auth/me', { signal }, true),
  csrf: async (signal?: AbortSignal) =>
    (await request<{ csrf_token: string }>('/auth/csrf', { signal }, true)).csrf_token,
  logout: (token?: string) => token
    ? request<void>('/auth/logout', { method: 'POST', headers: { 'X-CSRF-Token': token } }, true)
    : request<void>('/auth/logout', { method: 'POST' }),
}

export const api = {
  customers: (signal?: AbortSignal) => request<Customer[]>('/customers', { signal }),
  ledger: (id: number, cursor: string | null, signal: AbortSignal) => {
    const query = new URLSearchParams({ limit: '5' })
    if (cursor) query.set('cursor', cursor)
    return request<LedgerPage>(`/customers/${id}/ledger?${query}`, { signal })
  },
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
  reviewDispute: (id: number, decision: DisputeDecision, reviewer: string) =>
    post<Receipt>('/receipts/' + id + '/dispute/review', { decision, reviewer }),
}
