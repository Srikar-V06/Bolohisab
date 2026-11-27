const rupees = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
})

export function formatRupees(amount: number) {
  return rupees.format(amount)
}

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
  { customer: customers[0], amount: 750, kind: 'Payment received', time: 'Today, 10:42 am' },
  { customer: customers[1], amount: 320, kind: 'Credit added', time: 'Today, 9:15 am' },
  { customer: customers[2], amount: 500, kind: 'Payment received', time: 'Yesterday' },
  { customer: customers[3], amount: 180, kind: 'Credit added', time: 'Yesterday' },
] as const

export const disputes = [
  { customer: customers[1], amount: 320, issue: 'Customer asked to confirm the amount.' },
  { customer: customers[2], amount: 140, issue: 'Customer is checking a duplicate entry.' },
] as const
