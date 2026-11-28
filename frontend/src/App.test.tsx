// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from './App'
import { i18n, localizationReady } from './localization/i18n'

const timestamp = '2026-11-27T05:00:00Z'
const transcript = '  Ramesh ke khate mein saadhe chaar sau likh do aur usne do sau cash diya hai.  '
const customer = { id: 7, name: 'Ramesh Kumar' }
const entry = { id: 9, type: 'CREDIT', amount_paise: 45000, created_at: timestamp, payment_method: null }
const receipt = {
  entry_id: entry.id, shop_name: 'Kirana Shop', customer_name: customer.name,
  type: entry.type, amount_paise: entry.amount_paise, created_at: entry.created_at,
  payment_method: null, balance_after_paise: 125000, issued_at: null, sent_at: null, share_token: null,
  status: 'AWAITING', receipt_id: null, customer_id: customer.id, dispute: null, language: null,
}
const issuedReceipt = {
  ...receipt, receipt_id: 1, issued_at: timestamp, share_token: 'test-token',
  share_url: 'https://receipts.example.com/api/receipts/share/test-token',
  language: 'en-IN', status: 'GENERATED',
}
const preview = {
  original_transcript: transcript, status: 'REVIEW_REQUIRED', detected_language: 'hi-Latn-IN',
  english_interpretation: 'Credit ₹450 and cash payment of ₹200 for Ramesh Kumar.',
  clarification: null,
  actions: [
    { customer, intent: 'CREDIT', amount_paise: 45000, payment_method: null },
    { customer, intent: 'PAYMENT', amount_paise: 20000, payment_method: 'CASH' },
  ],
  balances: [{
    customer, credit_paise: 45000, payment_paise: 20000, previous_balance_paise: 100000,
    updated_balance_paise: 125000,
  }],
}

class FakeRecognition {
  static current: FakeRecognition
  lang = ''
  onstart?: () => void
  onend?: () => void
  onresult?: (event: unknown) => void
  stopped = false
  start() { FakeRecognition.current = this }
  stop() { this.stopped = true }
  abort() {}
  partial(text: string) {
    this.onresult?.({ resultIndex: 0, results: [{ 0: { transcript: text }, isFinal: false }] })
  }
  /** A pause after a finalized phrase, as Chrome reports it in continuous mode. */
  pause(...phrases: string[]) {
    this.onresult?.({ resultIndex: 0, results: phrases.map(text => ({ 0: { transcript: text }, isFinal: true })) })
  }
  deliver(text: string) {
    this.onresult?.({ resultIndex: 0, results: [{ 0: { transcript: text }, isFinal: true }] })
    this.onend?.()
  }
}

const send = vi.fn()

function json(data: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } }))
}

async function navigate(name: string) {
  fireEvent.click(within(screen.getByRole('navigation')).getByRole('link', { name }))
  await waitFor(() => expect(within(screen.getByRole('navigation')).getByRole('link', { name }).getAttribute('aria-current')).toBe('page'))
}

