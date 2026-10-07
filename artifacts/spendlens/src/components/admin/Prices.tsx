import { useCallback, useEffect, useState } from 'react'
import {
  autoMapPrices, getPricesStatus, refreshPrices, setPriceCfg, suggestPrice, unitsFromValue,
  type PriceOption, type PriceRow, type PricesStatus,
} from '../../api'
import { T, fmt } from '../../theme'
import { AdminHeader, btn, Card, input, label, Modal, smallBtn } from '../ui'

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : 'never')
const COLS = 'minmax(0,1fr) 120px 96px 120px 44px 56px'

export default function PricesTool() {
  const [st, setSt] = useState<PricesStatus | null>(null)
  const [msg, setMsg] = useState<{ text: string; error?: boolean } | null>(null)
  const [busy, setBusy] = useState(false)
  const [find, setFind] = useState<{ row: PriceRow; options: PriceOption[] } | null>(null)

  const load = useCallback(async () => {
    try { setSt(await getPricesStatus()) } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
  }, [])
  useEffect(() => { load() }, [load])

  const run = async (p: Promise<unknown>, ok?: (r: never) => string) => {
    setBusy(true)
    try { const r = await p; setMsg(ok ? { text: ok(r as never) } : null); await load() } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
    setBusy(false)
  }

  if (!st) return <div style={{ color: msg?.error ? T.negative : T.muted }}>{msg?.text ?? 'Loading…'}</div>
  const eq = st.holdings.filter(h => h.asset_type === 'EQ'), mf = st.holdings.filter(h => h.asset_type === 'MF'), gold = st.holdings.filter(h => h.asset_type === 'GOLD')
  const autoCount = st.holdings.filter(h => h.auto_price).length

  const openFind = async (row: PriceRow) => {
    try { setFind({ row, options: (await suggestPrice(row.id)).options }) } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
  }

  return (
    <div>
      <AdminHeader title="Prices" hint="Equity and gold ETF closing prices (Yahoo Finance, NSE) and mutual fund NAVs (AMFI) are fetched every weekday evening and when you open the app after a missed day."
        action={
          <div style={{ display: 'flex', gap: 8 }}>
            <button style={btn()} disabled={busy} onClick={() => run(autoMapPrices(), (r: { mapped: string[]; skipped: string[] }) => `${r.mapped.length} mapped${r.skipped.length ? `, ${r.skipped.length} need a manual symbol` : ''}`)}>Auto-map</button>
            <button style={btn(true)} disabled={busy} onClick={() => run(refreshPrices(), (r: { updated: number; failed: number }) => `${r.updated} prices updated${r.failed ? `, ${r.failed} failed` : ''}`)}>{busy ? 'Working…' : 'Refresh now'}</button>
          </div>
        } />
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 12.5, color: T.muted, marginBottom: 14 }}>
        <span>Last update <b style={{ color: T.text }}>{when(st.last_ok)}</b></span>
        <span><b style={{ color: T.text }}>{autoCount}</b> of {st.holdings.length} on auto</span>
        {st.stale && <span style={{ color: T.warn }}>an update is due</span>}
      </div>
      {msg && <div style={{ fontSize: 12.5, marginBottom: 12, color: msg.error ? T.negative : T.positive }}>{msg.text}</div>}

      <Card style={{ padding: 0, overflow: 'hidden', marginBottom: 18 }}>
        <Head title="Equity" cols={['NSE symbol', '', 'Close', 'Auto']} />
        {eq.map(h => <Row key={`${h.id}:${h.ticker}:${h.units}:${h.auto_price}`} h={h} onFind={() => openFind(h)} run={run} />)}
      </Card>
      {gold.length > 0 && (
        <Card style={{ padding: 0, overflow: 'hidden', marginBottom: 18 }}>
          <Head title="Gold" cols={['NSE symbol', '', 'Price', 'Auto']} />
          {gold.map(h => <Row key={`${h.id}:${h.ticker}:${h.units}:${h.auto_price}`} h={h} onFind={() => openFind(h)} run={run} />)}
          <div style={{ padding: '8px 16px', fontSize: 11.5, color: T.muted, borderTop: `1px solid ${T.hairline}` }}>
            Gold ETFs (e.g. GOLDIETF) update from Yahoo Finance. Sovereign Gold Bonds are not on Yahoo, so their symbol is kept for reference and their price stays manual – leave Auto off.
          </div>
        </Card>
      )}
      <Card style={{ padding: 0, overflow: 'hidden', marginBottom: 18 }}>
        <Head title="Mutual funds" cols={['AMFI code', 'Units', 'NAV', 'Auto']} />
        {mf.map(h => <Row key={`${h.id}:${h.scheme_code}:${h.units}:${h.auto_price}`} h={h} onFind={() => openFind(h)} run={run} />)}
        <div style={{ padding: '8px 16px', fontSize: 11.5, color: T.muted, borderTop: `1px solid ${T.hairline}` }}>
          Units are worked out once from today's value ÷ NAV (button "= value"), then the value follows the NAV. SIPs on these funds buy units at the day's NAV.
        </div>
      </Card>

      {st.runs.length > 0 && (
        <>
          <div style={{ ...label, marginBottom: 8 }}>Recent updates</div>
          <Card style={{ padding: 0, overflow: 'hidden' }}>
            {st.runs.slice(0, 5).map((r, i) => (
              <div key={r.id} style={{ display: 'flex', gap: 12, padding: '8px 16px', fontSize: 12.5, borderTop: i ? `1px solid ${T.hairline}` : undefined }}>
                <span style={{ width: 120, color: T.muted }}>{when(r.ran_at)}</span>
                <span style={{ color: r.ok ? T.positive : T.negative, width: 90 }}>{r.updated} updated</span>
                <span style={{ flex: 1, minWidth: 0, color: T.muted, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.failed ? `${r.failed} failed: ${r.detail}` : ''}</span>
              </div>
            ))}
          </Card>
        </>
      )}

      {find && (
        <Modal title={`Find: ${find.row.name}`} onClose={() => setFind(null)}>
          {find.options.length === 0 && <div style={{ color: T.muted, fontSize: 13 }}>No match found. Type the code by hand.</div>}
          {find.options.map(o => (
            <button key={o.code ?? o.ticker} style={{ ...btn(), display: 'block', width: '100%', textAlign: 'left', marginBottom: 6 }}
              onClick={() => {
                const r = find.row
                setFind(null)
                run(setPriceCfg(r.id, { ticker: o.ticker ?? r.ticker, scheme_code: o.code ?? r.scheme_code, units: r.units, auto_price: 0 }))
              }}>
              <b>{o.ticker ?? o.code}</b> <span style={{ color: T.muted }}>· {o.name}{o.plan ? ` · ${o.plan}` : ''}{o.nav ? ` · NAV ${o.nav}` : ''}</span>
            </button>
          ))}
        </Modal>
      )}
    </div>
  )
}

