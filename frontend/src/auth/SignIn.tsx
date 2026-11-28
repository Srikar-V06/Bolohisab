import { ArrowRight, Eye, EyeOff, Store, UserRound } from 'lucide-react'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError, authApi } from '../api'
import type { Role } from '../api'
import AuthFrame from './AuthFrame'

type Field = 'full_name' | 'phone_number' | 'password' | 'confirm_password' | 'shop_name' | 'shop_address'
type FieldError = 'required' | 'invalidPhone' | 'passwordLength' | 'passwordMismatch'
type AuthError = 'invalidCredentials' | 'invalidInput' | 'registrationFailed' | 'rateLimited'
  | 'originDenied' | 'connectionFailed' | 'roleMismatch'

function messageFor(error: unknown): AuthError {
  if (!(error instanceof ApiError)) return 'connectionFailed'
  switch (error.code) {
    case 'INVALID_CREDENTIALS': return 'invalidCredentials'
    case 'ROLE_MISMATCH': return 'roleMismatch'
    case 'INVALID_AUTH_INPUT': return 'invalidInput'
    case 'REGISTRATION_FAILED': return 'registrationFailed'
    case 'AUTH_RATE_LIMITED': return 'rateLimited'
    case 'ORIGIN_NOT_ALLOWED': return 'originDenied'
    default: return 'connectionFailed'
  }
}

function validPhone(phone: string) {
  const compact = phone.trim().replace(/[ ()-]/g, '')
  return /^(?:[6-9][0-9]{9}|91[6-9][0-9]{9}|\+[1-9][0-9]{7,14})$/.test(compact)
}

