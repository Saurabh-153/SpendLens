import { useEffect, useRef, useState, type FormEvent } from 'react'
import { HEROES, HeroArt, getEnabledHeroes, type Hero } from '../heroes'
import { T } from '../theme'

const H = 190   // height of a standing hero, in px

interface Msg { from: 'hero' | 'me'; text: string }

/** The chat window that opens when you click a hero. There is no chatbot behind it yet, so replies are one-liners. */
function ChatBox({ hero, onClose }: { hero: Hero; onClose: () => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([{ from: 'hero', text: `${hero.quips[0]} Ask me anything about your spending.` }])
  const [text, setText] = useState('')
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }) }, [msgs])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const send = (e: FormEvent) => {
    e.preventDefault()
    const t = text.trim()
    if (!t) return
    setText('')
    setMsgs(m => [...m, { from: 'me', text: t }])
    window.setTimeout(() => setMsgs(m => [...m, { from: 'hero', text: hero.quips[Math.floor(Math.random() * hero.quips.length)] }]), 600)
  }

  return (
    <div role="dialog" aria-label={`Chat with ${hero.name}`} style={{
      position: 'fixed', right: 16, bottom: 16, zIndex: 60, width: 'min(350px, calc(100vw - 32px))', height: 'min(460px, calc(100vh - 90px))',
      display: 'flex', flexDirection: 'column', background: T.surface, color: T.text, border: `1px solid ${T.border}`,
      borderRadius: 'var(--radius, 14px)', boxShadow: '0 16px 48px rgba(0,0,0,.45)', overflow: 'hidden',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', background: T.surface2, borderBottom: `1px solid ${T.hairline}` }}>
        <div style={{ width: 40, height: 40, borderRadius: '50%', overflow: 'hidden', background: T.surface, border: `1px solid ${T.border}`, flexShrink: 0 }}>
          <div style={{ marginLeft: -28, marginTop: 0 }}><HeroArt key={hero.id} hero={hero} size={120} /></div>
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>{hero.name}</div>
          <div style={{ fontSize: 11, color: T.muted }}>{hero.universe} · {hero.pose}</div>
        </div>
        <button onClick={onClose} aria-label="Close chat" title="Close (Esc)" style={{
          width: 30, height: 30, borderRadius: 8, border: 'none', cursor: 'pointer', background: 'transparent', color: T.muted, fontSize: 20, lineHeight: 1,
        }}>×</button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {msgs.map((m, i) => (
          <div key={i} style={{
            alignSelf: m.from === 'me' ? 'flex-end' : 'flex-start', maxWidth: '82%', padding: '8px 12px', fontSize: 13, lineHeight: 1.4,
            borderRadius: 14, borderBottomRightRadius: m.from === 'me' ? 4 : 14, borderBottomLeftRadius: m.from === 'hero' ? 4 : 14,
            background: m.from === 'me' ? T.accent : T.surface2, color: m.from === 'me' ? '#fff' : T.text,
          }}>{m.text}</div>
        ))}
        <div ref={end} />
      </div>
      <div style={{ padding: '0 14px 6px', fontSize: 10.5, color: T.muted }}>Demo chat: no real answers yet, just one-liners.</div>
      <form onSubmit={send} style={{ display: 'flex', gap: 8, padding: '4px 12px 12px' }}>
        <input autoFocus value={text} onChange={e => setText(e.target.value)} placeholder={`Message ${hero.name}…`} style={{
          flex: 1, minWidth: 0, background: T.surface2, border: `1px solid ${T.border}`, borderRadius: 20, color: T.text, padding: '9px 14px', fontSize: 13, outline: 'none', fontFamily: 'inherit',
        }} />
        <button type="submit" disabled={!text.trim()} style={{
          border: 'none', borderRadius: 20, padding: '0 16px', background: T.accent, color: '#fff', fontWeight: 600, fontSize: 13, cursor: 'pointer', opacity: text.trim() ? 1 : 0.5,
        }}>Send</button>
      </form>
    </div>
  )
}

/**
 * Point at the bottom-right corner (or tap it): a hero jumps up from below the screen and strikes their pose.
 * Self-contained, and mounted once in App.tsx: the corner is earmarked for a chatbot later, so removing this one
 * mount (or moving the `right` / `bottom` below) frees the spot.
 */
export default function HeroPeek() {
  const [hero, setHero] = useState<Hero | null>(null)
  const [quip, setQuip] = useState('')
  const [open, setOpen] = useState(false)
  const [chat, setChat] = useState(false)   // the chat window opened by clicking the hero
  const [n, setN] = useState(0)   // bumped on every pick so the jump animation replays
  const last = useRef('')
  const timer = useRef<number | undefined>(undefined)

  const pick = (id?: string) => {
    const on = HEROES.filter(h => getEnabledHeroes().includes(h.id))
    const pool = id ? HEROES.filter(h => h.id === id) : on.length > 1 ? on.filter(h => h.id !== last.current) : on
    if (pool.length === 0) return false
    const h = pool[Math.floor(Math.random() * pool.length)]
    last.current = h.id
    setHero(h); setQuip(h.quips[Math.floor(Math.random() * h.quips.length)]); setN(x => x + 1)
    return true
  }
  const show = (id?: string) => { window.clearTimeout(timer.current); if (pick(id)) setOpen(true) }
  const hide = (delay = 450) => { window.clearTimeout(timer.current); timer.current = window.setTimeout(() => setOpen(false), delay) }

  useEffect(() => {
    const onPreview = (e: Event) => { show((e as CustomEvent<string>).detail); hide(4200) }
    window.addEventListener('spendlens:hero', onPreview)
    return () => { window.removeEventListener('spendlens:hero', onPreview); window.clearTimeout(timer.current) }
  }, [])

  return (
    <>
    {chat && hero && <ChatBox hero={hero} onClose={() => { setChat(false); setOpen(false) }} />}
    {!chat && (
    <div onMouseEnter={() => { if (!open) show() }} onMouseLeave={() => hide()} onClick={() => { if (open && hero) { window.clearTimeout(timer.current); setChat(true) } else show() }}
      style={{ position: 'fixed', right: 0, bottom: 0, width: 150, height: 70, zIndex: 40 }}>
      {hero && (
        <div key={n}>
          <div className={open ? 'hero-jump' : 'hero-leave'} style={{
            position: 'absolute', right: 8, bottom: 0, width: Math.round(H * 0.8), height: H, cursor: 'pointer',
            transformOrigin: 'bottom center', filter: 'drop-shadow(0 6px 12px rgba(0,0,0,.5))', pointerEvents: open ? 'auto' : 'none',
          }}>
            <HeroArt key={hero.id} hero={hero} size={H} />
          </div>
          <div style={{
            position: 'absolute', right: Math.round(H * 0.8) + 14, bottom: 96, width: 'max-content', maxWidth: 230, padding: '9px 12px', borderRadius: 12,
            background: T.surface, color: T.text, border: `1px solid ${T.border}`, fontSize: 12.5, lineHeight: 1.4, fontWeight: 500,
            boxShadow: '0 6px 20px rgba(0,0,0,.35)', opacity: open ? 1 : 0, transform: open ? 'none' : 'translateY(8px)',
            transition: 'opacity .2s ease .55s, transform .25s ease .55s', pointerEvents: 'none',
          }}>
            <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: 0.6, textTransform: 'uppercase', color: T.accent, marginBottom: 2 }}>{hero.name} · {hero.pose}</div>
            {quip}
          </div>
        </div>
      )}
    </div>
    )}
    </>
  )
}
