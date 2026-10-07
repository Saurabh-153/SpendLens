import { useState, useSyncExternalStore } from 'react'
import Admin from './components/Admin'
import Cards from './components/Cards'
import Dashboard from './components/Dashboard'
import Expense from './components/Expense'
import Holdings from './components/Holdings'
import HeroPeek from './components/HeroPeek'
import Ledger from './components/Ledger'
import { T } from './theme'
import { subscribeTheme, themeVersion } from './themeStore'

type Page = 'expense' | 'holdings' | 'ledger' | 'cards' | 'dashboard' | 'admin'
const PAGES: { id: Page; label: string }[] = [
  { id: 'expense', label: 'Expense' },
  { id: 'holdings', label: 'Holdings' },
  { id: 'ledger', label: 'Ledger' },
  { id: 'cards', label: 'Cards' },
  { id: 'dashboard', label: 'Dashboard' },
]

function initialPage(): Page {
  const p = new URLSearchParams(location.search).get('page')
  return p === 'holdings' || p === 'ledger' || p === 'cards' || p === 'dashboard' || p === 'admin' ? p : 'expense'
}

export default function App() {
  const [page, setPage] = useState<Page>(initialPage)
  const themeKey = useSyncExternalStore(subscribeTheme, themeVersion)   // remount on a theme change so accent colours refresh
  const go = (p: Page, tool?: string, tab?: string) => {
    const url = new URL(location.href)
    url.searchParams.set('page', p)
    for (const [k, v] of [['tool', tool], ['tab', tab]] as const) { if (v) url.searchParams.set(k, v); else url.searchParams.delete(k) }
    history.replaceState(null, '', url)
    setPage(p)
  }
  return (
    <div key={themeKey} style={{ minHeight: '100vh' }}>
      <nav style={{ position: 'sticky', top: 0, zIndex: 50, height: 48, display: 'flex', alignItems: 'center', gap: 6, padding: '0 20px', background: 'var(--nav-bg, var(--surface))', backdropFilter: 'var(--nav-blur, none)', WebkitBackdropFilter: 'var(--nav-blur, none)', borderBottom: `1px solid ${T.hairline}` }}>
        <span className="brand" style={{ fontWeight: 700, fontSize: 15, marginRight: 22 }}>💰 SpendLens</span>
        {PAGES.map(p => (
          <button key={p.id} onClick={() => go(p.id)} style={{
            height: 48, padding: '0 14px', background: 'none', border: 'none', cursor: 'pointer', fontSize: 13.5, fontWeight: 'var(--display-weight, 500)' as unknown as number, fontFamily: 'var(--font-display, inherit)',
            color: page === p.id ? T.text : T.muted, borderBottom: `2px solid ${page === p.id ? T.accent : 'transparent'}`,
          }}>{p.label}</button>
        ))}
        <div style={{ flex: 1 }} />
<button className="gear-btn" onClick={() => go('admin')} title="Admin & settings" aria-label="Admin" style={{
          width: 40, height: 40, borderRadius: 10, border: 'none', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          color: page === 'admin' ? T.accent : T.muted, background: page === 'admin' ? T.surface2 : 'transparent',
        }}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="3.2" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </button>
      </nav>
      {page === 'expense' && <Expense onNavigate={go} />}
      {page === 'holdings' && <Holdings />}
      {page === 'ledger' && <Ledger />}
      {page === 'cards' && <Cards />}
      {page === 'dashboard' && <Dashboard />}
      {page === 'admin' && <Admin />}
      <HeroPeek />
    </div>
  )
}