beforeEach(async () => {
  await localizationReady
  await i18n.changeLanguage('hi-IN')
  window.history.replaceState(null, '', '/#speak')
  window.localStorage.clear()
  vi.stubGlobal('scrollTo', vi.fn())
  send.mockReset()
  vi.stubGlobal('fetch', send)
  if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = function () { this.open = true }
    HTMLDialogElement.prototype.close = function () { this.open = false }
  }
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

it('renders exactly three tabs, keeps Hindi as default, and remembers an English switch', async () => {
  send.mockResolvedValueOnce(await json([]))
  render(<App />)
  expect(screen.getByRole('heading', { name: 'बोलकर अपना हिसाब जोड़ें' })).toBeTruthy()
  expect(within(screen.getByRole('navigation')).getAllByRole('link')).toHaveLength(3)
  fireEvent.change(screen.getByRole('combobox', { name: 'ऐप की भाषा' }), { target: { value: 'en-IN' } })
  await screen.findByRole('heading', { name: 'Update your khata by voice' })
  await navigate('Customers')
  await screen.findByRole('heading', { name: 'Customers' })
  expect(window.localStorage.getItem('bolohisaab.interface-language')).toBe('en-IN')
  expect(window.localStorage.getItem('bolohisaab.speech-language')).toBeNull()
})

it('shows actual totals, filters by status and name, and opens a customer ledger sheet', async () => {
  await i18n.changeLanguage('en-IN')
  send.mockImplementation((path) => path === '/api/customers'
    ? json([
      { ...customer, balance_paise: 125000, last_transaction_at: timestamp },
      { id: 8, name: 'Sunita Devi', balance_paise: 240000, last_transaction_at: timestamp },
      { id: 12, name: 'Mohan', balance_paise: 0, last_transaction_at: null },
    ])
    : json({ items: [{ ...entry, balance_effect_paise: 45000, balance_after_paise: 125000 }], has_more: false, next_cursor: null }))
  render(<App />)
  await navigate('Customers')
  await screen.findByText('₹3,650')
  fireEvent.click(screen.getByRole('button', { name: 'Settled' }))
  expect(screen.getByText('Mohan')).toBeTruthy()
  expect(screen.queryByText('Ramesh Kumar')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'All' }))
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: '  RAMESH  ' } })
  expect(screen.queryByText('Sunita Devi')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: /Ramesh Kumar/ }))
  const sheet = await screen.findByRole('dialog', { name: customer.name })
  await within(sheet).findByText('₹450')
  expect(within(sheet).getByText('Current balance')).toBeTruthy()
  expect(window.location.hash).toBe('#customers')
})

it('loads five from the API, keeps them on failure, and appends unique items on retry', async () => {
  await i18n.changeLanguage('en-IN')
  const makeEntries = (ids: number[]) => ids.map((id) => ({
    ...entry, id, amount_paise: id * 100, balance_effect_paise: id * 100, balance_after_paise: id * 500,
  }))
  let finishNext: (response: Response) => void = () => {}
  let attempts = 0
  send.mockImplementation((path: string) => {
    if (path === '/api/customers') return json([
      { ...customer, balance_paise: 5000, last_transaction_at: timestamp },
      { id: 8, name: 'Sunita Devi', balance_paise: 0, last_transaction_at: null },
    ])
    if (path === '/api/customers/8/ledger?limit=5') return json({ items: [], has_more: false, next_cursor: null })
    if (path === '/api/customers/7/ledger?limit=5&cursor=page-2') {
      attempts += 1
      if (attempts === 1) return new Promise<Response>((resolve) => { finishNext = resolve })
      return json({ items: makeEntries([6, 5, 4, 3, 2, 1]), has_more: false, next_cursor: null })
    }
    if (path === '/api/customers/7/ledger?limit=5') {
      return json({ items: makeEntries([10, 9, 8, 7, 6]), has_more: true, next_cursor: 'page-2' })
    }
    return json({}, 404)
  })
  render(<App />)
  await navigate('Customers')
  fireEvent.click(await screen.findByRole('button', { name: /Ramesh Kumar/ }))
  const sheet = within(screen.getByRole('dialog', { name: customer.name }))
  fireEvent.click(await sheet.findByRole('button', { name: 'Load more' }))
  expect((sheet.getByRole('button', { name: 'Loading…' }) as HTMLButtonElement).disabled).toBe(true)
  expect(sheet.getAllByRole('listitem')).toHaveLength(5)
  await act(async () => finishNext(await json({}, 503)))
  expect(sheet.getAllByRole('listitem')).toHaveLength(5)
  fireEvent.click(await sheet.findByRole('button', { name: 'Try again' }))
  await sheet.findByText('All transactions shown.')
  expect(sheet.getAllByRole('listitem')).toHaveLength(10)
  const order = sheet.getAllByRole('listitem').map((row) => row.querySelector('.history-amount strong')?.textContent)
  expect(order).toEqual(['+₹10', '+₹9', '+₹8', '+₹7', '+₹6', '+₹5', '+₹4', '+₹3', '+₹2', '+₹1'])
  expect(sheet.queryByRole('button', { name: 'Load more' })).toBeNull()
  fireEvent.click(sheet.getByRole('button', { name: 'Close' }))
  fireEvent.click(screen.getByRole('button', { name: /Sunita Devi/ }))
  await within(screen.getByRole('dialog', { name: 'Sunita Devi' })).findByText('No transactions yet')
  expect(screen.queryByText('+₹10')).toBeNull()
})

