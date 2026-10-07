import { useState } from 'react'
import { getThemePref, resolveTheme, setThemePref, THEMES, type ThemeDef, type ThemePref } from '../../themeStore'
import { T } from '../../theme'
import { AdminHeader, Card } from '../ui'

// Each preview is painted from the theme's own palette (not the live variables), so it shows what you would get.
function Preview({ t }: { t: ThemeDef }) {
  const p = t.palette
  return (
    <div style={{ background: p.bgFull ?? p.bg, padding: 8, height: 82, display: 'flex', flexDirection: 'column', gap: 5, fontFamily: p.font }}>
      <div style={{ height: 9, borderRadius: 2, background: p.surface, border: `1px solid ${p.border}`, display: 'flex', gap: 4, padding: '1px 3px' }}>
        <span style={{ width: 16, background: t.accent, borderRadius: 1 }} /><span style={{ width: 16, background: p.muted, opacity: 0.5, borderRadius: 1 }} />
      </div>
      <div style={{ flex: 1, display: 'flex', gap: 5 }}>
        {[t.accent, t.accent2, '#f59e0b'].map(c => (
          <div key={c} style={{ flex: 1, background: p.surface, border: `1px solid ${p.border}`, borderTop: `2px solid ${c}`, borderRadius: 3, padding: 3 }}>
            <div style={{ height: 3, width: '60%', background: p.muted, opacity: 0.6, borderRadius: 1 }} />
            <div style={{ height: 5, width: '80%', background: p.text, borderRadius: 1, marginTop: 4 }} />
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Appearance() {
  const [pref, setPref] = useState<ThemePref>(getThemePref)
  const pick = (p: ThemePref) => { setThemePref(p); setPref(p) }
  const light = THEMES[0], dark = THEMES[1]
  const options: { id: ThemePref; def?: ThemeDef; title: string; sub: string }[] = [
    { id: 'auto', title: 'Auto', sub: 'Follows your laptop or phone setting' },
    ...THEMES.map(t => ({ id: t.id as ThemePref, def: t, title: t.label, sub: t.sub })),
  ]
  return (
    <>
      <AdminHeader title="Appearance" hint="Choose how SpendLens looks. The choice applies to every page and is remembered on this device. Auto switches between Light and Dark with your system." />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))', gap: 16 }}>
        {options.map(o => {
          const on = pref === o.id
          return (
            <button key={o.id} onClick={() => pick(o.id)} aria-pressed={on}
              style={{ padding: 0, background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', color: T.text, font: 'inherit', display: 'block', height: '100%' }}>
              <Card style={{ padding: 0, overflow: 'hidden', height: '100%', outline: on ? `2px solid ${T.accent}` : `1px solid ${T.border}`, outlineOffset: -1 }}>
                {o.def ? <Preview t={o.def} /> : (
                  <div style={{ position: 'relative' }}>
                    <Preview t={light} />
                    <div style={{ position: 'absolute', inset: 0, clipPath: 'inset(0 0 0 50%)' }}><Preview t={dark} /></div>
                  </div>
                )}
                <div style={{ padding: '10px 14px' }}>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{on ? '● ' : '○ '}{o.title}{o.id === 'auto' && on ? ` (now ${resolveTheme().label})` : ''}</div>
                  <div style={{ fontSize: 12, color: T.muted, marginTop: 2 }}>{o.sub}</div>
                </div>
              </Card>
            </button>
          )
        })}
      </div>
    </>
  )
}
