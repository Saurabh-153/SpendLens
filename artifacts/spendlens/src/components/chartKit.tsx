// Shared pieces for the hand-drawn SVG charts on the Goals & Forecast tab: axis ticks, label spreading, a width hook,
// toggle chips, stat tiles and the hover card.
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { T } from '../theme'
import { label } from './ui'

export const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export const probColor = (p: number) => (p >= 80 ? T.positive : p >= 50 ? T.warn : T.negative)

/** Round axis ticks (1, 2, 2.5 or 5 × a power of ten) covering lo..hi. */
export function niceTicks(lo: number, hi: number, n = 4) {
  const raw = (hi - lo) / n || 1, p = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map(m => m * p).find(s => s >= raw) ?? raw
  const out: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) out.push(v)
  return out
}

/** One-dimensional label placement: each item as close to where it wants to be as possible, at least `gap` apart,
 *  inside [min, max]. `wants` must be sorted. Used for badges, payment dots, goal cards and right-edge labels. */
export function spread(wants: number[], gap: number, min: number, max: number) {
  const pos = wants.slice()
  for (let i = 0; i < pos.length; i++) pos[i] = Math.max(pos[i], i ? pos[i - 1] + gap : min)
  for (let i = pos.length - 1; i >= 0; i--) pos[i] = Math.min(pos[i], i < pos.length - 1 ? pos[i + 1] - gap : max)
  for (let i = 0; i < pos.length; i++) pos[i] = Math.max(pos[i], i ? pos[i - 1] + gap : min)
  return pos
}

/** The smallest of 1/2/5/10 units between labels that leaves `minPx` per label. */
export const labelStep = (pxPerUnit: number, minPx = 44) => [1, 2, 5, 10].find(s => s * pxPerUnit >= minPx) ?? 10

/** Width of the element in px, kept up to date so the SVG draws in real pixels (crisp text, no stretching). */
export function useWidth() {
  const ref = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(() => setW(el.clientWidth))
    ro.observe(el)
    setW(el.clientWidth)
    return () => ro.disconnect()
  }, [])
  return [ref, w] as const
}

export function Chip({ on, onClick, children, disabled, title }: { on: boolean; onClick: () => void; children: ReactNode; disabled?: boolean; title?: string }) {
  return (
    <button onClick={onClick} aria-pressed={on} disabled={disabled} title={title} style={{
      border: 'none', background: on ? T.surface : 'none', color: on ? T.text : T.muted, font: 'inherit', fontSize: 11.5,
      fontWeight: 600, padding: '4px 10px', borderRadius: 6, cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.4 : 1,
      boxShadow: on ? '0 1px 2px rgba(0,0,0,0.15)' : 'none',
    }}>{children}</button>
  )
}
export const chipGroup: CSSProperties = { display: 'flex', gap: 3, background: T.surface2, padding: 3, borderRadius: 8, flexWrap: 'wrap' }

export function CardHead({ title, sub, children }: { title: string; sub?: string; children?: ReactNode }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
      <span style={{ ...label, fontSize: 12.5, letterSpacing: 0.8 }}>
        {title}{sub && <span style={{ textTransform: 'none', letterSpacing: 0, fontWeight: 500, marginLeft: 8 }}>{sub}</span>}
      </span>
      {children}
    </div>
  )
}

export function Stat({ l, v, s, color, children }: { l: string; v?: ReactNode; s?: ReactNode; color?: string; children?: ReactNode }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={label}>{l}</div>
      {v != null && <div style={{ fontSize: 18, fontWeight: 700, marginTop: 3, color: color ?? T.text, fontVariantNumeric: 'tabular-nums' }}>{v}</div>}
      {children}
      {s && <div style={{ fontSize: 11.5, color: T.muted, marginTop: 2 }}>{s}</div>}
    </div>
  )
}
export const statGrid: CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 14 }

/** Hover card beside the crosshair; flips to the left of it on the right half of the chart. */
export function Tip({ x, w, top, children }: { x: number; w: number; top: number; children: ReactNode }) {
  const flip = x > w / 2
  return (
    <div style={{
      position: 'absolute', left: x, top, transform: flip ? 'translateX(calc(-100% - 14px))' : 'translateX(14px)', pointerEvents: 'none',
      background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, padding: '8px 11px', fontSize: 12, minWidth: 170,
      boxShadow: '0 6px 20px rgba(0,0,0,0.2)', display: 'grid', gap: 3, zIndex: 2,
    }}>{children}</div>
  )
}
export function TipRow({ l, v, color, bold }: { l: ReactNode; v: ReactNode; color?: string; bold?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 14, fontVariantNumeric: 'tabular-nums' }}>
      <span style={{ color: T.muted }}>{l}</span><span style={{ color: color ?? T.text, fontWeight: bold ? 700 : 400 }}>{v}</span>
    </div>
  )
}
export const legend: CSSProperties = { display: 'flex', gap: 16, fontSize: 11.5, color: T.muted, marginTop: 8, flexWrap: 'wrap' }
export const hairCursor = { touchAction: 'pan-y' as const, cursor: 'crosshair' }

/** A small callout line (the "add ₹X a month" hint, the top-up note). */
export function Callout({ tone, icon, children }: { tone: string; icon: string; children: ReactNode }) {
  return (
    <div style={{ marginTop: 12, display: 'flex', gap: 10, alignItems: 'flex-start', fontSize: 12.5, lineHeight: 1.5, padding: '9px 12px', borderRadius: 8, background: T.surface2 }}>
      <span style={{ flex: 'none', width: 18, height: 18, borderRadius: '50%', display: 'grid', placeItems: 'center', fontWeight: 700, fontSize: 11, color: '#fff', background: tone }}>{icon}</span>
      <span>{children}</span>
    </div>
  )
}

/** Goal-kind colours: large goals (corpus), small goals and recurring expenses (set-aside). */
export const KIND_COLOR = { large: '#d946ef', small: '#06b6d4', recurring: '#f97316' } as const