export default function SignIn({ expired, login }: {
  expired: boolean; login: (role: Role, phone: string, password: string) => Promise<void>
}) {
  const { t } = useTranslation()
  const [role, setRole] = useState<Role>('SHOPKEEPER')
  const [register, setRegister] = useState(false)
  const [phone, setPhone] = useState('')
  const [visible, setVisible] = useState(false)
  const [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState<Partial<Record<Field, FieldError>>>({})
  const [error, setError] = useState<AuthError>()
  const [created, setCreated] = useState(false)
  const [showExpired, setShowExpired] = useState(expired)
  const roleLabel = t(role === 'SHOPKEEPER' ? 'auth.shopkeeper' : 'auth.customer')

  function changeMode(next: boolean, accountRole = role) {
    setRegister(next)
    setRole(accountRole)
    setVisible(false)
    setErrors({})
    setError(undefined)
    setCreated(false)
    setShowExpired(false)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    setError(undefined)
    setShowExpired(false)
    const form = event.currentTarget
    const data = new FormData(form)
    const value = (field: Field) => String(data.get(field) ?? '')
    const enteredPhone = value('phone_number')
    const password = value('password')
    const fullName = value('full_name').trim()
    const shopName = value('shop_name').trim()
    const address = value('shop_address').trim()
    const invalid: Partial<Record<Field, FieldError>> = {}
    if (register && !fullName) invalid.full_name = 'required'
    if (!enteredPhone.trim()) invalid.phone_number = 'required'
    else if (!validPhone(enteredPhone)) invalid.phone_number = 'invalidPhone'
    if (!password) invalid.password = 'required'
    else if (register && Array.from(password).length < 10) invalid.password = 'passwordLength'
    if (register && !value('confirm_password')) invalid.confirm_password = 'required'
    else if (register && value('confirm_password') !== password) invalid.confirm_password = 'passwordMismatch'
    if (register && role === 'SHOPKEEPER' && !shopName) invalid.shop_name = 'required'
    setErrors(invalid)
    const first = Object.keys(invalid)[0]
    if (first) {
      const field = form.elements.namedItem(first)
      if (field instanceof HTMLElement) field.focus()
      return
    }

    setBusy(true)
    try {
      if (register) {
        await authApi.register(role, {
          full_name: fullName, phone_number: enteredPhone, password,
          ...(role === 'SHOPKEEPER' ? { shop_name: shopName, ...(address ? { shop_address: address } : {}) } : {}),
        })
        changeMode(false)
        setCreated(true)
      } else {
        await login(role, enteredPhone, password)
      }
    } catch (failure) {
      setError(messageFor(failure))
    } finally {
      setBusy(false)
    }
  }

  function fieldMessage(field: Field, hint?: string) {
    const issue = errors[field]
    if (!issue && !hint) return null
    return <p id={field + '-message'} className={issue ? 'auth-field-error' : 'auth-hint'}>
      {issue ? t(`auth.${issue}`) : hint}
    </p>
  }

  function accessibility(field: Field, hint = false) {
    return {
      'aria-invalid': errors[field] ? true : undefined,
      'aria-describedby': errors[field] || hint ? field + '-message' : undefined,
    }
  }

  return <AuthFrame>
    <h1 className="auth-title">{t(register ? 'auth.registrationTitle' : 'auth.loginTitle', { role: roleLabel })}</h1>
    <div className="auth-role-options" role="group" aria-label={t('auth.chooseRole')}>
      <button type="button" aria-pressed={role === 'SHOPKEEPER'} disabled={busy}
        onClick={() => role !== 'SHOPKEEPER' && changeMode(register, 'SHOPKEEPER')}>
        <Store size={19} aria-hidden="true" /> {t('auth.shopkeeper')}
      </button>
      <button type="button" aria-pressed={role === 'CUSTOMER'} disabled={busy}
        onClick={() => role !== 'CUSTOMER' && changeMode(register, 'CUSTOMER')}>
        <UserRound size={19} aria-hidden="true" /> {t('auth.customer')}
      </button>
    </div>
    {showExpired && <p className="notice notice-error" role="alert">{t('auth.sessionExpired')}</p>}
    {created && <p className="notice" role="status">{t('auth.created')}</p>}
    {error && <p className="notice notice-error" role="alert">{t(`auth.${error}`)}</p>}
    <form className="auth-form" key={role + (register ? '-register' : '-login')} onSubmit={submit} noValidate>
      <fieldset disabled={busy}>
        {register && <div className="auth-field">
          <label htmlFor="full_name">{t('auth.fullName')}</label>
          <input id="full_name" name="full_name" autoComplete="name" required maxLength={120} {...accessibility('full_name')} />
          {fieldMessage('full_name')}
        </div>}
        <div className="auth-field">
          <label htmlFor="phone_number">{t('auth.phone')}</label>
          <input id="phone_number" name="phone_number" type="tel" autoComplete={register ? 'tel' : 'username'}
            value={phone} onChange={event => setPhone(event.target.value)} maxLength={48} required
            {...accessibility('phone_number', register)} />
          {fieldMessage('phone_number', register ? t('auth.phoneHint') : undefined)}
        </div>
        <div className="auth-field">
          <label htmlFor="password">{t('auth.password')}</label>
          <div className="auth-password">
            <input id="password" name="password" type={visible ? 'text' : 'password'} required maxLength={1024}
              autoComplete={register ? 'new-password' : 'current-password'} {...accessibility('password', register)} />
            <button type="button" className="icon-button" onClick={() => setVisible(value => !value)}
              aria-controls="password" aria-label={t(visible ? 'auth.hidePassword' : 'auth.showPassword')}>
              {visible ? <EyeOff size={20} aria-hidden="true" /> : <Eye size={20} aria-hidden="true" />}
            </button>
          </div>
          {fieldMessage('password', register ? t('auth.passwordHint') : undefined)}
        </div>
        {register && <div className="auth-field">
          <label htmlFor="confirm_password">{t('auth.confirmPassword')}</label>
          <input id="confirm_password" name="confirm_password" type="password" required maxLength={1024}
            autoComplete="new-password" {...accessibility('confirm_password')} />
          {fieldMessage('confirm_password')}
        </div>}
        {register && role === 'SHOPKEEPER' && <>
          <div className="auth-field">
            <label htmlFor="shop_name">{t('auth.shopName')}</label>
            <input id="shop_name" name="shop_name" autoComplete="organization" required maxLength={120} {...accessibility('shop_name')} />
            {fieldMessage('shop_name')}
          </div>
          <div className="auth-field">
            <label htmlFor="shop_address">{t('auth.shopAddress')}</label>
            <textarea id="shop_address" name="shop_address" autoComplete="street-address" maxLength={500} rows={2} />
          </div>
        </>}
        <button type="submit" className="button button-primary">
          {t(register ? (busy ? 'auth.creating' : 'auth.register') : (busy ? 'auth.signingIn' : 'auth.login'))}
          <ArrowRight size={18} aria-hidden="true" />
        </button>
      </fieldset>
    </form>
    <div className="auth-switch">
      <span>{t(register ? 'auth.alreadyAccount' : 'auth.newAccount')}</span>
      <button type="button" disabled={busy} onClick={() => changeMode(!register)}>
        {t(register ? 'auth.login' : 'auth.register')}
      </button>
    </div>
  </AuthFrame>
}
