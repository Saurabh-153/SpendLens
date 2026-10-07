// Neutral colours are CSS variables set by themeStore.ts, so the whole app re-themes at once.
// The accent / status colours are plain hex so they can still take an alpha suffix (`${T.warn}55`); the two accents follow the theme.
import { currentTheme } from './themeStore'

export const T = {
  bg: 'var(--bg)',
  surface: 'var(--surface)',
  surface2: 'var(--surface2)',
  border: 'var(--border)',
  hairline: 'var(--hairline)',
  text: 'var(--text)',
  muted: 'var(--muted)',
  sideBg: 'var(--side-bg)',          // category / Actual / Target columns of the expense grid
  dangerBorder: 'var(--danger-border)',
  today: 'var(--today)',
  // The two accents depend on the chosen theme; they are read when a component renders.
  get accent() { return currentTheme().accent },
  get accent2() { return currentTheme().accent2 },
  warn: '#f59e0b',
  danger: '#ef4444',
  positive: '#22c55e',
  negative: '#f43f5e',
}

export function fmt(n: number): string {
  const a = Math.abs(n)
  if (a >= 1e7) return `₹${(n / 1e7).toFixed(2)}Cr`
  if (a >= 1e5) return `₹${(n / 1e5).toFixed(2)}L`
  if (a >= 1e3) return `₹${(n / 1e3).toFixed(1)}k`
  return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
}

/** A whole-rupee amount; under ₹1,000 it keeps paise (at most two places). */
export const fmtFull = (n: number) => `₹${Math.abs(n).toLocaleString('en-IN', { maximumFractionDigits: Math.abs(n) >= 1000 ? 0 : 2 })}`

export const signed = (n: number, f: (x: number) => string = fmt) => `${n >= 0 ? '+' : '-'}${f(Math.abs(n))}`

export const pnlColor = (n: number) => (n >= 0 ? T.positive : T.negative)

export const HOLDING_TYPES = ['EQ', 'MF', 'GOLD', 'FD', 'PF', 'CASH'] as const

export const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
