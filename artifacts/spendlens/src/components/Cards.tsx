import { useCallback, useEffect, useRef, useState } from 'react'
import {
  deleteCardRule, getCardDashboard, getCardParsers, getCardRules, getCards, saveCardSettings, setCardMerchantRule,
  uploadCardStatements,
  type Card as CardRow, type CardDashboard, type CardImportFile, type CardMerchantRule, type CardParsers,
} from '../api'
import { T, fmt, fmtFull } from '../theme'
import CardsOverviewPage from './CardsOverview'
import PointsPanel from './PointsPanel'
import RubyxPanel from './RubyxPanel'
import CardPerks from './CardPerks'
import { Card, Field, Modal, btn, input, label, smallBtn } from './ui'
import { cardColor, CardChip } from '../cardColors'

/** One fixed colour per reward class, shared by every card. Grey for "earns nothing" is the meaning,
 *  not a leftover. The legend and table labels carry the identity, never colour alone. */
const CLS_COLOR: Record<string, string> = {
  online: '#3ecf8e', amazon: '#3ecf8e', partner: '#38bdf8', offline: '#f5b942', other: '#f5b942',
  excluded: '#8792ab', mixed: '#6c63ff',
}
const GAP = 2 // surface-coloured gap between adjacent fills

const pct1 = (n: number) => `${n.toFixed(1)}%`
const monthLabel = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { month: 'short', year: '2-digit' })
const dayLabel = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })
const shortDay = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
const clsColor = (c: string) => CLS_COLOR[c] ?? T.muted

const title = (t: string, right?: string) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14 }}>
    <span style={{ ...label, fontSize: 12.5, letterSpacing: 0.8 }}>{t}</span>
    {right && <span style={{ ...label, fontSize: 10.5, textTransform: 'none' }}>{right}</span>}
  </div>
)
const swatch = (c: string) => (
  <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: c, marginRight: 7 }} />
)
const th = { color: T.muted, fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 0.6 } as const

function Kpi({ name, value, sub, color, tip }: { name: string; value: string; sub?: string; color?: string; tip?: string }) {
  return (
    <Card style={{ padding: '14px 18px', borderTop: `3px solid ${color ?? T.accent}` }}>
      <div style={label} title={tip}>{name}</div>
      <div style={{ fontFamily: 'var(--font-display, inherit)', fontSize: 24, fontWeight: 700, margin: '4px 0 2px' }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: T.muted }}>{sub}</div>}
    </Card>
  )
}

/** A progress bar that can read past 100%, for the fee waiver and credit use. */
function Meter({ value, warnAbove, goodAbove }: { value: number; warnAbove?: number; goodAbove?: number }) {
  const color = goodAbove != null && value >= goodAbove ? T.positive
    : warnAbove != null && value >= warnAbove ? T.warn : T.accent
  return (
    <div style={{ height: 8, background: T.surface2, borderRadius: 4, overflow: 'hidden', margin: '6px 0' }}>
      <div style={{ width: `${Math.min(value, 100)}%`, height: '100%', background: color, borderRadius: 4 }} />
    </div>
  )
}

/** Monthly spend bars. Rewards are ~4% of spend, so they get a column in the table below
 *  rather than a second axis on this chart. */
function SpendChart({ d }: { d: CardDashboard }) {
  const [hover, setHover] = useState<number | null>(null)
  const months = d.months
  if (!months.length) return null
  const max = Math.max(...months.map(m => m.spend), 1)
  const W = 640, H = 170, PAD = 28
  const bw = (W - PAD * 2) / months.length
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img"
      aria-label={`Monthly card spend: ${months.map(m => `${monthLabel(m.period_to)} ${Math.round(m.spend)}`).join(', ')}`}>
      {months.map((m, i) => {
        const h = Math.max((m.spend / max) * (H - 46), 0)
        const x = PAD + i * bw
        const on = hover === i
        return (
          <g key={m.period_to} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <rect x={x} y={0} width={bw} height={H} fill="transparent" />
            <rect x={x + GAP} y={H - 26 - h} width={bw - GAP * 2} height={h} rx={4} fill={on ? T.accent : '#4a46c4'} />
            <text x={x + bw / 2} y={H - 10} textAnchor="middle" fontSize="9.5" fill={T.muted}>{monthLabel(m.period_to)}</text>
            {on && <text x={x + bw / 2} y={H - 32 - h} textAnchor="middle" fontSize="10.5" fontWeight="700" fill={T.text}>{fmt(m.spend)}</text>}
          </g>
        )
      })}
    </svg>
  )
}

