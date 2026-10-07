import type { Holding } from './api'

// Source names arrive in capitals ("HDFC BANK LIMITED"): show them as "HDFC Bank" without the legal suffix.
const ACRONYMS = new Set(['HDFC', 'ICICI', 'TCS', 'LIC', 'SBI', 'ITC', 'IT', 'ETF', 'FOF', 'NSE'])
export const titleCase = (s: string) => s.toLowerCase().replace(/(^|[\s(-])[a-z]/g, c => c.toUpperCase()).replace(/[A-Za-z]+/g, w => (ACRONYMS.has(w.toUpperCase()) ? w.toUpperCase() : w))
export const cleanName = (n: string) => titleCase(n.replace(/\b(limited|ltd\.?)\s*$/i, '').trim())
/** Name as shown everywhere: no legal suffix, no folio number (shown separately), SGBs shortened to "SGB Jun 2029 · Series III". */
export function displayName(h: Pick<Holding, 'name' | 'ticker' | 'asset_type'>): { name: string; folio: string } {
  let name = h.name, folio = ''
  const f = name.match(/\s*\(Folio:\s*([\w-]+)\)/i)
  if (f) { name = name.replace(f[0], '').trim(); folio = `Folio ···${f[1].slice(-4)}` }
  if (/^sovereign gold bond/i.test(name)) {
    const t = h.ticker.match(/^SGB([A-Z]{3})(\d{2})$/)
    const sr = name.match(/(?:\bSR\.?|Series)[-\s]*([IVX]+)\b/i)
    if (t) name = `SGB ${t[1][0]}${t[1].slice(1).toLowerCase()} 20${t[2]}${sr ? ` · Series ${sr[1].toUpperCase()}` : ''}`
  } else if (h.asset_type === 'EQ') name = cleanName(name)
  return { name, folio }
}
