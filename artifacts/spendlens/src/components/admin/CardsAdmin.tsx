import { useCallback, useEffect, useState } from 'react'
import { createCard, getCardsAdmin, patchCard, type AdminCard, type CardPatch } from '../../api'
import { T, fmt } from '../../theme'
import { cardColor, CardChip } from '../../cardColors'
import CardPerks from '../CardPerks'
import { AdminHeader, Card, Field, btn, input, smallBtn } from '../ui'

// Scheme -> label. A scheme sets the reward terms, so pick the one that matches the card; "Other" tracks usage only.
const SCHEMES: [string, string][] = [
  ['sbi_cashback', 'SBI Cashback'], ['icici_amazon', 'Amazon Pay ICICI'], ['icici_rubyx', 'ICICI Rubyx'], ['icici_sapphiro', 'ICICI Sapphiro'],
  ['bob_eterna', 'BOB Eterna'], ['hdfc_neu', 'HDFC Tata Neu'], ['amex_smartearn', 'Amex SmartEarn'], ['generic', 'Other card (usage only)'],
]

const dayLabel = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' }) : '—')

const startForm = (c: AdminCard): Record<string, string> => ({
  name: c.name, issuer: c.issuer, last4: c.numbers[c.numbers.length - 1] ?? '', network: c.network, profile: c.profile, notes: c.notes,
  credit_limit: String(c.credit_limit || ''), annual_fee: String(c.annual_fee || ''), fee_waiver_spend: String(c.fee_waiver_spend || ''),
  statement_day: c.statement_day ? String(c.statement_day) : '', grace_days: c.grace_days ? String(c.grace_days) : '', color: c.color,
})

// Quick picks for a card's colour; any colour can be chosen. The server keeps every card's colour different.
const SWATCHES = ['#7c74ff', '#f5b942', '#38bdf8', '#f472b6', '#3ecf8e', '#fb7c4a', '#e2e8f0', '#a3e635', '#c084fc', '#2dd4bf', '#f87171']

