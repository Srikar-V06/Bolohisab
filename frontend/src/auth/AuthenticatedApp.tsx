import { LogOut } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import App from '../App'
import { ApiError, authApi, onSessionEvent, setSessionCsrf } from '../api'
import type { Account, Role } from '../api'
import AuthFrame from './AuthFrame'
import CustomerAccount from './CustomerAccount'
import SignIn from './SignIn'
import './auth.css'

type AuthState = { screen: 'checking' | 'offline' } | { screen: 'login'; expired: boolean }
  | { screen: 'active'; account: Account }
const shopRoutes = new Set(['', '#speak', '#customers', '#receipts'])

export default function AuthenticatedApp() {
  const { t } = useTranslation()
  const [state, setState] = useState<AuthState>({ screen: 'checking' })
  const [revision, setRevision] = useState(0)
  const [route, setRoute] = useState(() => window.location.hash)
  const [signingOut, setSigningOut] = useState(false)
  const [notice, setNotice] = useState<'csrfRefreshed' | 'logoutFailed'>()
  const sessionChannel = useRef<BroadcastChannel>(null)

  useEffect(() => {
    const hashChanged = () => setRoute(window.location.hash)
    window.addEventListener('hashchange', hashChanged)
    const unsubscribe = onSessionEvent(event => {
      if (event === 'expired') setState({ screen: 'login', expired: true })
      if (event === 'csrfRefreshed') setNotice('csrfRefreshed')
    })
    return () => {
      window.removeEventListener('hashchange', hashChanged)
      unsubscribe()
    }
  }, [])

  useEffect(() => {
    if (typeof BroadcastChannel !== 'function') return
    const channel = new BroadcastChannel('bolohisaab-session')
    sessionChannel.current = channel
    channel.onmessage = ({ data }) => {
      if (data !== 'changed') return
      setSessionCsrf()
      setNotice(undefined)
      setState({ screen: 'checking' })
      setRevision(value => value + 1)
    }
    return () => {
      sessionChannel.current = null
      channel.close()
    }
  }, [])

  useEffect(() => {
    const check = new AbortController()
    async function restore() {
      try {
        const account = await authApi.me(check.signal)
        const token = await authApi.csrf(check.signal)
        if (check.signal.aborted) return
        setSessionCsrf(token)
        setState({ screen: 'active', account })
      } catch (error) {
        if (check.signal.aborted) return
        setSessionCsrf()
        setState(error instanceof ApiError && error.status === 401
          ? { screen: 'login', expired: false } : { screen: 'offline' })
      }
    }
    void restore()
    return () => check.abort()
  }, [revision])

  function go(path: string) {
    window.location.hash = path
    setRoute(path)
  }

  async function login(role: Role, phone: string, password: string) {
    setNotice(undefined)
    await authApi.login(phone, password)
    const account = await authApi.me()
    const token = await authApi.csrf()
    if (role !== account.role) {
      // The real account has been authenticated. Revoke its cookie before presenting the chooser again.
      await authApi.logout(token)
      sessionChannel.current?.postMessage('changed')
      throw new ApiError('ROLE_MISMATCH')
    }
    setSessionCsrf(token)
    if (role === 'CUSTOMER') go('#customer')
    else if (!shopRoutes.has(window.location.hash)) go('#speak')
    setState({ screen: 'active', account })
    sessionChannel.current?.postMessage('changed')
  }

  async function logout() {
    if (signingOut) return
    setSigningOut(true)
    setNotice(undefined)
    try {
      await authApi.logout()
      setSessionCsrf()
      go('')
      setState({ screen: 'login', expired: false })
      sessionChannel.current?.postMessage('changed')
    } catch (error) {
      if (!(error instanceof ApiError && (error.status === 401 || error.code === 'CSRF_INVALID'))) {
        setNotice('logoutFailed')
      }
    } finally {
      setSigningOut(false)
    }
  }

  if (state.screen === 'checking') return <AuthFrame>
    <p className="auth-session-status" role="status">{t('auth.sessionCheck')}</p>
  </AuthFrame>
  if (state.screen === 'offline') return <AuthFrame>
    <p className="notice notice-error" role="alert">{t('auth.connectionFailed')}</p>
    <button type="button" className="button button-primary" onClick={() => {
      setState({ screen: 'checking' })
      setRevision(value => value + 1)
    }}>{t('common.retry')}</button>
  </AuthFrame>
  if (state.screen === 'login') return <SignIn expired={state.expired} login={login} />
  if (state.screen !== 'active') return null

  const { account } = state
  const actions = <div className="account-action">
    <button type="button" className="auth-logout" onClick={() => void logout()} disabled={signingOut}>
      <LogOut size={17} aria-hidden="true" />
      <span>{t(signingOut ? 'auth.signingOut' : 'auth.logout')}</span>
    </button>
    {notice && <p role="status" className="auth-action-notice">{t(notice === 'csrfRefreshed' ? 'auth.csrfRefreshed' : 'auth.logoutFailed')}</p>}
  </div>
  const shopkeeper = account.role === 'SHOPKEEPER'
  const customer = account.role === 'CUSTOMER'
  if (shopkeeper && shopRoutes.has(route)) return <App key={account.id} accountActions={actions} />
  if (customer && (!route || route === '#customer')) return <CustomerAccount key={account.id} account={account} actions={actions} />
  return <AuthFrame>
    <h1 className="auth-title">{t('auth.unauthorized')}</h1>
    <div className="auth-unauthorized-actions">
      <button type="button" className="button button-primary" onClick={() => go(shopkeeper ? '#speak' : '#customer')}>
        {t('auth.backToAccount')}
      </button>
      {actions}
    </div>
  </AuthFrame>
}