export default function Cards() {
  const [cards, setCards] = useState<CardRow[]>([])
  const [cardId, setCardId] = useState<number | undefined>(undefined)
  const [d, setD] = useState<CardDashboard | null>(null)
  const [rules, setRules] = useState<CardMerchantRule[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [showCycle, setShowCycle] = useState(false)
  const [showAll, setShowAll] = useState(true)   // the all-cards usage view
  const [tick, setTick] = useState(0)            // bumps when data reloads, so the overview refetches
  const firstLoad = useRef(true)
  const [picked, setPicked] = useState<File[]>([])
  const [password, setPassword] = useState('')
  const [useLlm, setUseLlm] = useState(false)
  const [parsers, setParsers] = useState<CardParsers | null>(null)
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const [report, setReport] = useState<CardImportFile[] | null>(null)
  // the cycle editor's working copy, as text so a field can be cleared while typing
  const [form, setForm] = useState<Record<string, string>>({})

  const load = useCallback(async (id?: number) => {
    try {
      const cs = await getCards()
      setCards(cs)
      if (firstLoad.current) {
        firstLoad.current = false
        const want = Number(new URLSearchParams(location.search).get('card'))   // ?card=5 opens that card directly
        if (want && cs.some(c => c.id === want || c.members?.includes(want))) { setShowAll(false); id = id ?? want } else setShowAll(cs.length > 1)
      }
      const pick = id ?? cardId ?? cs[0]?.id
      setCardId(pick)
      const [dash, r] = [await getCardDashboard(pick), await getCardRules(pick)]
      setD(dash); setRules(r); setError(''); setTick(t => t + 1)
    } catch (e) { setError((e as Error).message) }
    getCardParsers().then(setParsers).catch(() => { })
  }, [cardId])
  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const remember = (card?: number) => {                // keep the address in step with the view, so it can be bookmarked
    const u = new URL(location.href)
    if (card) u.searchParams.set('card', String(card)); else u.searchParams.delete('card')
    history.replaceState(null, '', u)
  }
  const choose = (id: number) => { setShowAll(false); setCardId(id); setD(null); remember(id); load(id) }

  const addFiles = (list: FileList | null) => {
    const pdfs = Array.from(list ?? []).filter(f => /\.(pdf|xlsx)$/i.test(f.name))
    setPicked(prev => [...prev, ...pdfs.filter(f => !prev.some(p => p.name === f.name && p.size === f.size))])
    setReport(null)
  }

  const runImport = async () => {
    setBusy(true); setError(''); setReport(null)
    try {
      const r = await uploadCardStatements(picked, password, useLlm)
      setReport(r.files)
      setPassword('')  // never kept
      setPicked(prev => prev.filter(f => r.files.some(x => x.file === f.name && !x.ok)))  // keep only the failures
      load(r.files.find(f => f.ok)?.card_id)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  const correct = async (pattern: string, cls: string) => {
    setBusy(true)
    try { await setCardMerchantRule(pattern, cls, cardId); load(cardId) }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  const openCycle = () => {
    if (!d?.card) return
    const c = d.card
    setForm({
      name: c.name, profile: c.profile,
      statement_day: String(c.statement_day || ''), grace_days: String(c.grace_days), pay_buffer_days: String(c.pay_buffer_days),
      float_rate: String(c.float_rate), ...Object.fromEntries(Object.entries(c.rates).map(([k, v]) => [`rate_${k}`, String(v)])),
    })
    setShowCycle(true)
  }

  const saveCycle = async () => {
    if (!d?.card) return
    const c = d.card
    setBusy(true); setError('')
    try {
      await saveCardSettings(c.id, {
        name: form.name, profile: form.profile,
        credit_limit: c.credit_limit, annual_fee: c.annual_fee, fee_waiver_spend: c.fee_waiver_spend, cashback_cap: c.cashback_cap,
        statement_day: Number(form.statement_day), grace_days: Number(form.grace_days),
        pay_buffer_days: Number(form.pay_buffer_days), float_rate: Number(form.float_rate),
        rates: Object.fromEntries(d.profile.classes.map(k => [k.id, Number(form[`rate_${k.id}`])])),
      })
      setShowCycle(false); load(cardId)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  const closeImport = () => { setShowImport(false); setReport(null); setPicked([]); setError('') }

  const importDialog = (
    <Modal title="Import statements" onClose={closeImport}>
      <div
        onClick={() => fileInput.current?.click()}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files) }}
        style={{ border: `1.5px dashed ${dragging ? T.accent : T.border}`, borderRadius: 8, padding: '22px 14px',
          textAlign: 'center', cursor: 'pointer', background: dragging ? T.surface2 : 'transparent', marginBottom: 12 }}>
        <div style={{ fontSize: 13, fontWeight: 600 }}>Browse for statement PDFs or Excel exports</div>
        <div style={{ fontSize: 11.5, color: T.muted, marginTop: 2 }}>or drop them here · any mix of cards is fine</div>
        <input ref={fileInput} type="file" accept="application/pdf,.pdf,.xlsx" multiple hidden
          onChange={e => { addFiles(e.target.files); e.target.value = '' }} />
      </div>
      {picked.length > 0 && (
        <div style={{ marginBottom: 12, fontSize: 12 }}>
          {picked.map(f => (
            <div key={f.name + f.size} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 300 }}>{f.name}</span>
              <button onClick={() => setPicked(p => p.filter(x => x !== f))}
                style={{ background: 'none', border: 'none', color: T.muted, cursor: 'pointer' }} aria-label={`Remove ${f.name}`}>✕</button>
            </div>
          ))}
        </div>
      )}
      <Field name="PDF password (if the statement has one)">
        <input style={input} type="password" value={password}
          onChange={e => setPassword(e.target.value)} placeholder="used for this upload only, never saved" />
      </Field>
      {parsers && (
        <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 10 }}>
          Built-in readers: {parsers.formats.join(', ')}. Each statement identifies its own card.
          {parsers.llm_available ? (
            <label style={{ display: 'flex', gap: 6, alignItems: 'flex-start', marginTop: 8, color: T.text, cursor: 'pointer' }}>
              <input type="checkbox" checked={useLlm} onChange={e => setUseLlm(e.target.checked)} style={{ marginTop: 2 }} />
              <span>Use Claude for formats without a built-in reader.
                <span style={{ color: T.muted }}> The statement's text is sent to Anthropic. The result is still
                checked against the statement's own totals before anything is saved.</span></span>
            </label>
          ) : ' Other banks are not supported yet (set ANTHROPIC_API_KEY to enable a Claude fallback).'}
        </div>
      )}
      <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 14 }}>
        A statement that prints a purchases total must add up to it; one that does not must have every line
        readable. Anything else is reported and skipped, never half-imported. Re-uploading is safe: rows already
        stored are ignored. The PDF itself is not kept.
      </div>
      {error && <div style={{ color: T.negative, fontSize: 12.5, marginBottom: 10 }}>{error}</div>}
      <div style={{ display: 'flex', gap: 8 }}>
        <button style={btn(true)} disabled={busy || !picked.length} onClick={runImport}>
          {busy ? 'Reading…' : picked.length > 1 ? `Import ${picked.length} files` : 'Import'}
        </button>
        <button style={btn()} onClick={closeImport}>Close</button>
      </div>
      {report && (
        <table style={{ width: '100%', marginTop: 16, fontSize: 12, borderCollapse: 'collapse' }}>
          <tbody>
            {report.map(f => (
              <tr key={f.file} style={{ borderTop: `1px solid ${T.hairline}` }}>
                <td style={{ padding: '5px 0', verticalAlign: 'top' }}>
                  {f.ok ? '✓' : '✕'} {f.ok ? `${f.card} · ${f.period_to}` : f.file}
                </td>
                <td style={{ textAlign: 'right', color: f.ok ? T.muted : T.negative, maxWidth: 240 }}>
                  {f.ok ? `${fmt(f.spend ?? 0)} · +${f.added} rows${f.parser === 'Claude' ? ' · read by Claude' : ''}` : f.error}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Modal>
  )

  const cycleDialog = showCycle && d?.card && (
    <Modal title={`${d.card.name}: settings`} onClose={() => setShowCycle(false)}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 12px' }}>
        <Field name="Card name">
          <input style={input} value={form.name ?? ''} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
        </Field>
        <Field name="Reward scheme">
          <select style={input} value={form.profile ?? 'generic'} onChange={e => setForm(f => ({ ...f, profile: e.target.value }))}>
            <option value="generic">Usage only (no rewards)</option>
            <option value="icici_amazon">Amazon Pay ICICI</option>
            <option value="sbi_cashback">SBI Cashback</option>
            <option value="icici_rubyx">ICICI Rubyx</option>
            <option value="icici_sapphiro">ICICI Sapphiro</option>
            <option value="bob_eterna">BOB Eterna</option>
            <option value="hdfc_neu">HDFC Tata Neu</option>
            <option value="amex_smartearn">Amex SmartEarn</option>
          </select>
        </Field>
      </div>
      <div style={{ fontSize: 12, color: T.muted, marginBottom: 14 }}>
        The pay date is worked out from these. They apply to every card on the same bill. Take them from a monthly statement: the statement date and the
        <b> Payment Due Date</b> printed on it. A wrong due date means a wrong pay date, so check it.
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 12px' }}>
        <Field name="Statement day of month">
          <input style={input} inputMode="numeric" value={form.statement_day ?? ''}
            onChange={e => setForm(f => ({ ...f, statement_day: e.target.value }))} />
        </Field>
        <Field name="Days to the due date">
          <input style={input} inputMode="numeric" value={form.grace_days ?? ''}
            onChange={e => setForm(f => ({ ...f, grace_days: e.target.value }))} />
        </Field>
        <Field name="Pay this many days early">
          <input style={input} inputMode="numeric" value={form.pay_buffer_days ?? ''}
            onChange={e => setForm(f => ({ ...f, pay_buffer_days: e.target.value }))} />
        </Field>
        <Field name="Idle money earns (% a year)">
          <input style={input} inputMode="decimal" value={form.float_rate ?? ''}
            onChange={e => setForm(f => ({ ...f, float_rate: e.target.value }))} />
        </Field>
      </div>
      {form.profile !== d.card.profile && (
        <div style={{ fontSize: 11.5, color: T.muted, margin: '2px 0 10px' }}>
          Changing the scheme resets the reward rates to that scheme's published rates.
        </div>
      )}
      {d.profile.rewards && form.profile === d.card.profile && <div style={{ ...label, margin: '6px 0 8px' }}>Reward rates (%)</div>}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 12px' }}>
        {form.profile === d.card.profile && d.profile.rewards && d.profile.classes.map(k => (
          <Field key={k.id} name={k.label}>
            <input style={input} inputMode="decimal" value={form[`rate_${k.id}`] ?? ''}
              onChange={e => setForm(f => ({ ...f, [`rate_${k.id}`]: e.target.value }))} />
          </Field>
        ))}
      </div>
      {d.card.profile === 'icici_amazon' && (
        <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 12 }}>
          5% on Amazon needs a Prime membership; without Prime it is 3%.
        </div>
      )}
      {error && <div style={{ color: T.negative, fontSize: 12.5, marginBottom: 10 }}>{error}</div>}
      <div style={{ display: 'flex', gap: 8 }}>
        <button style={btn(true)} disabled={busy} onClick={saveCycle}>Save</button>
        <button style={btn()} onClick={() => setShowCycle(false)}>Cancel</button>
      </div>
    </Modal>
  )

  if (!d) return <div style={{ padding: 20, color: error ? T.negative : T.muted }}>{error || 'Loading…'}</div>

  const header = (
    <>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 10, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {cards.length > 1 && (
            <button onClick={() => { setShowAll(true); remember() }} style={{
              padding: '7px 14px', borderRadius: 18, fontSize: 13, fontWeight: 600, cursor: 'pointer',
              border: `1px solid ${showAll ? T.accent : T.border}`,
              background: showAll ? T.accent : T.surface2, color: showAll ? '#fff' : T.text,
            }}>All cards</button>
          )}
          {!showAll && [...cards].sort((a, b) => Number(a.status === 'closed') - Number(b.status === 'closed')).map(c => {
            const on = !showAll && c.id === cardId
            const closed = c.status === 'closed'
            return (
              <button key={c.id} onClick={() => choose(c.id)} style={{
                padding: '7px 14px', borderRadius: 18, fontSize: 13, fontWeight: 600, cursor: 'pointer',
                border: `1px solid ${on ? cardColor(c.color) : T.border}`, borderBottom: `3px solid ${cardColor(c.color)}`,
                background: on ? T.accent : T.surface2, color: on ? '#fff' : T.text,
                opacity: closed && !on ? 0.5 : 1, filter: closed && !on ? 'grayscale(1)' : 'none',
              }} title={closed ? 'Closed' : undefined}><CardChip color={c.color} name={c.name} size={18} />{c.name.replace(/ ···\d+$/, '')}</button>
            )
          })}
        </div>
        <button style={btn(true)} onClick={() => setShowImport(true)}>Import statements</button>
      </div>
      {error && !showImport && !showCycle && <div style={{ color: T.negative, fontSize: 12.5, marginBottom: 10 }}>{error}</div>}
    </>
  )

  if (!d.card) {
    return (
      <div style={{ padding: 20, maxWidth: 560 }}>
        {showImport && importDialog}
        <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8 }}>Cards</h2>
        <p style={{ color: T.muted, fontSize: 13, marginBottom: 14 }}>No card yet. Import a statement and its card is set up from it.</p>
        <button style={btn(true)} onClick={() => setShowImport(true)}>Import statements</button>
      </div>
    )
  }

  const { card, totals, fee, by_class: cls, pay, profile } = d
  const h = pay.habit
  const lb = pay.last_bill
  const next = pay.upcoming?.[0]
  const billOpen = lb && lb.days_to_pay >= 0           // a bill already issued whose pay date has not passed
  const recon = totals.cashback_calc - (totals.cashback_paid ?? 0)
  const reported = totals.cashback_paid != null
  const span = totals.since && totals.through ? (new Date(totals.through).getTime() - new Date(totals.since).getTime()) / 864e5 : 0
  const anyDue = d.months.some(m => m.due != null)
  const anyFee = d.months.some(m => m.fees)
  const when = (n: number) => (n === 0 ? 'today' : n === 1 ? 'tomorrow' : n > 1 ? `in ${n} days` : `${-n} day${n === -1 ? '' : 's'} ago`)

  return (
    <div style={{ padding: 20, maxWidth: 'none' }}>
      {showImport && importDialog}
      {cycleDialog}
      {header}

      {showAll ? <CardsOverviewPage key={tick} onPick={choose} /> : <>
      {card.numbers && card.numbers.length > 1 && (
        <div style={{ fontSize: 12, color: T.muted, marginBottom: 12 }}>
          Card numbers: ···{card.numbers.join(' → ···')}. A card re-issued under a new number is treated as one card.
        </div>
      )}

      {/* When to pay: the point of the page */}
      <Card style={{ padding: 22, marginBottom: 16, borderLeft: `4px solid ${T.accent2}` }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10, flexWrap: 'wrap', marginBottom: 6 }}>
          <span style={{ ...label, fontSize: 12.5, letterSpacing: 0.8 }}>When to pay</span>
          <span style={{ fontSize: 11.5, color: pay.verified ? T.muted : T.warn }}>
            {pay.needs_cycle ? 'Cycle not known' : pay.verified
              ? `Cycle: statement on the ${pay.statement_day}th, due ${pay.grace_days} days later`
              : `Assumed cycle: statement on the ${pay.statement_day}th, due ${pay.grace_days} days later`}
            {' · '}<button onClick={openCycle} style={{ background: 'none', border: 'none', color: T.accent, cursor: 'pointer', fontSize: 11.5, padding: 0 }}>
              {pay.verified ? 'edit' : 'confirm'}</button>
          </span>
        </div>

        {pay.shared_with && pay.shared_with.length > 0 && (
          <div style={{ fontSize: 12, color: T.muted, marginBottom: 6 }}>
            One bill with {pay.shared_with.join(' and ')}: the cards are paid together, so this is the date for all of them.
          </div>
        )}
        {pay.missing_statements && pay.missing_statements.length > 0 && (
          <div style={{ fontSize: 12, color: T.warn, marginBottom: 6 }}>
            Missing statement{pay.missing_statements.length > 1 ? 's' : ''}: {pay.missing_statements.map(shortDay).join(', ')}. Pay timing
            is worked out around the gap, not across it; upload {pay.missing_statements.length > 1 ? 'them' : 'it'} for the full picture.
          </div>
        )}
        {pay.needs_cycle && (
          <div style={{ fontSize: 13, color: T.muted }}>
            This statement format does not print the billing cycle. Enter the statement day and the days to the due
            date from a monthly statement to get pay dates.
          </div>
        )}

        {!pay.needs_cycle && (
          <>
            {billOpen && lb ? (
              <div style={{ fontFamily: 'var(--font-display, inherit)', fontSize: 26, fontWeight: 700, margin: '4px 0 2px' }}>
                Pay {fmtFull(lb.amount)} on {dayLabel(lb.pay_on)}
                <span style={{ fontSize: 14, fontWeight: 500, color: T.muted }}> · {when(lb.days_to_pay)}</span>
              </div>
            ) : next ? (
              <div style={{ fontFamily: 'var(--font-display, inherit)', fontSize: 26, fontWeight: 700, margin: '4px 0 2px' }}>
                Pay on {dayLabel(next.pay_on)}
                <span style={{ fontSize: 14, fontWeight: 500, color: T.muted }}> · {when(next.days_to_pay)}</span>
              </div>
            ) : null}
            <div style={{ fontSize: 12.5, color: T.muted, marginBottom: 14 }}>
              {billOpen && lb
                ? `Statement ${shortDay(lb.statement)} · due ${shortDay(lb.due)} · paying ${pay.buffer} day${pay.buffer === 1 ? '' : 's'} early leaves a margin.`
                : next && `Next statement ${shortDay(next.statement)} · due ${shortDay(next.due)} · pay ${pay.buffer} day${pay.buffer === 1 ? '' : 's'} before it`
                + (lb ? `. The ${shortDay(lb.statement)} bill (${fmtFull(lb.amount)}) was due ${shortDay(lb.due)}: upload the next statement to confirm it was paid.` : '.')}
            </div>

            {pay.stale && (
              <div style={{ fontSize: 12, color: T.warn, marginBottom: 12 }}>
                The latest transaction is from {shortDay(pay.data_through ?? '')}. Upload newer statements for current dates.
              </div>
            )}

            {h && h.paid > 0 && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 14, margin: '4px 0 12px' }}>
                <div>
                  <div style={{ fontSize: 20, fontWeight: 700 }}>{h.days_credit_used.toFixed(0)} <span style={{ fontSize: 13, color: T.muted, fontWeight: 500 }}>of {h.days_credit_available.toFixed(0)} days</span></div>
                  <div style={{ fontSize: 11.5, color: T.muted }}>of free credit you actually use</div>
                </div>
                <div>
                  <div style={{ fontSize: 20, fontWeight: 700 }}>{Math.abs(h.days_early).toFixed(0)} days {h.days_early >= 0 ? 'early' : 'late'}</div>
                  <div style={{ fontSize: 11.5, color: T.muted }}>on average, against the pay date</div>
                </div>
                <div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: h.forgone_per_year > 0 ? T.warn : T.positive }}>{fmtFull(h.forgone_per_year)} <span style={{ fontSize: 13, color: T.muted, fontWeight: 500 }}>a year</span></div>
                  <div style={{ fontSize: 11.5, color: T.muted }}>not earned, if idle money earns {pay.rate}%</div>
                </div>
              </div>
            )}

            {next && next.kept_value >= 1 && (
              <div style={{ fontSize: 12.5 }}>
                Paying the day the bill arrives, instead of on the pay date, gives away about <b>{fmtFull(next.kept_value)}</b> on
                a typical {fmt(pay.expected_bill ?? 0)} bill ({next.days_kept} days of your money).
              </div>
            )}
            {h && h.late_amount > 0 && (
              <div style={{ fontSize: 12.5, color: pay.verified ? T.negative : T.warn, marginTop: 6 }}>
                {pay.verified ? `${fmtFull(h.late_amount)} was paid after its due date. That costs a late fee plus interest on the whole cycle.` : `${fmtFull(h.late_amount)} was paid after the due date this cycle assumes. If the assumed cycle is wrong it was not late: confirm the cycle above.`}
              </div>
            )}
            <div style={{ fontSize: 11.5, color: T.muted, marginTop: 8 }}>
              Pay the whole bill on the pay date and never after the due date. One day early costs a few rupees;
              one day late costs a fee plus about 45% a year on everything in the cycle. The pay date also steps
              back off a weekend.
            </div>

            {h && h.cycles.length > 0 && (
              <details style={{ marginTop: 12 }}>
                <summary style={{ cursor: 'pointer', fontSize: 12, color: T.muted }}>How the last {h.cycles.length} bills were paid</summary>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, marginTop: 8 }}>
                  <thead>
                    <tr style={th}>
                      <th style={{ textAlign: 'left', padding: '4px 0' }}>Statement</th><th style={{ textAlign: 'right' }}>Pay on</th>
                      <th style={{ textAlign: 'right' }}>Paid</th><th style={{ textAlign: 'right' }}>Days early</th>
                      <th style={{ textAlign: 'right' }}>Not earned</th>
                    </tr>
                  </thead>
                  <tbody>
                    {h.cycles.map(c => (
                      <tr key={c.statement} style={{ borderTop: `1px solid ${T.hairline}` }}>
                        <td style={{ padding: '6px 0' }}>{shortDay(c.statement)} {monthLabel(c.statement).slice(-2)}</td>
                        <td style={{ textAlign: 'right', color: T.muted }}>{shortDay(c.pay_on)}</td>
                        <td style={{ textAlign: 'right' }}>{fmt(c.paid)}</td>
                        <td style={{ textAlign: 'right', color: c.late ? T.negative : T.muted }}>{c.early_days == null ? '—' : c.early_days.toFixed(0)}</td>
                        <td style={{ textAlign: 'right', color: c.forgone ? T.warn : T.muted }}>{fmtFull(c.forgone)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            )}
          </>
        )}
      </Card>

      {/* What the card made, or for a card with no reward scheme, how it is used */}
      {!profile.rewards && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12, marginBottom: 16 }}>
          <Kpi name="Card spend" value={fmt(totals.spend)} color={T.accent}
            sub={`${fmt(totals.avg_monthly_spend)} a month · ${totals.transactions} txns`} />
          <Kpi name="Last 12 months" value={fmt(totals.spend_12m)} color={T.accent2} sub="net of refunds" />
          <Kpi name="On EMI" value={totals.emi ? fmt(totals.emi) : '—'} color={T.warn}
            sub={totals.emi ? `${pct1(totals.emi / (totals.spend || 1) * 100)} of spend, paid as instalments` : 'no EMI instalments'} />
          <Kpi name="Fees and interest" value={totals.fees_paid ? fmtFull(totals.fees_paid) : '—'} color={T.warn}
            sub={totals.fees_paid ? 'EMI interest, tax, redemption fees' : 'none charged'} />
        </div>
      )}
      {profile.rewards && <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12, marginBottom: 16 }}>
        <Kpi name={profile.earned_label ?? (d.points ? 'Rewards earned' : totals.earned_is_estimate ? 'Rewards (estimated)' : 'Cashback earned')} value={fmtFull(totals.earned)} color={T.positive}
          sub={d.points ? `${d.points.earned.toLocaleString('en-IN')} points at ₹${profile.point_value} · ${pct1(totals.effective_rate)} of spend` : `${pct1(totals.effective_rate)} of spend${totals.milestone_bonus ? ` · incl. ${fmtFull(totals.milestone_bonus)} milestone bonus` : ''}`}
          tip={totals.earned_is_estimate ? "These statements do not print the reward earned, so it is estimated from the card's rates" : 'Taken from the statements, not computed'} />
        <Kpi name="Net profit" value={fmtFull(totals.net_profit)} color={totals.net_profit >= 0 ? T.positive : T.negative}
          sub={totals.fees_paid ? `after ${fmtFull(totals.fees_paid)} of fees${profile.emi_earns ? '' : ' and EMI interest'}` : 'no fees charged'} />
        {profile.has_leaks
          ? <Kpi name="Left on the table" value={fmtFull(Math.max(totals.best_possible - totals.earned, 0))} color={T.warn}
            sub={`if every rupee earned ${Math.max(...Object.values(card.rates))}%`} tip="The gap between what you earned and the most this card can pay" />
          : <Kpi name="Fees and interest" value={fmtFull(totals.fees_paid)} color={T.warn}
            sub={totals.fees_paid ? 'EMI interest, processing fees, tax' : 'none'} />}
        <Kpi name="Card spend" value={fmt(totals.spend)} color={T.accent}
          sub={`${fmt(totals.avg_monthly_spend)} a month · ${totals.transactions} txns`} />
      </div>}

      {/* Where the rewards come from, and the card's two thresholds */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(330px, 1fr))', gap: 16, marginBottom: (profile.rewards || fee || d.utilisation != null) ? 16 : 0 }}>
        {profile.rewards && profile.classes.length > 1 && <Card style={{ padding: 20 }}>
          {title('Where the rewards come from', `${totals.since ? shortDay(totals.since) + ' ' + monthLabel(totals.since).slice(-2) : ''} to ${totals.through ? shortDay(totals.through) + ' ' + monthLabel(totals.through).slice(-2) : ''}`)}
          <div style={{ display: 'flex', height: 12, gap: GAP, borderRadius: 3, overflow: 'hidden', marginBottom: 14 }}>
            {profile.classes.filter(k => cls[k.id]?.spend > 0).map(k => (
              <div key={k.id} title={`${k.label}: ${fmt(cls[k.id].spend)} (${pct1(cls[k.id].pct)})`}
                style={{ width: `${cls[k.id].pct}%`, background: clsColor(k.id) }} />
            ))}
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr style={th}>
                <th style={{ textAlign: 'left', padding: '4px 0' }}>Kind of spend</th>
                <th style={{ textAlign: 'right' }}>Spend</th><th style={{ textAlign: 'right' }}>Share</th>
                {profile.point_value > 0 && <th style={{ textAlign: 'right' }}>Points</th>}
                <th style={{ textAlign: 'right' }}>{reported ? 'Cashback' : 'Est.'}</th>
              </tr>
            </thead>
            <tbody>
              {profile.classes.map(k => (
                <tr key={k.id} style={{ borderTop: `1px solid ${T.hairline}` }}>
                  <td style={{ padding: '7px 0' }}>
                    {swatch(clsColor(k.id))}{k.id === 'excluded' ? `${k.label}${!profile.emi_earns ? ' (incl. EMI)' : ''}` : profile.point_value ? `${k.label} · ${+(k.rate / profile.point_value).toFixed(1)} pts per ₹100` : `${k.label} · ${k.rate}%`}
                  </td>
                  <td style={{ textAlign: 'right' }}>{fmt(cls[k.id]?.spend ?? 0)}</td>
                  <td style={{ textAlign: 'right', color: T.muted }}>{pct1(cls[k.id]?.pct ?? 0)}</td>
                  {profile.point_value > 0 && <td style={{ textAlign: 'right', color: T.muted }}>{(cls[k.id]?.points ?? 0).toLocaleString('en-IN')}</td>}
                  <td style={{ textAlign: 'right', color: k.id === 'excluded' ? T.muted : T.positive }}>{fmtFull(cls[k.id]?.cashback ?? 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ fontSize: 11.5, color: T.muted, marginTop: 10 }}>
            {reported
              ? <>The statement never says which spend was online, so each merchant is classified by rule. Computed {fmtFull(totals.cashback_calc)} against {fmtFull(totals.cashback_paid ?? 0)} actually paid
                — a gap of {recon >= 0 ? '+' : '−'}{fmtFull(Math.abs(recon))} ({pct1(Math.abs(recon) / ((totals.cashback_paid ?? 0) || 1) * 100)}). Fix a merchant below to close it.</>
              : <>This statement format does not print the reward earned, so it is estimated from the card's rates and cannot be checked against a statement. Refunds take their reward back.</>}
          </div>
        </Card>}

        {(fee || d.utilisation != null) && (
          <Card style={{ padding: 20 }}>
            {title('The two numbers that cost money', 'fee waiver and credit use')}
            {fee && (
              <div style={{ marginBottom: 18 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5 }}>
                  <span>Annual fee {fmtFull(fee.annual_fee)}</span>
                  <span style={{ color: fee.waived ? T.positive : T.warn, fontWeight: 600 }}>{fee.waived ? 'Waived' : `${fmt(fee.short_by)} short`}</span>
                </div>
                <Meter value={fee.progress} goodAbove={100} />
                <div style={{ fontSize: 11.5, color: T.muted }}>
                  {fmt(fee.year_spend)} spent in the last 12 months against the {fmt(fee.waiver_spend)} that waives the renewal fee — {pct1(fee.progress)} of the way.
                  {fee.waived && ' At this rate the fee should not be charged again.'}
                </div>
              </div>
            )}
            {d.utilisation != null && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5 }}>
                  <span>Credit used</span>
                  <span style={{ color: d.utilisation >= 30 ? T.warn : T.positive, fontWeight: 600 }}>{pct1(d.utilisation)}</span>
                </div>
                <Meter value={d.utilisation} warnAbove={30} />
                <div style={{ fontSize: 11.5, color: T.muted }}>
                  {d.latest ? `${fmtFull(d.latest.total_due)} due of a ${fmt(card.credit_limit)} limit` : '—'}. Under 30% protects the credit score.
                </div>
              </div>
            )}
          </Card>
        )}
      </div>

      {d.benefits && <RubyxPanel b={d.benefits} />}
      {d.points && <PointsPanel p={d.points} value={profile.point_value} />}
      <Card style={{ padding: 20, marginBottom: 16 }}><CardPerks cardId={card.id} /></Card>

      {/* Month by month, and by year where statements are yearly */}
      <Card style={{ padding: 20, marginBottom: 16 }}>
        {title('Month by month', profile.rewards ? 'spend, and the reward it earned' : 'spend by statement cycle')}
        <SpendChart d={d} />
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, marginTop: 10 }}>
          <thead>
            <tr style={th}>
              <th style={{ textAlign: 'left', padding: '4px 0' }}>Statement</th>
              <th style={{ textAlign: 'right' }}>Spend</th>
              {profile.rewards && <><th style={{ textAlign: 'right' }}>{reported ? 'Cashback' : 'Est. reward'}</th>
              <th style={{ textAlign: 'right' }}>Rate</th></>}
              {reported && <th style={{ textAlign: 'right' }}>Computed</th>}
              {anyDue && <th style={{ textAlign: 'right' }}>Bill</th>}
              {anyFee && <th style={{ textAlign: 'right' }}>Fees</th>}
            </tr>
          </thead>
          <tbody>
            {[...d.months].reverse().map(m => {
              const diff = m.calc - m.cashback
              return (
                <tr key={m.period_to} style={{ borderTop: `1px solid ${T.hairline}` }}>
                  <td style={{ padding: '7px 0' }}>{monthLabel(m.period_to)}</td>
                  <td style={{ textAlign: 'right' }}>{fmtFull(m.spend)}</td>
                  {profile.rewards && <>
                    <td style={{ textAlign: 'right', color: T.positive }}>{fmtFull(m.cashback)}</td>
                    <td style={{ textAlign: 'right', color: T.muted }}>{pct1(m.rate)}</td></>}
                  {reported && (
                    <td style={{ textAlign: 'right', color: Math.abs(diff) > 100 ? T.warn : T.muted }} title="What the classification rules say this cycle should have paid">
                      {m.reported ? <>{fmtFull(m.calc)} <span style={{ fontSize: 11 }}>({diff >= 0 ? '+' : '−'}{Math.round(Math.abs(diff))})</span></> : '—'}
                    </td>
                  )}
                  {anyDue && <td style={{ textAlign: 'right', color: T.muted }}>{m.due != null ? fmtFull(m.due) : '—'}</td>}
                  {anyFee && <td style={{ textAlign: 'right', color: m.fees ? T.warn : T.muted }}>{m.fees ? fmtFull(m.fees) : '—'}</td>}
                </tr>
              )
            })}
          </tbody>
        </table>
        {d.years.length > 1 && span > 450 && (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, marginTop: 18 }}>
            <thead>
              <tr style={th}>
                <th style={{ textAlign: 'left', padding: '4px 0' }}>Financial year</th>
                <th style={{ textAlign: 'right' }}>Spend</th>{profile.rewards && <th style={{ textAlign: 'right' }}>{reported ? 'Cashback' : 'Est. reward'}</th>}
                <th style={{ textAlign: 'right' }}>Fees</th>
              </tr>
            </thead>
            <tbody>
              {d.years.map(y => (
                <tr key={y.fy} style={{ borderTop: `1px solid ${T.hairline}` }}>
                  <td style={{ padding: '7px 0' }}>{y.fy}</td>
                  <td style={{ textAlign: 'right' }}>{fmtFull(y.spend)}</td>
                  {profile.rewards && <td style={{ textAlign: 'right', color: T.positive }}>{fmtFull(y.cashback)}</td>}
                  <td style={{ textAlign: 'right', color: y.fees ? T.warn : T.muted }}>{y.fees ? fmtFull(y.fees) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {/* Merchants, and where moving spend would pay */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))', gap: 16, marginBottom: 16 }}>
        <Card style={{ padding: 20 }}>
          {title('Where the money goes', profile.rewards ? 'change a merchant\'s kind if it is wrong' : 'net of refunds, by merchant')}
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr style={th}>
                <th style={{ textAlign: 'left', padding: '4px 0' }}>Merchant</th>
                <th style={{ textAlign: 'right' }}>Spend</th>
                {profile.rewards && <><th style={{ textAlign: 'right' }}>Earned</th>
                <th style={{ textAlign: 'left', paddingLeft: 10 }}>Kind</th></>}
              </tr>
            </thead>
            <tbody>
              {d.merchants.slice(0, 14).map(m => (
                <tr key={m.name} style={{ borderTop: `1px solid ${T.hairline}` }}>
                  <td style={{ padding: '7px 0' }}>
                    {m.name}
                    <span style={{ color: T.muted, fontSize: 11 }}> ×{m.count}{m.emi ? ` · ${m.emi} EMI` : ''}</span>
                  </td>
                  <td style={{ textAlign: 'right' }}>{fmt(m.spend)}</td>
                  {profile.rewards && <>
                  <td style={{ textAlign: 'right', color: m.cashback ? T.positive : T.muted }}>
                    {fmtFull(m.cashback)} <span style={{ fontSize: 11, color: T.muted }}>{pct1(m.rate)}</span>
                  </td>
                  <td style={{ paddingLeft: 10 }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                      {swatch(clsColor(m.cls))}
                      <select value={m.cls} disabled={busy} aria-label={`Kind for ${m.name}`}
                        onChange={e => correct(m.name.toUpperCase(), e.target.value)}
                        style={{ background: 'transparent', color: T.text, border: 'none', fontSize: 12, cursor: 'pointer', outline: 'none' }}>
                        {m.cls === 'mixed' && <option value="mixed" disabled>mixed</option>}
                        {profile.classes.map(k => <option key={k.id} value={k.id} style={{ background: T.surface }}>{k.label}</option>)}
                      </select>
                    </span>
                  </td></>}
                </tr>
              ))}
            </tbody>
          </table>
          {rules.length > 0 && (
            <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid ${T.hairline}` }}>
              <div style={{ ...label, marginBottom: 6 }}>Your corrections</div>
              {rules.map(r => (
                <div key={r.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12, padding: '3px 0' }}>
                  <span>{swatch(clsColor(r.cls))}{r.pattern} → {profile.classes.find(k => k.id === r.cls)?.label ?? r.cls}</span>
                  <button style={{ ...smallBtn, padding: '2px 8px', fontSize: 11 }} onClick={() => deleteCardRule(r.id).then(() => load(cardId))}>Remove</button>
                </div>
              ))}
            </div>
          )}
        </Card>

        {d.categories.length > 0 && (
          <Card style={{ padding: 20 }}>
            {title('By category', "the card issuer's own labels")}
            {d.categories.slice(0, 10).map(c => (
              <div key={c.name} style={{ display: 'grid', gridTemplateColumns: 'minmax(120px, 1fr) 90px 70px', gap: 10, alignItems: 'center', padding: '5px 0', fontSize: 12.5 }}>
                <div>
                  <div style={{ marginBottom: 3 }} title={c.name}>{c.name.replace('-', ' · ')}</div>
                  <div style={{ height: 6, background: T.surface2, borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{ width: `${c.pct}%`, height: '100%', background: T.accent, borderRadius: 3 }} />
                  </div>
                </div>
                <span style={{ textAlign: 'right' }}>{fmt(c.spend)}</span>
                <span style={{ textAlign: 'right', color: T.muted }}>{pct1(c.pct)}</span>
              </div>
            ))}
          </Card>
        )}

        {profile.has_leaks && (
          <Card style={{ padding: 20 }}>
            {title('Worth moving online', `${fmtFull(d.leaks.reduce((t, l) => t + l.missed, 0))} at stake over this period`)}
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead>
                <tr style={th}>
                  <th style={{ textAlign: 'left', padding: '4px 0' }}>Merchant</th>
                  <th style={{ textAlign: 'right' }}>Spend</th><th style={{ textAlign: 'right' }}>Missed</th>
                </tr>
              </thead>
              <tbody>
                {d.leaks.map(l => (
                  <tr key={l.name} style={{ borderTop: `1px solid ${T.hairline}` }}>
                    <td style={{ padding: '7px 0' }}>
                      {swatch(clsColor(l.cls))}{l.name}
                      {l.cls === 'excluded' && <span style={{ color: T.muted, fontSize: 11 }}> earns nothing</span>}
                    </td>
                    <td style={{ textAlign: 'right' }}>{fmt(l.spend)}</td>
                    <td style={{ textAlign: 'right', color: T.warn }}>{fmtFull(l.missed)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ fontSize: 11.5, color: T.muted, marginTop: 10 }}>
              An in-person spend earns less than the same spend online, so moving it to the merchant's website or app is
              worth the difference. An excluded merchant earns nothing on this card whatever you do, so the amount shown is
              the case for putting it on a different card.
            </div>
          </Card>
        )}
      </div>
      </>}
    </div>
  )
}