function Head({ title, cols }: { title: string; cols: string[] }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 10, padding: '10px 16px', background: T.surface2, alignItems: 'center' }}>
      <span style={{ ...label, color: T.text }}>{title}</span>
      {cols.map((c, i) => <span key={i} style={{ ...label, fontSize: 10.5, textAlign: i >= 2 ? 'right' : 'left' }}>{c}</span>)}
      <span />
    </div>
  )
}

function Row({ h, onFind, run }: { h: PriceRow; onFind: () => void; run: (p: Promise<unknown>, ok?: (r: never) => string) => Promise<void> }) {
  const mf = h.asset_type === 'MF'
  const [code, setCode] = useState(mf ? h.scheme_code : h.ticker)
  const [units, setUnits] = useState(h.units ? String(h.units) : '')
  const u = parseFloat(units) || 0
  const dirty = code !== (mf ? h.scheme_code : h.ticker) || u !== h.units
  const cfg = (auto: number) => ({ ticker: mf ? '' : code, scheme_code: mf ? code : '', units: u, auto_price: auto })
  const small = { ...input, padding: '5px 8px', fontSize: 12.5 }
  return (
    <div style={{ borderTop: `1px solid ${T.hairline}`, padding: '7px 16px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 10, alignItems: 'center', fontSize: 13 }}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={h.name}>{h.name}</span>
        <input style={small} value={code} placeholder={mf ? 'scheme code' : 'e.g. HDFCBANK'} onChange={e => setCode(e.target.value)} />
        {mf
          ? <input style={{ ...small, textAlign: 'right' }} type="number" value={units} placeholder="units" onChange={e => setUnits(e.target.value)} />
          : <button style={smallBtn} onClick={onFind}>Find</button>}
        <span style={{ textAlign: 'right', fontSize: 12.5 }}>
          {(mf ? h.nav : h.cmp) ? <>{mf ? h.nav : h.cmp}<span style={{ display: 'block', fontSize: 10.5, color: T.muted }}>{h.price_date || ''}</span></> : <span style={{ color: T.muted }}>—</span>}
        </span>
        <input type="checkbox" style={{ justifySelf: 'end' }} checked={!!h.auto_price} title="Update this holding automatically"
          onChange={e => run(setPriceCfg(h.id, cfg(e.target.checked ? 1 : 0)))} />
        <span style={{ textAlign: 'right' }}>
          {dirty && <button style={{ ...smallBtn, background: T.accent, borderColor: T.accent, color: '#fff' }} onClick={() => run(setPriceCfg(h.id, cfg(h.auto_price)))}>Save</button>}
        </span>
      </div>
      {(h.price_note || (mf && !!code && !u)) && (
        <div style={{ fontSize: 11.5, marginTop: 3, color: h.price_note ? T.negative : T.muted, display: 'flex', gap: 8, alignItems: 'center' }}>
          {h.price_note || 'No units yet.'}
          {mf && !!code && <button style={smallBtn} onClick={() => run(unitsFromValue(h.id))}>= value {fmt(h.present)} → units</button>}
        </div>
      )}
      {mf && !!code && !!u && !h.price_note && (
        <div style={{ fontSize: 11.5, marginTop: 3, color: T.muted }}>{fmt(h.present)} · {h.units} units</div>
      )}
    </div>
  )
}
