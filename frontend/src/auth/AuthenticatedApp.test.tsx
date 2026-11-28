// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, setSessionCsrf } from '../api'
import { i18n, localizationReady } from '../localization/i18n'
import AuthenticatedApp from './AuthenticatedApp'

const seller = { id: 1, full_name: 'Sita', role: 'SHOPKEEPER', shop_id: 2 }
const buyer = { id: 2, full_name: 'Anand', role: 'CUSTOMER', shop_id: null }
const request = vi.fn<(path: string, options?: RequestInit) => Promise<Response>>()
const response = (body: unknown, status = 200) =>
  Promise.resolve(new Response(status === 204 ? null : JSON.stringify(body), { status }))
const missing = () => response({ detail: 'AUTH_REQUIRED' }, 401)
const csrfResponse = (token = 'csrf-one') => response({ csrf_token: token })

beforeEach(async () => {
  await localizationReady
  window.localStorage.clear()
  window.history.replaceState(null, '', '/')
  await i18n.changeLanguage('en-IN')
  request.mockReset()
  vi.stubGlobal('fetch', request)
  vi.stubGlobal('scrollTo', vi.fn())
  setSessionCsrf()
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function write(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label, { exact: true }), { target: { value } })
}

function submit(name = 'Sign in') {
  fireEvent.click(screen.getByRole('button', { name }))
}

async function enterCredentials(password = '  some passphrase  ') {
  await screen.findByLabelText('Phone number')
  write('Phone number', '9876543210')
  write('Password', password)
}

it('checks the session before rendering, shows Hindi by default, and supports password visibility and English', async () => {
  await i18n.changeLanguage('hi-IN')
  let finish!: (value: Response) => void
  request.mockReturnValue(new Promise(resolve => { finish = resolve }))
  render(<AuthenticatedApp />)
  expect(screen.getByRole('status').textContent).toBe('आपका सत्र जाँचा जा रहा है…')
  expect(screen.queryByRole('navigation')).toBeNull()
  expect(screen.queryByLabelText('पासवर्ड')).toBeNull()
  await act(async () => finish(await missing()))
  await screen.findByRole('heading', { name: 'दुकानदार साइन इन' })
  fireEvent.change(screen.getByRole('combobox', { name: 'ऐप की भाषा' }), { target: { value: 'en-IN' } })
  const password = screen.getByLabelText('Password', { exact: true })
  expect(password.getAttribute('type')).toBe('password')
  fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
  expect(password.getAttribute('type')).toBe('text')
  fireEvent.click(screen.getByRole('button', { name: 'Hide password' }))
  expect(password.getAttribute('type')).toBe('password')
})

it('signs in, takes the role from /me, preserves the three tabs and revokes the session on logout', async () => {
  let signedIn = false
  request.mockImplementation((path) => {
    switch (path) {
      case '/api/auth/me': return signedIn ? response(seller) : missing()
      case '/api/auth/login': signedIn = true; return response(seller)
      case '/api/auth/csrf': return csrfResponse()
      case '/api/auth/logout': signedIn = false; return response(null, 204)
      default: return response([])
    }
  })
  render(<AuthenticatedApp />)
  await enterCredentials()
  submit()
  const nav = await screen.findByRole('navigation')
  expect(within(nav).getAllByRole('link').map(link => link.textContent)).toEqual(['Customers', 'Speak', 'Receipts'])
  const login = request.mock.calls.find(([path]) => path === '/api/auth/login')?.[1]
  expect(login?.credentials).toBe('include')
  expect(JSON.parse(String(login?.body))).toEqual({ phone_number: '9876543210', password: '  some passphrase  ' })
  submit('Sign out')
  await screen.findByRole('heading', { name: 'Shopkeeper sign-in' })
  expect(screen.queryByRole('navigation')).toBeNull()
  const logout = request.mock.calls.find(([path]) => path === '/api/auth/logout')?.[1]
  expect(new Headers(logout?.headers).get('X-CSRF-Token')).toBe('csrf-one')
  expect(logout?.credentials).toBe('include')
})

