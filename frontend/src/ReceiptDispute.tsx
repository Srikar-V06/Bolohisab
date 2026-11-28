import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { DisputeDecision, ReceiptDispute as Dispute } from './api'
import { money, receiptDate } from './format'
import type { Locale } from './localization/languages'

export default function ReceiptDispute({ dispute, language, pending, review }: {
  dispute: Dispute; language: Locale; pending: boolean
  review: (decision: DisputeDecision, reviewer: string) => void
}) {
  const { t } = useTranslation()
  const id = useId()
  const [reviewer, setReviewer] = useState('')

  const name = reviewer.trim()

  return (
    <details className="receipt-dispute">
      <summary>
        {t('receiptList.dispute.title')}
        <span className="status-chip amber">{t(`receiptList.dispute.status.${dispute.status}`)}</span>
      </summary>
      <div className="receipt-dispute-content">
        <dl>
          <div className="info-row"><dt>{t('receiptList.dispute.claim')}</dt><dd>{money(dispute.claimed_amount_paise)}</dd></div>
          <div className="info-row"><dt>{t('receiptList.dispute.reason')}</dt><dd>{dispute.reason}</dd></div>
          <div className="info-row"><dt>{t('receiptList.dispute.requestedAt')}</dt>
            <dd><time dateTime={dispute.created_at}>{receiptDate(dispute.created_at, language)}</time></dd>
          </div>
          <div className="info-row"><dt>{t('receiptList.dispute.adjustment')}</dt>
            <dd>{BigInt(dispute.adjustment_paise) > 0n ? '+' : ''}{money(dispute.adjustment_paise)}</dd>
          </div>
          {dispute.reviewed_at && <div className="info-row"><dt>{t('receiptList.dispute.reviewedBy')}</dt>
            <dd>{dispute.reviewed_by} · <time dateTime={dispute.reviewed_at}>{receiptDate(dispute.reviewed_at, language)}</time></dd>
          </div>}
          {dispute.adjustment_entry_id !== null && <div className="info-row"><dt>{t('receiptList.dispute.adjustmentId')}</dt>
            <dd>#{dispute.adjustment_entry_id}</dd>
          </div>}
        </dl>
        {dispute.status === 'PENDING' && (
          <div className="receipt-review-form">
            <label htmlFor={id}>{t('receiptList.dispute.reviewer')}</label>
            <input id={id} value={reviewer} onChange={(event) => setReviewer(event.currentTarget.value)}
              maxLength={120} autoComplete="name" disabled={pending} />
            <div className="sheet-actions receipt-actions">
              <button type="button" className="button button-secondary" disabled={pending || !name}
                onClick={() => review('REJECTED', name)}>
                {t('receiptList.dispute.reject')}
              </button>
              <button type="button" className="button button-primary" disabled={pending || !name}
                onClick={() => review('APPROVED', name)}>
                {t('receiptList.dispute.approve')}
              </button>
            </div>
          </div>
        )}
      </div>
    </details>
  )
}