it('keeps both desktop lists interactive while their detail panels are open', async () => {
  await i18n.changeLanguage('en-IN')
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
  send.mockImplementation((path: string) => {
    if (path === '/api/customers') return json([
      { ...customer, balance_paise: 125000, last_transaction_at: timestamp },
      { id: 8, name: 'Sunita Devi', balance_paise: 240000, last_transaction_at: timestamp },
    ])
    if (path === '/api/receipts') return json([receipt, { ...receipt, entry_id: 10, customer_name: 'Sunita Devi' }])
    return json({ items: [], has_more: false, next_cursor: null })
  })
  render(<App />)
  await navigate('Customers')
  fireEvent.click(await screen.findByRole('button', { name: /Ramesh Kumar/ }))
  expect(screen.getByRole('region', { name: 'Ramesh Kumar' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: /Sunita Devi/ }))
  expect(screen.getByRole('region', { name: 'Sunita Devi' })).toBeTruthy()
  expect(screen.queryByRole('dialog')).toBeNull()
  await navigate('Receipts')
  fireEvent.click(await screen.findByRole('button', { name: /Ramesh Kumar/ }))
  const panel = within(screen.getByRole('region', { name: 'Receipt preview' }))
  expect(panel.getByText('Ramesh Kumar')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: /Sunita Devi/ }))
  const nextPanel = within(screen.getByRole('region', { name: 'Receipt preview' }))
  expect(nextPanel.getByText('Sunita Devi')).toBeTruthy()
  expect(screen.queryByRole('dialog')).toBeNull()
})

