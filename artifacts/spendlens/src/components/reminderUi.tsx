import { MONTHS, T } from '../theme'

export const REMINDER_PALETTE = ['#f5b942', '#fb7185', '#3ecf8e', '#38bdf8', '#a78bfa', '#fb923c', '#2dd4bf', '#f472b6']

export function ord(n: number): string {
  const s = ['th', 'st', 'nd', 'rd'], v = n % 100
  return n + (s[(v - 20) % 10] || s[v] || s[0])
}

export const REPEAT_TEXT = { monthly: 'Every month', quarterly: 'Every 3 months', yearly: 'Every year' } as const

/** Round colour choices; arrow keys move between them like any radio group. */
export function Swatches({ value, onChange }: { value: string; onChange: (c: string) => void }) {
  return (
    <div role="radiogroup" aria-label="Colour" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      {REMINDER_PALETTE.map(c => (
        <label key={c} style={{ cursor: 'pointer', position: 'relative' }}>
          <input type="radio" name="reminder-colour" value={c} checked={value === c} onChange={() => onChange(c)} aria-label={`Colour ${c}`}
            style={{ position: 'absolute', opacity: 0, inset: 0 }} />
          <span style={{ display: 'block', width: 22, height: 22, borderRadius: '50%', background: c,
            boxShadow: value === c ? `0 0 0 2px ${T.surface}, 0 0 0 4px ${T.text}` : `0 0 0 2px ${T.surface}` }} />
        </label>
      ))}
    </div>
  )
}

export function Switch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label style={{ position: 'relative', width: 34, height: 20, flexShrink: 0, display: 'inline-block' }}>
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} aria-label={label}
        style={{ position: 'absolute', inset: 0, opacity: 0, margin: 0, cursor: 'pointer', zIndex: 1 }} />
      <span style={{ position: 'absolute', inset: 0, borderRadius: 999, background: checked ? T.accent : T.border, transition: 'background .15s' }} />
      <span style={{ position: 'absolute', top: 2, left: 2, width: 16, height: 16, borderRadius: '50%', background: '#fff',
        transform: checked ? 'translateX(14px)' : 'none', transition: 'transform .15s' }} />
    </label>
  )
}

/** HH:MM from what a person types ("9:00", "21:30"); null when it isn't a time. */
export function parseTime(text: string): string | null {
  const m = text.trim().match(/^([01]?\d|2[0-3]):([0-5]\d)$/)
  return m ? `${m[1].padStart(2, '0')}:${m[2]}` : null
}

/** '24 Oct to 29 Oct 2026' (years shown on both ends when the trip crosses a year). */
export function vacationRange(startIso: string, endIso: string): string {
  const part = (iso: string, year: boolean) => `${Number(iso.slice(8))} ${MONTHS[Number(iso.slice(5, 7)) - 1].slice(0, 3)}${year ? ` ${iso.slice(0, 4)}` : ''}`
  if (startIso === endIso) return part(startIso, true)
  const cross = startIso.slice(0, 4) !== endIso.slice(0, 4)
  return `${part(startIso, cross)} to ${part(endIso, true)}`
}
