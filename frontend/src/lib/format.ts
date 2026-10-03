export const fixed = (value: number | null | undefined, digits = 1, dash = '—') =>
  value === null || value === undefined || Number.isNaN(value) ? dash : value.toFixed(digits)

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  const s = Math.max(0, Math.round(seconds))
  const m = Math.floor(s / 60)
  return `${m}:${String(s % 60).padStart(2, '0')}`
}

export function distance(metres: number | null | undefined): string {
  if (metres === null || metres === undefined) return '—'
  return metres >= 1000 ? `${(metres / 1000).toFixed(2)} km` : `${Math.round(metres)} m`
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour12: false })
}

export const words = (s: string) => s.replaceAll('_', ' ')