/** Every detail of a card. Only what you changed is sent, so a card with an old short number is not re-checked. */
function DetailsForm({ card, f, onChange, onSave, onCancel }: {
  card: AdminCard; f: Record<string, string>; onChange: (f: Record<string, string>) => void
  onSave: (body: CardPatch) => void; onCancel: () => void
}) {
  const start = startForm(card)
  const set = (k: string) => (e: { target: { value: string } }) => onChange({ ...f, [k]: e.target.value })
  const text = (k: string, name: string, extra: object = {}) => (
    <Field name={name}><input style={input} value={f[k]} onChange={set(k)} {...extra} /></Field>
  )
  const save = () => {
    const body: Record<string, unknown> = {}
    for (const k of Object.keys(f)) {
      if (f[k] === start[k]) continue
      body[k] = ['credit_limit', 'annual_fee', 'fee_waiver_spend', 'statement_day', 'grace_days'].includes(k) ? Number(f[k] || 0) : f[k]
    }
    if (!Object.keys(body).length) return onCancel()
    onSave(body as CardPatch)
  }
  return (
    <div style={{ borderTop: `1px solid ${T.border}`, marginTop: 14, paddingTop: 14 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
        {text('name', 'Card name', { maxLength: 60 })}
        {text('issuer', 'Bank')}
        {text('last4', 'Last digits', { inputMode: 'numeric', maxLength: 5 })}
        {text('network', 'Network (Visa, Mastercard…)', { maxLength: 30 })}
        <Field name="Reward scheme">
          <select style={input} value={f.profile} onChange={set('profile')}>
            {SCHEMES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </Field>
        {text('credit_limit', 'Credit limit (₹)', { inputMode: 'numeric' })}
        {text('annual_fee', 'Annual fee (₹)', { inputMode: 'numeric' })}
        {text('fee_waiver_spend', 'Fee waived at yearly spend (₹)', { inputMode: 'numeric' })}
        {text('statement_day', 'Statement day of month', { inputMode: 'numeric' })}
        {text('grace_days', 'Days from statement to due date', { inputMode: 'numeric' })}
      </div>
      <Field name="Colour (every card has its own)">
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
          <CardChip color={f.color} name={f.name || card.name} size={26} />
          {SWATCHES.map(s => (
            <button key={s} title={s} onClick={() => onChange({ ...f, color: s })} style={{
              width: 22, height: 22, borderRadius: 5, background: s, cursor: 'pointer', padding: 0,
              border: f.color.toLowerCase() === s ? `2px solid ${T.text}` : `1px solid ${T.border}`,
            }} />
          ))}
          <input type="color" value={f.color} onChange={e => onChange({ ...f, color: e.target.value })} title="Any colour"
            style={{ width: 30, height: 24, padding: 0, border: 'none', background: 'none', cursor: 'pointer' }} />
        </div>
      </Field>
      <Field name="Notes"><input style={input} value={f.notes} maxLength={500} onChange={set('notes')} placeholder="anything worth remembering about this card" /></Field>
      <div style={{ fontSize: 11.5, color: T.muted, margin: '4px 0 10px' }}>
        {f.profile !== card.profile && "Changing the scheme resets its reward rates to the new scheme's and recomputes this card's rewards. "}
        {f.issuer !== card.issuer && 'Statements attach to a card by bank name and last digits, so keep the bank as the statement prints it if you want imports to find this card. '}
        Limit and fees apply to every number this card has had; the cycle applies to every card on its bill. Past statements are never changed.
      </div>
      <button style={btn(true)} onClick={save}>Save details</button>{' '}
      <button style={btn()} onClick={onCancel}>Cancel</button>
    </div>
  )
}

/** Every card, active or closed. A card is never deleted: closing it keeps all its data and greys it out,
 *  and it drops out of pay dates and recommendations. Rename it here too. */
export default function CardsAdmin() {
  const [cards, setCards] = useState<AdminCard[]>([])
  const [msg, setMsg] = useState<{ text: string; error?: boolean } | null>(null)
  const [renaming, setRenaming] = useState<{ id: number; name: string } | null>(null)
  const [closing, setClosing] = useState<number | null>(null)   // a card waiting for its close to be confirmed
  const [editing, setEditing] = useState<{ id: number; f: Record<string, string> } | null>(null)
  const [perksOf, setPerksOf] = useState<number | null>(null)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ name: '', profile: 'generic', last4: '', issuer: '' })

  const load = useCallback(() => {
    getCardsAdmin().then(setCards).catch(e => setMsg({ text: e.message, error: true }))
  }, [])
  useEffect(load, [load])

  const run = async (p: Promise<unknown>, ok: string) => {
    try { await p; setMsg({ text: ok }); setRenaming(null); setClosing(null); setAdding(false); setEditing(null); load() } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
  }

  const active = cards.filter(c => c.status !== 'closed').length
  return (
    <div>
      <AdminHeader title="Cards"
        hint="Every card you have. Add one, rename it, or mark it closed when you no longer use it: a closed card is greyed out everywhere and left out of pay dates and recommendations, but nothing is ever deleted."
        action={<button style={btn(true)} onClick={() => setAdding(true)}>+ Add card</button>} />
      {adding && (
        <Card style={{ padding: 18, marginBottom: 14 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12 }}>
            <Field name="Card name"><input autoFocus style={input} maxLength={60} value={form.name} placeholder="e.g. Axis Magnus" onChange={e => setForm({ ...form, name: e.target.value })} /></Field>
            <Field name="Reward scheme">
              <select style={input} value={form.profile} onChange={e => setForm({ ...form, profile: e.target.value })}>
                {SCHEMES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </Field>
            {form.profile === 'generic' && (
              <Field name="Bank (optional)"><input style={input} value={form.issuer} placeholder="e.g. Axis Bank" onChange={e => setForm({ ...form, issuer: e.target.value })} /></Field>
            )}
            <Field name="Last 4 digits (optional)"><input style={input} inputMode="numeric" maxLength={5} value={form.last4} placeholder="1234" onChange={e => setForm({ ...form, last4: e.target.value.replace(/\D/g, '') })} /></Field>
          </div>
          <div style={{ fontSize: 11.5, color: T.muted, margin: '10px 0' }}>
            A placeholder is fine: no statement is needed. The card appears on the Cards page straight away, and statements imported later attach to it when the bank and last digits match.
          </div>
          <button style={btn(true)} onClick={() => run(createCard(form).then(() => setForm({ name: '', profile: 'generic', last4: '', issuer: '' })), 'Card added')}>Add card</button>{' '}
          <button style={btn()} onClick={() => setAdding(false)}>Cancel</button>
        </Card>
      )}
      {msg && <div style={{ fontSize: 12.5, marginBottom: 12, color: msg.error ? T.negative : T.positive }}>{msg.text}</div>}
      <div style={{ fontSize: 12, color: T.muted, marginBottom: 10 }}>{cards.length} cards · {active} active · {cards.length - active} closed</div>

      {cards.map(c => {
        const closed = c.status === 'closed'
        return (
          <Card key={c.id} style={{ padding: '14px 18px', marginBottom: 10, borderLeft: `4px solid ${cardColor(c.color)}`, opacity: closed ? 0.5 : 1, filter: closed ? 'grayscale(0.9)' : 'none' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
              <div style={{ minWidth: 240, flex: 1 }}>
                {renaming?.id === c.id ? (
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <input autoFocus style={{ ...input, maxWidth: 320 }} value={renaming.name} maxLength={60}
                      onChange={e => setRenaming({ id: c.id, name: e.target.value })}
                      onKeyDown={e => {
                        if (e.key === 'Enter') run(patchCard(c.id, { name: renaming.name }), 'Renamed')
                        if (e.key === 'Escape') setRenaming(null)
                      }} />
                    <button style={btn(true)} onClick={() => run(patchCard(c.id, { name: renaming.name }), 'Renamed')}>Save</button>
                    <button style={btn()} onClick={() => setRenaming(null)}>Cancel</button>
                  </div>
                ) : (
                  <div style={{ fontSize: 15, fontWeight: 700 }}>
                    <CardChip color={c.color} name={c.name} size={22} />{c.name}
                    {closed && <span style={{ marginLeft: 8, fontSize: 10.5, fontWeight: 600, color: T.muted, border: `1px solid ${T.border}`, borderRadius: 10, padding: '1px 8px' }}>CLOSED</span>}
                  </div>
                )}
                <div style={{ fontSize: 12, color: T.muted, marginTop: 3 }}>
                  {c.issuer} · {c.scheme} · {c.numbers.some(Boolean) ? `number${c.numbers.length > 1 ? 's' : ''} ···${c.numbers.slice().reverse().join(', ···')}` : 'no number yet'}
                  {c.shared_with.length > 0 && ` · shares a bill with ${c.shared_with.join(', ')}`}
                </div>
              </div>

              <div style={{ display: 'flex', gap: 22, fontSize: 12.5 }}>
                <div><div style={{ color: T.muted, fontSize: 10.5 }}>USED</div>{dayLabel(c.since)} to {dayLabel(c.last_used)}</div>
                <div><div style={{ color: T.muted, fontSize: 10.5 }}>SPEND</div>{fmt(c.spend)}</div>
                <div><div style={{ color: T.muted, fontSize: 10.5 }}>DATA</div>{c.transactions} txns · {c.statements} stmts</div>
              </div>

              <div style={{ display: 'flex', gap: 6, alignItems: 'center', filter: 'none' }}>
                {renaming?.id !== c.id && <button style={smallBtn} onClick={() => setRenaming({ id: c.id, name: c.name })}>Rename</button>}
                <button style={smallBtn} onClick={() => setPerksOf(perksOf === c.id ? null : c.id)}>{perksOf === c.id ? 'Hide benefits' : 'Benefits'}</button>
                <button style={smallBtn} onClick={() => editing?.id === c.id ? setEditing(null) : setEditing({ id: c.id, f: startForm(c) })}>{editing?.id === c.id ? 'Close details' : 'Edit details'}</button>
                {closed ? (
                  <button style={smallBtn} onClick={() => run(patchCard(c.id, { status: 'active' }), `${c.name} is active again`)}>Reopen</button>
                ) : closing === c.id ? (
                  <>
                    <span style={{ fontSize: 11.5, color: T.muted, maxWidth: 190 }}>Keeps all its data. Greyed out, no pay dates.</span>
                    <button style={{ ...smallBtn, color: T.warn }} onClick={() => run(patchCard(c.id, { status: 'closed' }), `${c.name} marked closed`)}>Confirm</button>
                    <button style={smallBtn} onClick={() => setClosing(null)}>Cancel</button>
                  </>
                ) : (
                  <button style={smallBtn} onClick={() => setClosing(c.id)}>Mark closed</button>
                )}
              </div>
            </div>
            {perksOf === c.id && (
              <div style={{ borderTop: `1px solid ${T.border}`, marginTop: 14, paddingTop: 14 }}><CardPerks cardId={c.id} editable /></div>
            )}
            {editing?.id === c.id && (
              <DetailsForm card={c} f={editing.f} onChange={f => setEditing({ id: c.id, f })} onCancel={() => setEditing(null)}
                onSave={body => run(patchCard(c.id, body), `${c.name} updated`)} />
            )}
          </Card>
        )
      })}
    </div>
  )
}
