import { useState, useSyncExternalStore } from 'react'
import Admin from './components/Admin'
import Cards from './components/Cards'
import ChangePassword from './components/ChangePassword'
import DatabaseBanner from './components/DatabaseBanner'
import Expense from './components/Expense'
import Holdings from './components/Holdings'
import HeroPeek from './components/HeroPeek'
import Ledger from './components/Ledger'
import MfAnalysis from './components/MfAnalysis'
import { useAuth } from './auth'
import LockedModule from './components/LockedModule'
import Login from './components/Login'
import type { ModuleId } from './api'
import { T } from './theme'
import { subscribeTheme, themeVersion } from './themeStore'

type Page = 'expense' | 'holdings' | 'mf' | 'ledger' | 'cards' | 'admin'
// `module`: the module a page needs.
const PAGES: { id: Page; label: string; module: ModuleId }[] = [
  { id: 'expense', label: 'Expense', module: 'expense' },
  { id: 'holdings', label: 'Holdings', module: 'holdings' },
  { id: 'mf', label: 'MF Analysis', module: 'holdings' },
  { id: 'ledger', label: 'Ledger', module: 'ledger' },
  { id: 'cards', label: 'Cards', module: 'cards' },
]

/** The Dashboard page is gone: its Spending view is part of Expense, and Wealth and Asset Mix are Holdings tabs.
 *  A saved link to any of them lands in the new place. */
function moveOldTabs() {
  const u = new URL(location.href), tab = u.searchParams.get('tab')
  if (u.searchParams.get('page') !== 'dashboard') return
  if (tab === 'portfolio' || tab === 'exposure') {
    u.searchParams.set('page', 'holdings')
    u.searchParams.set('tab', tab === 'portfolio' ? 'outlook' : 'allocation')
  } else {
    u.searchParams.set('page', 'expense')
    u.searchParams.delete('tab')
  }
  history.replaceState(null, '', u)
}

function initialPage(): Page {
  moveOldTabs()
  const p = new URLSearchParams(location.search).get('page')
  return p === 'holdings' || p === 'mf' || p === 'ledger' || p === 'cards' || p === 'admin' ? p : 'expense'
}

export default function App() {
  const { me, loading } = useAuth()
  if (loading) return null
  if (!me) return <Login />
  return <Shell />
}

function Shell() {
  const { me, can, logout } = useAuth()
  const [page, setPage] = useState<Page>(() => {
    const p = initialPage()
    if (new URLSearchParams(location.search).get('page')) return p
    return PAGES.find(x => can(x.module))?.id ?? 'admin'   // no page in the URL: open the first module this person has
  })
  const [pwOpen, setPwOpen] = useState(false)
  const themeKey = useSyncExternalStore(subscribeTheme, themeVersion)   // remount on a theme change so accent colours refresh
  const go = (p: Page, tool?: string, tab?: string) => {
    const url = new URL(location.href)
    url.searchParams.set('page', p)
    for (const [k, v] of [['tool', tool], ['tab', tab]] as const) { if (v) url.searchParams.set(k, v); else url.searchParams.delete(k) }
    history.replaceState(null, '', url)
    setPage(p)
  }
  const needed = PAGES.find(p => p.id === page)   // undefined for the admin page
  return (
    <div key={themeKey} style={{ minHeight: '100vh' }}>
      <nav style={{ position: 'sticky', top: 0, zIndex: 50, height: 48, display: 'flex', alignItems: 'center', gap: 6, padding: '0 20px', background: 'var(--nav-bg, var(--surface))', backdropFilter: 'var(--nav-blur, none)', WebkitBackdropFilter: 'var(--nav-blur, none)', borderBottom: `1px solid ${T.hairline}` }}>
        <span className="brand" style={{ fontWeight: 700, fontSize: 15, marginRight: 22 }}>💰 SpendLens</span>
        {PAGES.map(p => (
          <button key={p.id} onClick={() => go(p.id)} style={{
            height: 48, padding: '0 14px', background: 'none', border: 'none', cursor: 'pointer', fontSize: 13.5, fontWeight: 'var(--display-weight, 500)' as unknown as number, fontFamily: 'var(--font-display, inherit)',
            color: page === p.id ? T.text : T.muted, borderBottom: `2px solid ${page === p.id ? T.accent : 'transparent'}`,
          }}>{!can(p.module) && <span aria-label="locked" style={{ marginRight: 5, fontSize: 11 }}>🔒</span>}{p.label}</button>
        ))}
        <div style={{ flex: 1 }} />
        <span style={{ color: T.muted, fontSize: 12, marginRight: 4 }} title={me?.email}>{me?.name || me?.email}</span>
        <button onClick={() => setPwOpen(true)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.muted, fontSize: 12.5 }}>Change password</button>
        <button onClick={() => logout()} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.muted, fontSize: 12.5, marginRight: 8 }}>Sign out</button>
<button className="gear-btn" onClick={() => go('admin')} title="Admin & settings" aria-label="Admin" style={{
          width: 40, height: 40, borderRadius: 10, border: 'none', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          color: page === 'admin' ? T.accent : T.muted, background: page === 'admin' ? T.surface2 : 'transparent',
        }}>
          {!!me?.pending_requests && <span title={`${me.pending_requests} access request(s) waiting`} style={{ position: 'absolute', marginLeft: 18, marginTop: -16, minWidth: 16, height: 16, padding: '0 4px', borderRadius: 8, background: T.warn, color: '#000', fontSize: 10.5, fontWeight: 700, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>{me.pending_requests}</span>}
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="3.2" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </button>
      </nav>
      <DatabaseBanner />
      {needed && !can(needed.module) ? <LockedModule module={needed.module} /> : <>
        {page === 'expense' && <Expense onNavigate={go} />}
        {page === 'holdings' && <Holdings />}
        {page === 'mf' && <MfAnalysis />}
        {page === 'ledger' && <Ledger />}
        {page === 'cards' && <Cards />}
        {page === 'admin' && <Admin />}
      </>}
      <HeroPeek />
      {pwOpen && <ChangePassword onClose={() => setPwOpen(false)} />}
    </div>
  )
}