it('restores a customer session, protects shop routes, and renders scoped ledgers without shopkeeper navigation', async () => {
  window.history.replaceState(null, '', '/#receipts')
  request.mockImplementation(path => {
    if (path === '/api/auth/me') return response(buyer)
    if (path === '/api/auth/csrf') return csrfResponse()
    if (path === '/api/customers') return response([{ id: 2, name: 'Anand', shop_id: 6, balance_paise: 1200 }])
    if (path === '/api/customers/2/ledger?limit=5') return response({ items: [], has_more: false })
    if (path === '/api/receipts') return response([])
    throw Error(path)
  })
  render(<AuthenticatedApp />)
  await screen.findByRole('heading', { name: 'This page isn’t available for your account' })
  expect(request.mock.calls.map(([path]) => path)).toEqual(['/api/auth/me', '/api/auth/csrf'])
  submit('Go to my account')
  await screen.findByRole('heading', { name: 'My account' })
  expect(screen.queryByRole('navigation')).toBeNull()
  fireEvent.click(await screen.findByRole('button', { name: /Anand.*Shop #6/ }))
  await screen.findByText('There are no transactions in this ledger.')
})

it('shows invalid credentials and discards a session created with the wrong selected account type', async () => {
  let loginCount = 0
  request.mockImplementation(path => {
    if (path === '/api/auth/me') return loginCount === 2 ? response(buyer) : missing()
    if (path === '/api/auth/login') return ++loginCount === 2 ? response(buyer) : response({ detail: 'INVALID_CREDENTIALS' }, 401)
    if (path === '/api/auth/csrf') return csrfResponse()
    if (path === '/api/auth/logout') return response(null, 204)
    throw Error(path)
  })
  render(<AuthenticatedApp />)
  await enterCredentials('mistyped')
  submit()
  await screen.findByRole('alert')
  expect(screen.getByRole('alert').textContent).toMatch(/Check your phone number and password/)
  write('Password', 'good passphrase')
  submit()
  await screen.findByText(/This account belongs to the other account type/)
  expect(screen.queryByRole('navigation')).toBeNull()
  expect(request.mock.calls.some(([path]) => path === '/api/auth/logout')).toBe(true)
})

it.each(['SHOPKEEPER', 'CUSTOMER'] as const)('validates and submits the %s registration form', async role => {
  request.mockImplementation(path => path === '/api/auth/me' ? missing() : response({}, 201))
  render(<AuthenticatedApp />)
  await screen.findByRole('heading', { name: 'Shopkeeper sign-in' })
  if (role === 'CUSTOMER') submit('Customer')
  submit('Create an account')
  const form = document.querySelector('form')!
  expect(Boolean(screen.queryByLabelText('Shop name'))).toBe(role === 'SHOPKEEPER')
  write('Full name', 'Account name')
  write('Phone number', '9876543210')
  write('Password', 'some passphrase')
  write('Confirm password', 'wrong value')
  if (role === 'SHOPKEEPER') {
    write('Shop name', 'Corner Shop')
    write('Shop address (optional)', 'Pune')
  }
  fireEvent.submit(form)
  expect(screen.getByText('The passwords do not match.')).toBeTruthy()
  expect(request.mock.calls).toHaveLength(1)
  write('Confirm password', 'some passphrase')
  fireEvent.submit(form)
  await screen.findByText('Your account was created. Sign in to continue.')
  const [, data] = request.mock.calls.find(([path]) => path.endsWith(role.toLowerCase()))!
  const body = JSON.parse(String(data?.body))
  expect(body).toEqual({
    full_name: 'Account name', phone_number: '9876543210', password: 'some passphrase',
    ...(role === 'SHOPKEEPER' ? { shop_name: 'Corner Shop', shop_address: 'Pune' } : {}),
  })
  expect((screen.getByLabelText('Password', { exact: true }) as HTMLInputElement).value).toBe('')
})

it('refreshes a rejected CSRF token without replaying a write and clears the UI on expiry', async () => {
  let token = 0
  let attempts = 0
  request.mockImplementation(path => {
    if (path === '/api/auth/me') return response(seller)
    if (path === '/api/auth/csrf') return csrfResponse('csrf-' + ++token)
    if (path === '/api/voice/parse') {
      if (++attempts === 1) return response({ detail: 'CSRF_INVALID' }, 403)
      return missing()
    }
    return response([])
  })
  render(<AuthenticatedApp />)
  await screen.findByRole('navigation')
  const send = () => api.parse('Ramesh 10', 'en-IN', 'en-IN', new AbortController().signal)
  await act(async () => { await expect(send()).rejects.toMatchObject({ code: 'CSRF_INVALID' }) })
  expect(attempts).toBe(1)
  await screen.findByText('Your session was refreshed. Try that action again.')
  await act(async () => { await expect(send()).rejects.toMatchObject({ code: 'AUTH_REQUIRED' }) })
  expect(attempts).toBe(2)
  const mutations = request.mock.calls.filter(([path]) => path === '/api/voice/parse')
  expect(mutations.map(([, init]) => new Headers(init?.headers).get('X-CSRF-Token'))).toEqual(['csrf-1', 'csrf-2'])
  expect(screen.queryByRole('navigation')).toBeNull()
  await screen.findByText('Your session expired. Sign in again.')
})

it('signs a customer in to their own workspace even from a prior shop hash', async () => {
  let signedIn = false
  request.mockImplementation(path => {
    if (path === '/api/auth/me') return signedIn ? response(buyer) : missing()
    if (path === '/api/auth/login') { signedIn = true; return response(buyer) }
    if (path === '/api/auth/csrf') return csrfResponse()
    return response([])
  })
  window.history.replaceState(null, '', '/#customers')
  render(<AuthenticatedApp />)
  await screen.findByRole('heading', { name: 'Shopkeeper sign-in' })
  submit('Customer')
  await enterCredentials()
  submit()
  await screen.findByRole('heading', { name: 'My account' })
  expect(window.location.hash).toBe('#customer')
  await waitFor(() => expect(screen.getByText('You don’t have any linked ledgers yet.')).toBeTruthy())
})

it('clears the prior workspace when another tab changes the session', async () => {
  let notify: (message: { data: string }) => void = () => {}
  vi.stubGlobal('BroadcastChannel', class {
    set onmessage(listener: (message: { data: string }) => void) { notify = listener }
    close() {}
  })
  let account: typeof seller | typeof buyer = seller
  request.mockImplementation(path => {
    if (path === '/api/auth/me') return response(account)
    if (path === '/api/auth/csrf') return csrfResponse()
    return response([])
  })
  render(<AuthenticatedApp />)
  await screen.findByRole('navigation')
  account = buyer
  act(() => notify({ data: 'changed' }))
  expect(screen.queryByRole('navigation')).toBeNull()
  await screen.findByRole('heading', { name: 'My account' })
  expect(screen.getByText('Anand')).toBeTruthy()
})