it('handles recording and preview, cancels without writing, and posts only after Confirm', async () => {
  await i18n.changeLanguage('en-IN')
  vi.stubGlobal('SpeechRecognition', FakeRecognition)
  window.localStorage.setItem('bolohisaab.speech-language', 'hi-IN')
  send.mockImplementation((path) => json(path === '/api/voice/parse' ? preview : {}))
  render(<App />)
  const record = async () => {
    fireEvent.click(screen.getByRole('button', { name: 'Start recording' }))
    expect(screen.getByText('Requesting microphone access…')).toBeTruthy()
    expect(FakeRecognition.current.lang).toBe('hi-IN')
    act(() => FakeRecognition.current.onstart?.())
    expect(screen.getByText('Listening…')).toBeTruthy()
    act(() => FakeRecognition.current.partial('Ramesh ke khate'))
    expect(screen.getByText('Ramesh ke khate')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Stop recording' }))
    expect(screen.getByText('Processing your recording…')).toBeTruthy()
    act(() => FakeRecognition.current.deliver(transcript))
    await screen.findByText('Awaiting confirmation')
  }
  await record()
  const sheet = screen.getByRole('dialog')
  expect(within(sheet).getByText('₹450')).toBeTruthy()
  expect(within(sheet).getByText('₹200')).toBeTruthy()
  expect(within(sheet).getByText('₹1,000')).toBeTruthy()
  expect(within(sheet).getByText('₹1,250')).toBeTruthy()
  expect(sheet.querySelector('blockquote')?.textContent).toBe(transcript)
  fireEvent.click(within(sheet).getByRole('button', { name: 'Cancel' }))
  expect(send.mock.calls.map(([path]) => path).filter((path) => path !== '/api/customers' && path !== '/api/receipts')).toEqual(['/api/voice/parse'])
  await record()
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
  await screen.findByRole('heading', { name: 'Transaction saved' })
  const [path, request] = send.mock.calls.at(-1)!
  expect(path).toBe('/api/voice/confirm')
  expect(JSON.parse(request.body)).toMatchObject({
    original_transcript: transcript,
    previous_balances: { '7': 100000 },
    actions: [{ amount_paise: 45000 }, { amount_paise: 20000, payment_method: 'CASH' }],
  })
})

it('shows microphone fallback and localizes a clarification in the app language', async () => {
  await i18n.changeLanguage('en-IN')
  const { unmount } = render(<App />)
  expect((screen.getByRole('button', { name: 'Start recording' }) as HTMLButtonElement).disabled).toBe(true)
  expect(screen.getByText(/Voice recording isn’t available/)).toBeTruthy()
  unmount()
  vi.stubGlobal('SpeechRecognition', FakeRecognition)
  send.mockImplementation(() => json({
    ...preview, status: 'CLARIFICATION_REQUIRED', balances: [], actions: [], english_interpretation: null,
    clarification: { code: 'MISSING_AMOUNT', candidates: [] },
  }))
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Start recording' }))
  act(() => FakeRecognition.current.deliver(transcript))
  await screen.findByText('How much should I record?')
  expect(screen.queryByRole('button', { name: 'Confirm' })).toBeNull()
})

it('keeps listening through pauses and submits the whole sentence after sustained silence', async () => {
  await i18n.changeLanguage('en-IN')
  vi.stubGlobal('SpeechRecognition', FakeRecognition)
  send.mockImplementation((path) => json(path === '/api/voice/parse' ? preview : []))
  render(<App />)
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  try {
    fireEvent.click(screen.getByRole('button', { name: 'Start recording' }))
    act(() => FakeRecognition.current.onstart?.())
    // Silence before the first word never ends the capture on our side.
    act(() => vi.advanceTimersByTime(10_000))
    expect(FakeRecognition.current.stopped).toBe(false)
    act(() => FakeRecognition.current.pause('Ramesh'))
    act(() => vi.advanceTimersByTime(2_000))
    act(() => FakeRecognition.current.pause('Ramesh', ' 450 credit'))
    act(() => vi.advanceTimersByTime(2_000))
    expect(FakeRecognition.current.stopped).toBe(false)
    expect(screen.getByText('Ramesh 450 credit')).toBeTruthy()
    act(() => vi.advanceTimersByTime(600))
    expect(FakeRecognition.current.stopped).toBe(true)
  } finally {
    vi.useRealTimers()
  }
  act(() => FakeRecognition.current.onend?.())
  await screen.findByText('Awaiting confirmation')
  const parse = send.mock.calls.find(([path]) => path === '/api/voice/parse')
  expect(JSON.parse(parse?.[1].body).original_transcript).toBe('Ramesh 450 credit')
})

it('shows confirmed receipt rows, previews the balance, and separates generation from sharing', async () => {
  await i18n.changeLanguage('en-IN')
  window.localStorage.setItem('bolohisaab.receipt-language', 'en-IN')
  send.mockImplementation((path) => {
    if (path === '/api/receipts') return json([receipt])
    if (path === '/api/receipts/9') return json(issuedReceipt)
    return json({ ...issuedReceipt, sent_at: timestamp, status: 'SENT' })
  })
  render(<App />)
  await navigate('Receipts')
  await screen.findByText('Receipt due')
  fireEvent.click(screen.getByRole('button', { name: /Ramesh Kumar/ }))
  const sheet = screen.getByRole('dialog', { name: 'Receipt preview' })
  expect(within(sheet).getByText('Kirana Shop')).toBeTruthy()
  expect(within(sheet).getByText('₹1,250')).toBeTruthy()
  fireEvent.click(within(sheet).getByRole('button', { name: 'Generate receipt' }))
  await within(sheet).findByRole('button', { name: 'Share receipt link' })
  expect(screen.getByRole('button', { name: 'Sent' }).getAttribute('aria-pressed')).toBe('true')
  fireEvent.click(within(sheet).getByRole('button', { name: 'Copy link' }))
  const link = await within(sheet).findByRole<HTMLInputElement>('textbox', { name: 'Share receipt link' })
  expect(link.value).toBe(issuedReceipt.share_url + '?language=en-IN')
  expect(send.mock.calls.map(([path]) => path)).not.toContain('/api/receipts/9/sent')
  fireEvent.click(within(sheet).getByRole('button', { name: 'Mark as sent' }))
  await within(sheet).findByText('Receipt marked as sent.')
  fireEvent.click(within(sheet).getByRole('button', { name: 'Close' }))
  fireEvent.click(screen.getByRole('button', { name: 'Sent' }))
  expect(screen.getByRole('button', { name: /Ramesh Kumar/ })).toBeTruthy()
  expect(window.location.hash).toBe('#receipts')
})

it('uses browser voice and native sharing with clipboard fallback', async () => {
  await i18n.changeLanguage('en-IN')
  const speak = vi.fn()
  const share = vi.fn().mockRejectedValueOnce(new DOMException('Unavailable', 'NotAllowedError'))
    .mockResolvedValueOnce(undefined)
  const writeText = vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('speechSynthesis', { getVoices: () => [{ lang: 'hi-IN' }, { lang: 'en-IN' }], speak, cancel: vi.fn() })
  vi.stubGlobal('SpeechSynthesisUtterance', class {
    constructor(readonly text: string) {}
  })
  vi.stubGlobal('navigator', { share, clipboard: { writeText } })
  send.mockImplementation((path) => path === '/api/receipts'
    ? json([issuedReceipt]) : json({ ...issuedReceipt, status: 'SENT', sent_at: timestamp }))
  render(<App />)
  await navigate('Receipts')
  fireEvent.click(screen.getByRole('button', { name: 'Sent' }))
  fireEvent.click(await screen.findByRole('button', { name: /Ramesh Kumar/ }))
  const sheet = within(screen.getByRole('dialog', { name: 'Receipt preview' }))
  fireEvent.change(sheet.getByRole('combobox', { name: 'Receipt language' }), { target: { value: 'hi-IN' } })
  fireEvent.click(sheet.getByRole('button', { name: 'Listen to receipt' }))
  expect(speak).toHaveBeenCalledWith(expect.objectContaining({
    lang: 'hi-IN', text: expect.stringContaining('Ramesh Kumar'),
  }))
  fireEvent.click(sheet.getByRole('button', { name: 'Stop playback' }))
  fireEvent.click(sheet.getByRole('button', { name: 'Share receipt link' }))
  await sheet.findByText(/Link copied/)
  const link = issuedReceipt.share_url + '?language=hi-IN'
  expect(writeText).toHaveBeenCalledWith(link)
  expect(send.mock.calls.map(([path]) => path)).not.toContain('/api/receipts/9/sent')
  fireEvent.click(sheet.getByRole('button', { name: 'Share receipt link' }))
  await sheet.findByText('Receipt marked as sent.')
  expect(share).toHaveBeenLastCalledWith({ title: 'रसीद देखें', url: link })
})

it.each([
  ['APPROVED', 'Accept correction', 'Correction accepted. An adjustment was added to the ledger.'],
  ['REJECTED', 'Reject correction', 'Correction rejected.'],
] as const)('reviews a discrepancy as %s inside the receipt preview', async (decision, button, notice) => {
  await i18n.changeLanguage('en-IN')
  const item = {
    ...issuedReceipt, type: 'PAYMENT', amount_paise: 20000, status: 'DISPUTED',
    dispute: {
      id: 7, claimed_amount_paise: 30000, adjustment_paise: -10000, reason: 'I paid ₹300.', status: 'PENDING',
      created_at: timestamp, reviewed_at: null, reviewed_by: null, adjustment_entry_id: null,
    },
  }
  const reviewed = { ...item, dispute: {
    ...item.dispute, status: decision, reviewed_at: timestamp, reviewed_by: 'Shivani',
    adjustment_entry_id: decision === 'APPROVED' ? 10 : null,
  } }
  let saved = false
  send.mockImplementation((path) => {
    if (path === '/api/receipts/9/dispute/review') {
      saved = true
      return json(reviewed)
    }
    return json(path === '/api/receipts' ? [saved ? reviewed : item] : [])
  })
  render(<App />)
  await navigate('Receipts')
  fireEvent.click(screen.getByRole('button', { name: 'Sent' }))
  fireEvent.click(await screen.findByRole('button', { name: /Ramesh Kumar.*Disputed/ }))
  const dialog = screen.getByRole('dialog', { name: 'Receipt preview' })
  const sheet = within(dialog)
  const section = dialog.querySelector('details')!
  section.open = true
  expect(sheet.getByText('−₹100')).toBeTruthy()
  expect(sheet.getByText('I paid ₹300.')).toBeTruthy()
  fireEvent.change(sheet.getByRole('textbox', { name: 'Your name for the review record' }), { target: { value: 'Shivani' } })
  fireEvent.click(sheet.getByRole('button', { name: button }))
  await sheet.findByText(notice)
  expect(sheet.getByText(/Shivani/)).toBeTruthy()
  expect(send.mock.calls).toContainEqual(['/api/receipts/9/dispute/review', expect.objectContaining({
    body: JSON.stringify({ decision, reviewer: 'Shivani' }),
  })])
  expect(window.location.hash).toBe('#receipts')
})
