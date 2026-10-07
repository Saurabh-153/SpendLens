import { useEffect, type CSSProperties, type ReactNode } from 'react'
import { T } from '../theme'

export const card: CSSProperties = { background: T.surface, borderRadius: 'var(--radius, 10px)', boxShadow: 'inset 0 1px 0 var(--ov-4), 0 1px 2px rgba(0,0,0,0.25)' }
export const label: CSSProperties = { fontSize: 11, fontWeight: 600, letterSpacing: 0.6, textTransform: 'uppercase', color: T.muted }
export const input: CSSProperties = {
  background: T.surface2, border: `1px solid ${T.border}`, borderRadius: 6, color: T.text,
  padding: '8px 10px', fontSize: 13, outline: 'none', fontFamily: 'inherit', width: '100%',
}
export const btn = (primary = false): CSSProperties => ({
  background: primary ? T.accent : T.surface2, color: primary ? '#fff' : T.text,
  border: `1px solid ${primary ? T.accent : T.border}`, borderRadius: 6, padding: '8px 14px',
  fontSize: 13, fontWeight: 600, cursor: 'pointer',
})

/** Compact buttons for list rows in Admin tools. */
export const smallBtn: CSSProperties = { ...btn(), padding: '4px 10px', fontSize: 12 }
export const dangerBtn: CSSProperties = { ...smallBtn, color: T.danger, borderColor: T.dangerBorder }

/** Page title, optional primary action on the right and a one-line hint: the same on every Admin tool. */
export function AdminHeader({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, minHeight: 34 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700 }}>{title}</h2>
        {action}
      </div>
      {hint && <p style={{ color: T.muted, fontSize: 12.5, marginTop: 4, maxWidth: 720, lineHeight: 1.5 }}>{hint}</p>}
      <div style={{ height: 2, width: 44, marginTop: 12, borderRadius: 1, background: `linear-gradient(90deg, ${T.accent}, ${T.accent2})` }} />
    </div>
  )
}

/** A KPI tile's colour treatment: a coloured top edge and a faint glow of the same colour. */
export const accentStyle = (c: string): CSSProperties => ({ borderTop: `3px solid ${c}`, background: `linear-gradient(180deg, ${c}1f, ${T.surface} 62%)` })

export function Card({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return <div style={{ ...card, padding: 18, ...style }}>{children}</div>
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
      <div onClick={e => e.stopPropagation()} style={{ ...card, padding: 22, width: 440, maxWidth: '90vw', maxHeight: '90vh', overflowY: 'auto' }}>
        <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>{title}</div>
        {children}
      </div>
    </div>
  )
}

export function Field({ name, children }: { name: string; children: ReactNode }) {
  return (
    <label style={{ display: 'block', marginBottom: 12 }}>
      <div style={{ ...label, marginBottom: 5 }}>{name}</div>
      {children}
    </label>
  )
}
