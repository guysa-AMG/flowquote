export function formatCents(cents: number, currency: string = 'ZAR'): string {
  const sign = cents < 0 ? '-' : ''
  const abs = Math.abs(cents)
  const rands = Math.floor(abs / 100)
  const centsRemainder = (abs % 100).toString().padStart(2, '0')
  return `${sign}${currency} ${rands.toLocaleString()}.${centsRemainder}`
}

export function formatQuantity(milli: number): string {
  const qty = milli / 1000
  if (qty % 1 === 0) return qty.toString()
  if ((milli % 100) === 0) return qty.toFixed(1)
  if ((milli % 10) === 0) return qty.toFixed(2)
  return qty.toFixed(3)
}
