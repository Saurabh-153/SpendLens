import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  addTransaction, deleteTransaction, getHoldings, getLedgerSummary, getTransactions,
  type Holding, type LedgerSummary, type Tx, type TxKind,
} from '../api'
import { T, fmt, fmtFull, pnlColor, signed } from '../theme'
import { accentStyle, btn, Card, Field, input, label, Modal, smallBtn } from './ui'

const kindColor = (): Record<TxKind, string> => ({ BUY: T.accent, SELL: T.warn, DIVIDEND: T.positive, OPENING: T.muted })
const DIRECT = ['MF', 'FD', 'PF']
const today = () => new Date().toISOString().slice(0, 10)

function Stat({ name, value, sub, color, accent }: { name: string; value: React.ReactNode; sub?: React.ReactNode; color?: string; accent?: string }) {
  return (
    <Card style={{ padding: '14px 18px', ...accentStyle(accent ?? color ?? T.accent) }}>
      <div style={label}>{name}</div>
      <div style={{ fontFamily: 'var(--font-display, inherit)', fontSize: 24, fontWeight: 700, margin: '4px 0 2px', color }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: T.muted }}>{sub}</div>}
    </Card>
  )
}

export default function Ledger() {
  const [sum, setSum] = useState<LedgerSummary | null>(null)
  const [txs, setTxs] = useState<Tx[]>([])
  const [total, setTotal] = useState(0)
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [kind, setKind] = useState('')
  const [fy, setFy] = useState('')
  const [adding, setAdding] = useState(false)
  const [dates, setDates] = useState<Record<number, string>>({})
  const [error, setError] = useState('')

  const load = useCallback(() => {
    Promise.all([getLedgerSummary(), getTransactions({ kind, fy, limit: 200 }), getHoldings()])
      .then(([s, t, h]) => { setSum(s); setTxs(t.rows); setTotal(t.total); setHoldings(h); setError('') })
      .catch(e => setError(e.message))
  }, [kind, fy])
  useEffect(load, [load])
  const run = (p: Promise<unknown>) => p.then(load).catch(e => setError(e.message))

  const cur = useMemo(() => sum?.fy.find(f => f.fy === sum.current_fy), [sum])
  const missing = sum?.xirr.holdings.filter(h => !h.covered && h.present > 0) ?? []
  const covered = sum?.xirr.holdings.filter(h => h.covered) ?? []
  if (!sum) return <div style={{ color: error ? T.negative : T.muted }}>{error || 'Loading…'}</div>
  const th: React.CSSProperties = { ...label, fontSize: 10.5, padding: '0 10px 8px', textAlign: 'right', fontWeight: 600 }
  const td: React.CSSProperties = { padding: '7px 10px', fontSize: 13, textAlign: 'right' }

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700 }}>Ledger</h2>
        <button style={btn(true)} onClick={() => setAdding(true)}>+ Add transaction</button>
      </div>
      {error && <div style={{ color: T.negative, fontSize: 12.5, marginBottom: 10 }}>{error}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 16, marginBottom: 18 }}>
        <Stat name={`Dividends ${sum.current_fy}`} value={fmtFull(cur?.dividends ?? 0)} color={T.positive} sub={`${fmtFull(sum.dividends_total)} all time`} />
        <Stat name={`Realised ${sum.current_fy}`} value={signed(cur?.realized ?? 0)} color={pnlColor(cur?.realized ?? 0)} sub={`${signed(sum.realized_total)} all time`} />
        <Stat accent="#38bdf8" name="XIRR (dated money)" value={sum.xirr.portfolio != null ? `${sum.xirr.portfolio}%` : '—'}
          sub={`${sum.xirr.covered_pct}% of the portfolio has dated flows${sum.xirr.covered_pct < 50 ? ': add opening dates below' : ''}`} />
      </div>

      {sum.fy.length > 0 && (
        <Card style={{ marginBottom: 18, overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead><tr><th style={{ ...th, textAlign: 'left' }}>Financial year</th><th style={th}>Dividends</th><th style={th}>Realised P&amp;L</th><th style={th}>Bought</th><th style={th}>Sold</th></tr></thead>
            <tbody>
              {sum.fy.map(f => (
                <tr key={f.fy} style={{ borderTop: `1px solid ${T.hairline}` }}>
                  <td style={{ ...td, textAlign: 'left', fontWeight: 600 }}>{f.fy}</td>
                  <td style={td}>{f.dividends ? fmtFull(f.dividends) : '—'}</td>
                  <td style={{ ...td, color: f.realized ? pnlColor(f.realized) : T.muted }}>{f.realized ? signed(f.realized) : '—'}</td>
                  <td style={{ ...td, color: T.muted }}>{f.bought ? fmt(f.bought) : '—'}</td>
                  <td style={{ ...td, color: T.muted }}>{f.sold ? fmt(f.sold) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(440px, 1fr))', gap: 18, alignItems: 'start', marginBottom: 18 }}>
        <Card style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '12px 16px', ...label }}>Returns by holding <span style={{ textTransform: 'none', letterSpacing: 0, fontWeight: 400 }}>· XIRR needs the date money went in</span></div>
          <div style={{ maxHeight: 420, overflowY: 'auto' }}>
            {covered.sort((a, b) => b.present - a.present).map(h => (
              <div key={h.id} style={{ display: 'flex', gap: 10, padding: '7px 16px', borderTop: `1px solid ${T.hairline}`, fontSize: 13, alignItems: 'center' }}>
                <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{h.name}</span>
                <span style={{ color: T.muted, fontSize: 11.5 }}>since {h.since}</span>
                <b style={{ width: 62, textAlign: 'right', color: h.xirr != null ? pnlColor(h.xirr) : T.muted }}>{h.xirr != null ? `${h.xirr}%` : '—'}</b>
              </div>
            ))}
            {missing.length > 0 && <div style={{ padding: '8px 16px', fontSize: 11.5, color: T.muted, borderTop: `1px solid ${T.hairline}`, background: T.surface2 }}>
              {missing.length} holdings need an opening date (when the money went in; an average date is fine)
            </div>}
            {missing.map(h => (
              <div key={h.id} style={{ display: 'flex', gap: 8, padding: '6px 16px', borderTop: `1px solid ${T.hairline}`, fontSize: 13, alignItems: 'center' }}>
                <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={h.name}>{h.name}</span>
                <span style={{ color: T.muted, fontSize: 11.5 }}>{fmt(h.invested)}</span>
                <input type="date" style={{ ...input, width: 140, padding: '4px 8px', fontSize: 12.5 }} max={today()} value={dates[h.id] ?? ''} onChange={e => setDates({ ...dates, [h.id]: e.target.value })} />
                <button style={{ ...smallBtn, opacity: dates[h.id] ? 1 : 0.4 }} disabled={!dates[h.id]}
                  onClick={() => run(addTransaction({ holding_id: h.id, tx_date: dates[h.id], kind: 'OPENING', amount: h.invested }))}>Save</button>
              </div>
            ))}
          </div>
        </Card>

        <Card style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '10px 16px' }}>
            <span style={{ ...label, flex: 1 }}>Transactions <span style={{ textTransform: 'none', letterSpacing: 0, fontWeight: 400 }}>· {total}</span></span>
            <select style={{ ...input, width: 'auto', padding: '4px 8px', fontSize: 12.5 }} value={kind} onChange={e => setKind(e.target.value)}>
              <option value="">All types</option>{['BUY', 'SELL', 'DIVIDEND', 'OPENING'].map(k => <option key={k}>{k}</option>)}
            </select>
            <select style={{ ...input, width: 'auto', padding: '4px 8px', fontSize: 12.5 }} value={fy} onChange={e => setFy(e.target.value)}>
              <option value="">All years</option>{sum.fy.map(f => <option key={f.fy}>{f.fy}</option>)}
            </select>
          </div>
          <div style={{ maxHeight: 420, overflowY: 'auto' }}>
            {txs.length === 0 && <div style={{ padding: '14px 16px', color: T.muted, fontSize: 13 }}>No transactions.</div>}
            {txs.map(t => (
              <div key={t.id} style={{ display: 'grid', gridTemplateColumns: '78px 62px minmax(0,1fr) 84px 22px', gap: 8, padding: '6px 16px', borderTop: `1px solid ${T.hairline}`, fontSize: 12.5, alignItems: 'center' }}>
                <span style={{ color: T.muted }}>{t.tx_date}</span>
                <span style={{ color: kindColor()[t.kind], fontWeight: 600, fontSize: 11 }}>{t.kind}{t.source === 'sip' ? ' · SIP' : ''}</span>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={t.note}>
                  {t.name}{t.kind !== 'DIVIDEND' && t.qty ? <span style={{ color: T.muted }}> · {+t.qty.toFixed(3)} @ {+t.price.toFixed(2)}</span> : null}
                  {t.kind === 'SELL' && <span style={{ color: pnlColor(t.realized) }}> · {signed(t.realized)}</span>}
                </span>
                <span style={{ textAlign: 'right', fontWeight: 600 }}>{t.kind === 'BUY' || t.kind === 'OPENING' ? '-' : '+'}{fmt(t.amount)}</span>
                <button title="Delete record (the holding is not changed)" onClick={() => run(deleteTransaction(t.id))}
                  style={{ background: 'none', border: 'none', color: T.muted, cursor: 'pointer', fontSize: 14, padding: 0 }}>×</button>
              </div>
            ))}
          </div>
        </Card>
      </div>
      <p style={{ color: T.muted, fontSize: 12, maxWidth: 760 }}>
        SIPs are added here automatically. Deleting a record never changes the holding. Gains use the holding's average cost, not individual lots, so this is a guide, not a tax statement.
      </p>

      {adding && <AddDialog holdings={holdings} onClose={() => setAdding(false)} onSave={t => { setAdding(false); run(addTransaction(t)) }} />}
    </div>
  )
}

function AddDialog({ holdings, onClose, onSave }: { holdings: Holding[]; onClose: () => void; onSave: (t: Parameters<typeof addTransaction>[0]) => void }) {
  const [kind, setKind] = useState<TxKind>('DIVIDEND')
  const [hid, setHid] = useState<number | ''>('')
  const [name, setName] = useState('')
  const [date, setDate] = useState(today())
  const [qty, setQty] = useState('')
  const [price, setPrice] = useState('')
  const [amount, setAmount] = useState('')
  const [fees, setFees] = useState('')
  const [apply, setApply] = useState(true)
  const [note, setNote] = useState('')
  const h = holdings.find(x => x.id === hid)
  const priced = !!h && !DIRECT.includes(h.asset_type)
  const unitMode = (kind === 'BUY' || kind === 'SELL') && priced
  const needAmount = !unitMode && kind !== 'OPENING'
  const ok = !!date && (hid !== '' || (kind === 'DIVIDEND' && name.trim())) && (unitMode ? +qty > 0 && +price > 0 : kind === 'OPENING' || +amount > 0)
  const total = unitMode ? (+qty || 0) * (+price || 0) + (kind === 'BUY' ? 1 : -1) * (+fees || 0) : +amount || 0

  return (
    <Modal title="Add transaction" onClose={onClose}>
      <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
        {(['DIVIDEND', 'BUY', 'SELL', 'OPENING'] as TxKind[]).map(k => (
          <button key={k} style={{ ...btn(kind === k), flex: 1, padding: '6px 4px', fontSize: 12 }} onClick={() => setKind(k)}>{k === 'OPENING' ? 'Opening' : k[0] + k.slice(1).toLowerCase()}</button>
        ))}
      </div>
      <Field name="Holding">
        <select style={input} value={hid} onChange={e => setHid(e.target.value ? Number(e.target.value) : '')}>
          <option value="">{kind === 'DIVIDEND' ? 'Other / sold stock (type the name)' : 'Choose…'}</option>
          {holdings.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}
        </select>
      </Field>
      {kind === 'DIVIDEND' && hid === '' && <Field name="Name"><input style={input} value={name} onChange={e => setName(e.target.value)} /></Field>}
      <Field name={kind === 'OPENING' ? 'Date the money went in' : 'Date'}><input style={input} type="date" max={today()} value={date} onChange={e => setDate(e.target.value)} /></Field>
      {unitMode && (
        <div style={{ display: 'flex', gap: 10 }}>
          <Field name="Quantity"><input style={input} type="number" value={qty} onChange={e => setQty(e.target.value)} /></Field>
          <Field name="Price"><input style={input} type="number" value={price} onChange={e => setPrice(e.target.value)} /></Field>
          <Field name="Fees"><input style={input} type="number" value={fees} onChange={e => setFees(e.target.value)} /></Field>
        </div>
      )}
      {(needAmount || kind === 'OPENING') && (
        <Field name={kind === 'OPENING' ? 'Amount (blank = current invested)' : kind === 'DIVIDEND' ? 'Net dividend received (₹)' : 'Amount (₹)'}>
          <input style={input} type="number" value={amount} onChange={e => setAmount(e.target.value)} />
        </Field>
      )}
      {(kind === 'BUY' || kind === 'SELL') && (
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12.5, marginBottom: 12, cursor: 'pointer' }}>
          <input type="checkbox" checked={apply} onChange={e => setApply(e.target.checked)} />
          Also update the holding ({kind === 'BUY' ? 'add to' : 'reduce'} quantity / value). Untick to record an old trade only.
        </label>
      )}
      <Field name="Note"><input style={input} value={note} onChange={e => setNote(e.target.value)} /></Field>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
        <span style={{ flex: 1, fontSize: 12.5, color: T.muted }}>{total > 0 ? `Total ${fmtFull(total)}` : ''}</span>
        <button style={btn()} onClick={onClose}>Cancel</button>
        <button style={{ ...btn(true), opacity: ok ? 1 : 0.5 }} disabled={!ok}
          onClick={() => onSave({ holding_id: hid === '' ? null : hid, name, tx_date: date, kind, qty: +qty || 0, price: +price || 0, amount: +amount || 0, fees: +fees || 0, note, apply: apply ? 1 : 0 })}>Save</button>
      </div>
    </Modal>
  )
}
