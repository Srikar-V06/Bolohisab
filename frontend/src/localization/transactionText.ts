import type { TFunction } from 'i18next'

type TransactionDisplay = Readonly<{
  kind: 'payment' | 'credit'
  customerName: string
  amount: string
  transactionId: string
  date: string
}>

export function transactionText(t: TFunction, transaction: TransactionDisplay) {
  const { amount, customerName, transactionId, date, kind } = transaction

  return {
    confirmation: t(`transaction.confirmation.${kind}`, { amount, customerName }),
    receipt: t('transaction.receipt', {
      amount, customerName, transactionId, date, type: t(`transaction.${kind}`),
    }),
  }
}
