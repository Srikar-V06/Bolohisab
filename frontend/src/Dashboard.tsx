import {
  ArrowDownLeft, ArrowUpRight, CircleAlert, Mic, Wallet,
} from 'lucide-react'
import { activity, dashboard, formatRupees } from './sampleData'
import type { Customer } from './sampleData'

export function CustomerAvatar({ customer }: { customer: Customer }) {
  const initials = customer.name.split(' ').map((part) => part[0]).join('')
  return <span aria-hidden="true" className={`customer-avatar avatar-${customer.color}`}>{initials}</span>
}

export function WeeklySummary() {
  const collected = dashboard.collectedThisWeek
  const credit = dashboard.creditAddedThisWeek
  const collectedShare = (collected / (collected + credit)) * 100

  return (
    <section className="panel self-start p-5 sm:p-6" aria-labelledby="weekly-summary">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id="weekly-summary" className="section-heading">Weekly summary</h2>
          <p className="mt-1 text-sm text-muted">Money in and credit given</p>
        </div>
        <span className="period-label">This week</span>
      </div>
      <div aria-hidden="true" className="mt-7 flex h-3 gap-1 overflow-hidden rounded-full">
        <span className="rounded-full bg-primary" style={{ width: `${collectedShare}%` }} />
        <span className="flex-1 rounded-full bg-mint-bar" />
      </div>
      <dl className="mt-4 divide-y divide-line">
        <div className="summary-row">
          <dt><span aria-hidden="true" className="summary-dot bg-primary" /> Payments received</dt>
          <dd>{formatRupees(collected)}</dd>
        </div>
        <div className="summary-row">
          <dt><span aria-hidden="true" className="summary-dot bg-mint-bar" /> Credit added</dt>
          <dd>{formatRupees(credit)}</dd>
        </div>
      </dl>
    </section>
  )
}

const stats = [
  {
    label: 'Outstanding balance',
    value: formatRupees(dashboard.outstanding),
    detail: `${dashboard.customersWithBalance} customers owe money`,
    icon: Wallet,
    color: 'sage',
  },
  {
    label: 'Payments received',
    value: formatRupees(dashboard.collectedThisWeek),
    detail: 'Collected this week',
    icon: ArrowDownLeft,
    color: 'blue',
  },
  {
    label: 'Open disputes',
    value: dashboard.openDisputes,
    detail: 'Awaiting review',
    icon: CircleAlert,
    color: 'sand',
  },
] as const

export default function Dashboard() {
  return (
    <>
      <div>
        <h1 tabIndex={-1} className="page-heading">Namaste, Sharma Kirana</h1>
        <p className="page-intro">Here’s what’s happening in your khata.</p>
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
          <span className="hero-label"><Mic size={15} aria-hidden="true" /> Voice khata</span>
          <h2 id="voice-prompt" className="mt-3 max-w-[24rem] text-[1.65rem] leading-tight font-extrabold sm:text-[2rem]">Add to your khata by voice</h2>
          <p className="mt-2 max-w-[26rem] text-sm leading-relaxed text-[#d4eee3] sm:text-base">Try a sample entry and see what it looks like in your ledger.</p>
          <a href="#voice-entry" className="button button-hero mt-5">
            <Mic size={18} aria-hidden="true" />
            Try voice entry
          </a>
        </div>
      </section>

      <dl className="grid gap-3 sm:grid-cols-3 sm:gap-4" aria-label="Khata at a glance">
        {stats.map(({ label, value, detail, icon: Icon, color }) => (
          <div key={label} className="panel relative flex flex-col p-4 sm:p-5">
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
          <h2 id="recent-activity" className="section-heading">Recent activity</h2>
          <p className="mt-1 text-sm text-muted">Latest updates to your khata</p>
          <ul className="mt-3 divide-y divide-line">
            {activity.map(({ customer, amount, kind, time }) => (
              <li key={customer.name} className="activity-row">
                <CustomerAvatar customer={customer} />
                <div>
                  <p className="text-sm font-extrabold">{customer.name}</p>
                  <p className="mt-0.5 text-xs leading-snug text-muted sm:text-sm">{time}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-extrabold tabular-nums">{formatRupees(amount)}</p>
                  <p className={`mt-0.5 flex items-center justify-end gap-1 text-xs font-bold ${kind === 'Payment received' ? 'text-primary' : 'text-muted'}`}>
                    {kind === 'Payment received' ? <ArrowDownLeft size={13} aria-hidden="true" /> : <ArrowUpRight size={13} aria-hidden="true" />}
                    {kind}
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
