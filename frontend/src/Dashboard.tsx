import {
  ArrowDownLeft, ArrowUpRight, CircleAlert, Mic, Wallet,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { activity, dashboard, formatRupees, shopName } from './sampleData'
import type { Customer } from './sampleData'

export function CustomerAvatar({ customer }: { customer: Customer }) {
  const initials = customer.name.split(' ').map((part) => part[0]).join('')
  return <span aria-hidden="true" className={`customer-avatar avatar-${customer.color}`}>{initials}</span>
}

export function WeeklySummary() {
  const { t } = useTranslation()
  const collected = dashboard.collectedThisWeek
  const credit = dashboard.creditAddedThisWeek
  const collectedShare = (collected / (collected + credit)) * 100

  return (
    <section className="panel self-start p-5 sm:p-6" aria-labelledby="weekly-summary">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id="weekly-summary" className="section-heading">{t('dashboard.weeklySummary')}</h2>
          <p className="mt-1 text-sm text-muted">{t('dashboard.weeklyIntro')}</p>
        </div>
        <span className="period-label">{t('dashboard.thisWeek')}</span>
      </div>
      <div aria-hidden="true" className="mt-7 flex h-3 gap-1 overflow-hidden rounded-full">
        <span className="rounded-full bg-primary" style={{ width: `${collectedShare}%` }} />
        <span className="flex-1 rounded-full bg-mint-bar" />
      </div>
      <dl className="mt-4 divide-y divide-line">
        <div className="summary-row">
          <dt><span aria-hidden="true" className="summary-dot bg-primary" /> {t('transaction.payment')}</dt>
          <dd>{formatRupees(collected)}</dd>
        </div>
        <div className="summary-row">
          <dt><span aria-hidden="true" className="summary-dot bg-mint-bar" /> {t('transaction.credit')}</dt>
          <dd>{formatRupees(credit)}</dd>
        </div>
      </dl>
    </section>
  )
}

export default function Dashboard() {
  const { t } = useTranslation()
  const stats = [
    {
      id: 'outstanding',
      label: t('dashboard.outstanding'),
      value: formatRupees(dashboard.outstanding),
      detail: t('dashboard.balanceCount', { count: dashboard.customersWithBalance }),
      icon: Wallet,
      color: 'sage',
    },
    {
      id: 'payment',
      label: t('transaction.payment'),
      value: formatRupees(dashboard.collectedThisWeek),
      detail: t('dashboard.collected'),
      icon: ArrowDownLeft,
      color: 'blue',
    },
    {
      id: 'disputes',
      label: t('dashboard.openDisputes'),
      value: dashboard.openDisputes,
      detail: t('dashboard.awaitingReview'),
      icon: CircleAlert,
      color: 'sand',
    },
  ]

  return (
    <>
      <div>
        <h1 tabIndex={-1} className="page-heading">{t('dashboard.greeting', { shopName })}</h1>
        <p className="page-intro">{t('dashboard.intro')}</p>
      </div>

      <section className="voice-hero relative isolate overflow-hidden rounded-[1.25rem] px-5 py-7 sm:px-8 sm:py-8" aria-labelledby="voice-prompt">
        <div aria-hidden="true" className="voice-art hidden sm:grid">
          <div className="voice-ring voice-ring-outer" />
          <div className="voice-ring voice-ring-middle" />
          <div className="voice-ring voice-ring-inner" />
          <div className="voice-orb"><Mic size={44} strokeWidth={1.7} /></div>
          <div className="voice-wave voice-wave-left"><i /><i /><i /><i /><i /></div>
          <div className="voice-wave voice-wave-right"><i /><i /><i /><i /><i /></div>
        </div>
        <div className="relative">
          <span className="hero-label"><Mic size={15} aria-hidden="true" /> {t('dashboard.voiceLabel')}</span>
          <h2 id="voice-prompt" className="mt-3 max-w-[24rem] text-[1.65rem] leading-snug font-extrabold sm:text-[2rem]">{t('dashboard.voiceHeading')}</h2>
          <p className="mt-2 max-w-[26rem] text-sm leading-relaxed text-[#d4eee3] sm:text-base">{t('dashboard.voiceIntro')}</p>
          <a href="#voice-entry" className="button button-hero mt-5">
            <Mic size={18} aria-hidden="true" />
            {t('dashboard.tryVoice')}
          </a>
        </div>
      </section>

      <dl className="grid gap-3 sm:grid-cols-3 sm:gap-4" aria-label={t('dashboard.statistics')}>
        {stats.map(({ id, label, value, detail, icon: Icon, color }) => (
          <div key={id} className="panel relative flex flex-col p-4 sm:p-5">
            <dt className="flex items-center gap-3 text-sm leading-snug font-bold text-muted">
              <span className={`stat-icon avatar-${color}`}><Icon size={19} aria-hidden="true" /></span>
              {label}
            </dt>
            <dd className="mt-3 text-[1.65rem] leading-none font-extrabold tracking-tight tabular-nums sm:text-[1.8rem]">{value}</dd>
            <dd className="mt-2 text-sm text-muted">{detail}</dd>
          </div>
        ))}
      </dl>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <section className="panel min-w-0 px-4 pt-5 sm:px-6 sm:pt-6" aria-labelledby="recent-activity">
          <h2 id="recent-activity" className="section-heading">{t('dashboard.recentActivity')}</h2>
          <p className="mt-1 text-sm text-muted">{t('dashboard.recentIntro')}</p>
          <ul className="mt-3 divide-y divide-line">
            {activity.map(({ customer, amount, kind, time }) => (
              <li key={customer.name} className="activity-row">
                <CustomerAvatar customer={customer} />
                <div>
                  <p className="text-sm font-extrabold">{customer.name}</p>
                  <p className="mt-0.5 text-xs leading-snug text-muted sm:text-sm">
                    {time ? t('dashboard.todayAt', { time }) : t('dashboard.yesterday')}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-extrabold tabular-nums">{formatRupees(amount)}</p>
                  <p className={`mt-0.5 flex items-center justify-end gap-1 text-xs font-bold ${kind === 'payment' ? 'text-primary' : 'text-muted'}`}>
                    {kind === 'payment' ? <ArrowDownLeft size={13} aria-hidden="true" /> : <ArrowUpRight size={13} aria-hidden="true" />}
                    {t(`transaction.${kind}`)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </section>
        <WeeklySummary />
      </div>
    </>
  )
}
