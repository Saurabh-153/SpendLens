import { useState } from 'react'
import { HEROES, HeroArt, getEnabledHeroes, previewHero, setEnabledHeroes } from '../../heroes'
import { T } from '../../theme'
import { AdminHeader, Card, smallBtn } from '../ui'

export default function Heroes() {
  const [on, setOn] = useState<string[]>(getEnabledHeroes)
  const save = (ids: string[]) => { setOn(ids); setEnabledHeroes(ids) }
  const toggle = (id: string) => save(on.includes(id) ? on.filter(x => x !== id) : [...on, id])
  return (
    <>
      <AdminHeader title="Heroes" hint="Point at the bottom-right corner of any page and one of the heroes you've switched on jumps up, strikes a pose and says a word about your budget. Tap the corner on a phone. Saved on this device. To use your own picture for a hero, save a transparent PNG as artifacts/spendlens/public/heroes/<name>.png (ironman, hulk, superman, batman, wonderwoman) and rebuild."
        action={<div style={{ display: 'flex', gap: 8 }}>
          <button style={smallBtn} onClick={() => save(HEROES.map(h => h.id))}>All on</button>
          <button style={smallBtn} onClick={() => save([])}>All off</button>
        </div>} />
      <Card style={{ padding: 0, overflow: 'hidden' }}>
        {HEROES.map((h, i) => {
          const enabled = on.includes(h.id)
          return (
            <div key={h.id} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '12px 18px', borderTop: i ? `1px solid ${T.hairline}` : 'none' }}>
              <div style={{ width: 58, height: 72, flexShrink: 0, display: 'flex', justifyContent: 'center', alignItems: 'flex-end', opacity: enabled ? 1 : 0.35, filter: enabled ? 'none' : 'grayscale(1)' }}><HeroArt hero={h} size={72} /></div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{h.name} <span style={{ fontSize: 10.5, fontWeight: 600, color: T.muted, border: `1px solid ${T.border}`, borderRadius: 8, padding: '1px 7px', marginLeft: 6 }}>{h.universe}</span> <span style={{ fontSize: 11.5, color: T.muted, marginLeft: 6 }}>{h.pose}</span></div>
                <div style={{ fontSize: 12, color: T.muted, marginTop: 3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>“{h.quips[0]}”</div>
              </div>
              <button style={smallBtn} disabled={!enabled} onClick={() => previewHero(h.id)}>Show me</button>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, cursor: 'pointer', width: 74 }}>
                <input type="checkbox" checked={enabled} onChange={() => toggle(h.id)} style={{ accentColor: T.accent, width: 16, height: 16 }} />
                {enabled ? 'On' : 'Off'}
              </label>
            </div>
          )
        })}
      </Card>
    </>
  )
}
