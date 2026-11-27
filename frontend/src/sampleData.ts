const rupees = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
})

export function formatRupees(amount: number) {
  return rupees.format(amount)
}

export const shopName = 'Sharma Kirana'

export const dashboard = {
  outstanding: 24_850,
  customersWithBalance: 18,
  collectedThisWeek: 8_450,
  creditAddedThisWeek: 5_750,
  openDisputes: 2,
}

export const customers = [
  { name: 'Priya Sharma', balance: 1_250, color: 'sage' },
  { name: 'Ramesh Yadav', balance: 820, color: 'sand' },
  { name: 'Sunita Verma', balance: 340, color: 'lilac' },
  { name: 'Amit Gupta', balance: 0, color: 'blue' },
] as const

export type Customer = (typeof customers)[number]

export const activity = [
  { customer: customers[0], amount: 750, kind: 'payment', time: '10:42 am' },
  { customer: customers[1], amount: 320, kind: 'credit', time: '9:15 am' },
  { customer: customers[2], amount: 500, kind: 'payment', time: null },
  { customer: customers[3], amount: 180, kind: 'credit', time: null },
] as const

export const disputes = [
  { customer: customers[1], amount: 320, issue: 'confirmAmount' },
  { customer: customers[2], amount: 140, issue: 'duplicateEntry' },
] as const

export const sampleVoice = {
  transcript: 'Priya Sharma ne 750 rupaye diye.',
  english: 'Priya Sharma paid 750 rupees.',
  customerName: customers[0].name,
  amount: activity[0].amount,
  kind: activity[0].kind,
  transactionId: 'BH-DEMO-001',
  date: '2026-11-27',
} as const
