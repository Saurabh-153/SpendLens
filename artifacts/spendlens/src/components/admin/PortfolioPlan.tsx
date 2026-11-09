import { useCallback, useEffect, useState } from 'react'
import {
  addGoal, deleteGoal, getCategories, getMix, getPortfolioPlan, getSubcategories, saveMixPlan, savePortfolioPlan, updateGoal,
  type Category, type GoalKind, type PortfolioGoal, type PortfolioPlan, type Subcategory,
} from '../../api'
import { KIND_COLOR, MON } from '../chartKit'
import { MIX, colorOf } from '../../exposure'
import { CardChip } from '../../cardColors'
import { useGroupColor } from '../../groupColors'
import { T, fmt } from '../../theme'
import { AdminHeader, dangerBtn, smallBtn, btn, Card, Field, input, label, Modal } from '../ui'

type GoalDraft = {
  id?: number; name: string; amount: string; year: string; kind: GoalKind; kindTouched: boolean; month: string
  every: string; endYear: string; esc: string; categoryId: string; subId: string
}
const SMALL_BELOW = 500000  // same cut-off as portfolio.default_kind
const KINDS: { id: GoalKind; label: string; hint: string }[] = [
  { id: 'large', label: 'Large goal', hint: 'Paid from investments; its chance of being funded is simulated' },
  { id: 'small', label: 'Small goal', hint: 'A phone, a trip: paid from the monthly set-aside' },
  { id: 'recurring', label: 'Yearly expense', hint: 'School fees, the trip home, insurance: repeats and rises each year' },
]
const SECTIONS: { kind: GoalKind; title: string; sub: string }[] = [
  { kind: 'large', title: 'Large goals', sub: 'paid from investments' },
  { kind: 'small', title: 'Small goals', sub: 'paid from the monthly set-aside' },
  { kind: 'recurring', title: 'Yearly expenses', sub: 'recurring, paid from the monthly set-aside' },
]
const CLOSED_KEY = 'spendlens.goalSections.closed'  // which goal sections are collapsed, per browser
const blankDraft = (kind?: GoalKind): GoalDraft => ({
  name: '', amount: '', year: String(new Date().getFullYear() + (kind === 'recurring' ? 0 : kind === 'small' ? 1 : 5)),
  kind: kind ?? 'large', kindTouched: !!kind, month: '',
  every: '12', endYear: '', esc: '0', categoryId: '', subId: '',
})
const toDraft = (g: PortfolioGoal): GoalDraft => ({
  id: g.id, name: g.name, amount: String(g.target_amount), year: String(g.target_year), kind: g.kind ?? 'large', kindTouched: true,
  month: g.target_month ? String(g.target_month) : '', every: String(g.every_months), endYear: g.end_year ? String(g.end_year) : '',
  esc: String(g.escalation_pct), categoryId: g.category_id ? String(g.category_id) : '', subId: g.subcategory_id ? String(g.subcategory_id) : '',
})
const when = (g: PortfolioGoal) => g.kind === 'recurring'
  ? `${g.every_months === 12 ? `every ${MON[(g.target_month ?? 6) - 1]}` : `every ${g.every_months} mo`} from ${g.target_year}${g.end_year ? ` to ${g.end_year}` : ''}${g.escalation_pct ? ` · +${g.escalation_pct}%/yr` : ''}`
  : `${g.target_month ? `${MON[g.target_month - 1]} ` : ''}${g.target_year}`

/** A goal's colour by how soon it is needed: amber within 5 years, sky within 12, indigo beyond. */
const urgency = (year: number) => { const n = year - new Date().getFullYear(); return n <= 5 ? '#f5b942' : n <= 12 ? '#38bdf8' : '#7c74ff' }

export default function PortfolioPlanTool() {
  const [plan, setPlan] = useState<PortfolioPlan | null>(null)
  const groupColor = useGroupColor(plan ? plan.groups : [])
  const [targets, setTargets] = useState<Record<string, string>>({})
  const [ret, setRet] = useState<Record<string, { ret: string; vol: string }>>({})
  const [stepup, setStepup] = useState('5')
  const [mixT, setMixT] = useState<Record<string, string>>({})
  const [mixR, setMixR] = useState<Record<string, string>>({})
  const [mixYears, setMixYears] = useState('15')
  const [reachYears, setReachYears] = useState('5')
  const [goal, setGoal] = useState<GoalDraft | null>(null)
  const [cats, setCats] = useState<Category[]>([])
  const [subs, setSubs] = useState<Subcategory[]>([])
  const [msg, setMsg] = useState<{ text: string; error?: boolean } | null>(null)
  const [closed, setClosed] = useState<Partial<Record<GoalKind, boolean>>>(() => {
    try { return JSON.parse(localStorage.getItem(CLOSED_KEY) ?? '{}') } catch { return {} }
  })
  const toggle = (k: GoalKind) => setClosed(c => {
    const next = { ...c, [k]: !c[k] }
    try { localStorage.setItem(CLOSED_KEY, JSON.stringify(next)) } catch { /* private window: just not remembered */ }
    return next
  })

  const load = useCallback(async () => {
    try {
      const p = await getPortfolioPlan()
      setPlan(p)
      setTargets(Object.fromEntries(p.groups.map(g => [g, String(p.targets[g] ?? 0)])))
      setRet(Object.fromEntries(p.groups.map(g => {
        const a = p.assumptions.groups[g] ?? p.assumptions.groups.Others ?? { ret: 8, vol: 10 }
        return [g, { ret: String(a.ret), vol: String(a.vol) }]
      })))
      setStepup(String(p.assumptions.stepup))
      const m = await getMix()
      setMixT(Object.fromEntries(MIX.map(e => [e, String(m.targets[e])])))
      setMixR(Object.fromEntries(MIX.map(e => [e, String(m.returns[e])])))
      setMixYears(String(m.years))
      setReachYears(String(m.reach_years))
    } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
  }, [])
  useEffect(() => { load() }, [load])
  // Categories for linking a yearly expense to what is actually spent; loaded once the form needs them.
  const needCats = goal?.kind === 'recurring'
  useEffect(() => {
    if (!needCats || cats.length) return
    Promise.all([getCategories(), getSubcategories()]).then(([c, sb]) => { setCats(c.filter(x => x.status !== 'archived')); setSubs(sb) }).catch(() => {})
  }, [needCats, cats.length])

  if (!plan) return <div style={{ color: msg?.error ? T.negative : T.muted }}>{msg?.text ?? 'Loading…'}</div>

  const mixSum = MIX.reduce((s, e) => s + (Number(mixT[e]) || 0), 0)
  const sum = Object.values(targets).reduce((s, v) => s + (Number(v) || 0), 0)
  const run = async (p: Promise<unknown>, ok: string) => {
    try { await p; setMsg({ text: ok }); await load() } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
  }
  const saveTargets = () => run(savePortfolioPlan({ targets: Object.fromEntries(Object.entries(targets).map(([g, v]) => [g, Number(v) || 0])) }), 'Target allocation saved')
  const saveAssumptions = () => run(savePortfolioPlan({
    assumptions: { stepup: Number(stepup) || 0, groups: Object.fromEntries(Object.entries(ret).map(([g, v]) => [g, { ret: Number(v.ret) || 0, vol: Number(v.vol) || 0 }])) },
  }), 'Return assumptions saved')
  const saveMix = () => run(saveMixPlan({
    targets: Object.fromEntries(MIX.map(e => [e, Number(mixT[e]) || 0])) as never, returns: Object.fromEntries(MIX.map(e => [e, Number(mixR[e]) || 0])) as never,
    years: Number(mixYears) || 15, reach_years: Number(reachYears) || 5,
  }), 'Target mix saved')
  const saveGoal = async () => {
    if (!goal) return
    const rec = goal.kind === 'recurring'
    const body: Omit<PortfolioGoal, 'id'> = {
      name: goal.name, target_amount: Number(goal.amount), target_year: Number(goal.year), kind: goal.kind,
      target_month: goal.month ? Number(goal.month) : null,
      every_months: rec ? Number(goal.every) || 12 : 12, end_year: rec && goal.endYear ? Number(goal.endYear) : null,
      escalation_pct: rec ? Number(goal.esc) || 0 : 0,
      category_id: rec && goal.categoryId ? Number(goal.categoryId) : null, subcategory_id: rec && goal.subId ? Number(goal.subId) : null,
    }
    await run(goal.id ? updateGoal(goal.id, body) : addGoal(body), 'Goal saved')
    setGoal(null)
  }
  const cell: React.CSSProperties = { padding: '8px 10px', fontSize: 13 }
  const num = { ...input, width: 80, textAlign: 'right' as const }

  return (
    <div>
      <AdminHeader title="Goals & targets" hint="Goals, target allocation and the return assumptions behind the Portfolio dashboard. The emergency fund is kept out of goal money." />
      {msg && <div style={{ fontSize: 12.5, marginBottom: 12, color: msg.error ? T.negative : T.positive }}>{msg.text}</div>}

      <Card style={{ padding: 0, overflow: 'hidden', marginBottom: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', padding: '12px 16px' }}>
          <div style={{ flex: 1, fontWeight: 700, fontSize: 14 }}>Goals &amp; yearly expenses <span style={{ color: T.muted, fontWeight: 400 }}>· amounts in the year they are needed</span></div>
          <button style={smallBtn} onClick={() => {
            const allClosed = SECTIONS.every(s => closed[s.kind])
            const next = Object.fromEntries(SECTIONS.map(s => [s.kind, !allClosed]))
            setClosed(next)
            try { localStorage.setItem(CLOSED_KEY, JSON.stringify(next)) } catch { /* not remembered */ }
          }}>{SECTIONS.every(s => closed[s.kind]) ? 'Expand all' : 'Collapse all'}</button>
        </div>
        {SECTIONS.map(sec => {
          const rows = plan.goals.filter(g => (g.kind ?? 'large') === sec.kind)  // a goal from before goal kinds counts as large
          const isClosed = !!closed[sec.kind]
          const total = rows.reduce((s, g) => s + g.target_amount * (sec.kind === 'recurring' ? 12 / (g.every_months || 12) : 1), 0)
          return (
            <div key={sec.kind}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 16px 6px 8px', borderTop: `1px solid ${T.hairline}`, background: T.surface2 }}>
                <button onClick={() => toggle(sec.kind)} aria-expanded={!isClosed} style={{
                  ...label, flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 8, background: 'none', border: 'none', cursor: 'pointer',
                  padding: '4px 8px', textAlign: 'left', flexWrap: 'wrap',
                }}>
                  <span style={{ display: 'inline-block', width: 10, transition: 'transform .15s', transform: isClosed ? 'rotate(-90deg)' : 'none' }}>▾</span>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: KIND_COLOR[sec.kind] }} />
                  {sec.title}
                  <span style={{ textTransform: 'none', letterSpacing: 0, fontWeight: 400 }}>· {sec.sub}</span>
                  <span style={{ marginLeft: 'auto', textTransform: 'none', letterSpacing: 0, color: T.text, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                    {rows.length} · {fmt(total)}{sec.kind === 'recurring' ? ' a year' : ''}
                  </span>
                </button>
                <button style={smallBtn} onClick={() => setGoal(blankDraft(sec.kind))}>+ Add</button>
              </div>
              {!isClosed && rows.map(g => (
                <div key={g.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '9px 16px', borderTop: `1px solid ${T.hairline}`, fontSize: 13, flexWrap: 'wrap' }}>
                  <span style={{ flex: 1, minWidth: 140, fontWeight: 600 }}>{g.name}</span>
                  {g.kind !== 'recurring' && <span style={{ fontSize: 11, fontWeight: 600, padding: '2px 9px', borderRadius: 10, color: urgency(g.target_year), background: `${urgency(g.target_year)}22` }}>in {Math.max(0, g.target_year - new Date().getFullYear())} yrs</span>}
                  <span style={{ color: T.muted }}>{when(g)}</span>
                  <span style={{ width: 90, textAlign: 'right' }}>{fmt(g.target_amount)}</span>
                  <button style={smallBtn} onClick={() => setGoal(toDraft(g))}>Edit</button>
                  <button style={dangerBtn} onClick={() => run(deleteGoal(g.id), 'Removed')}>Delete</button>
                </div>
              ))}
              {!isClosed && !rows.length && <div style={{ padding: '4px 16px 10px', color: T.muted, fontSize: 12.5 }}>None yet.</div>}
            </div>
          )
        })}
      </Card>

      <Card style={{ marginBottom: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 10 }}>
          <div style={{ flex: 1, fontWeight: 700, fontSize: 14 }}>Target mix <span style={{ color: Math.abs(mixSum - 100) > 0.5 ? T.negative : T.muted, fontWeight: 400 }}>· Equity / Gold / Debt · {mixSum}% of 100%</span></div>
          <button style={{ ...btn(true), opacity: Math.abs(mixSum - 100) > 0.5 ? 0.5 : 1 }} disabled={Math.abs(mixSum - 100) > 0.5} onClick={saveMix}>Save</button>
        </div>
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead><tr>{['', 'Target share', 'Expected return (yearly)'].map((h, i) => <th key={i} style={{ ...label, ...cell, textAlign: i ? 'right' : 'left' }}>{h}</th>)}</tr></thead>
          <tbody>
            {MIX.map(e => (
              <tr key={e} style={{ borderTop: `1px solid ${T.hairline}` }}>
                <td style={cell}><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 3, background: colorOf(e), marginRight: 9 }} />{e}{e === 'Debt' ? ' (incl. cash)' : ''}</td>
                <td style={{ ...cell, textAlign: 'right' }}><input style={num} type="number" value={mixT[e] ?? ''} onChange={x => setMixT({ ...mixT, [e]: x.target.value })} />%</td>
                <td style={{ ...cell, textAlign: 'right' }}><input style={num} type="number" value={mixR[e] ?? ''} onChange={x => setMixR({ ...mixR, [e]: x.target.value })} />%</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 14, fontSize: 13 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span>Reach this mix within</span><input style={num} type="number" value={reachYears} onChange={e => setReachYears(e.target.value)} /><span>years</span></label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span>Forecast for</span><input style={num} type="number" value={mixYears} onChange={e => setMixYears(e.target.value)} /><span>years</span></label>
        </div>
        <p style={{ color: T.muted, fontSize: 12, marginTop: 10 }}>Drives the Asset Mix tab: it shows how to re-split your monthly SIPs (nothing is sold) to reach this mix, and when. A longer window means a gentler change.</p>
      </Card>

      <Card style={{ marginBottom: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 10 }}>
          <div style={{ flex: 1, fontWeight: 700, fontSize: 14 }}>Target allocation <span style={{ color: Math.abs(sum - 100) > 0.5 ? T.negative : T.muted, fontWeight: 400 }}>· {sum}% of 100%</span></div>
          <button style={btn(true)} onClick={saveTargets}>Save</button>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: 10 }}>
          {plan.groups.map(g => (
            <label key={g} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
              <span style={{ flex: 1, display: 'inline-flex', alignItems: 'center' }}><CardChip color={groupColor(g)} name={g} size={18} />{g}</span>
              <input style={num} type="number" value={targets[g] ?? ''} onChange={e => setTargets({ ...targets, [g]: e.target.value })} />%
            </label>
          ))}
        </div>
      </Card>

      <Card>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 10 }}>
          <div style={{ flex: 1, fontWeight: 700, fontSize: 14 }}>Return assumptions <span style={{ color: T.muted, fontWeight: 400 }}>· yearly %</span></div>
          <button style={btn(true)} onClick={saveAssumptions}>Save</button>
        </div>
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead><tr>{['Group', 'Expected return', 'Volatility'].map((h, i) => <th key={h} style={{ ...label, ...cell, textAlign: i ? 'right' : 'left' }}>{h}</th>)}</tr></thead>
          <tbody>
            {plan.groups.map(g => (
              <tr key={g} style={{ borderTop: `1px solid ${T.hairline}` }}>
                <td style={cell}><span style={{ display: 'inline-flex', alignItems: 'center' }}><CardChip color={groupColor(g)} name={g} size={18} />{g}</span></td>
                <td style={{ ...cell, textAlign: 'right' }}><input style={num} type="number" value={ret[g]?.ret ?? ''} onChange={e => setRet({ ...ret, [g]: { ...ret[g], ret: e.target.value } })} /></td>
                <td style={{ ...cell, textAlign: 'right' }}><input style={num} type="number" value={ret[g]?.vol ?? ''} onChange={e => setRet({ ...ret, [g]: { ...ret[g], vol: e.target.value } })} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, marginTop: 14 }}>
          <span>SIPs rise every year by</span><input style={num} type="number" value={stepup} onChange={e => setStepup(e.target.value)} />%
        </label>
        <p style={{ color: T.muted, fontSize: 12, marginTop: 10 }}>Volatility is how far a year can swing from the expected return. Higher volatility widens the shaded range.</p>
      </Card>

      {goal && (() => {
        const rec = goal.kind === 'recurring'
        const setAmount = (v: string) => setGoal({
          ...goal, amount: v, kind: goal.kindTouched || rec ? goal.kind : Number(v) >= SMALL_BELOW ? 'large' : 'small',
        })
        const catSubs = subs.filter(x => String(x.category_id) === goal.categoryId && x.status !== 'archived')
        const valid = goal.name.trim() && Number(goal.amount) > 0 && Number(goal.year) > 2000
          && (!rec || !goal.endYear || Number(goal.endYear) >= Number(goal.year))
        return (
          <Modal title={goal.id ? 'Edit' : 'Add a goal or yearly expense'} onClose={() => setGoal(null)}>
            <Field name="Kind">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 6 }}>
                {KINDS.map(k => (
                  <button key={k.id} onClick={() => setGoal({ ...goal, kind: k.id, kindTouched: true })} aria-pressed={goal.kind === k.id} title={k.hint}
                    style={{ ...btn(goal.kind === k.id), padding: '7px 6px', fontSize: 12.5, borderColor: goal.kind === k.id ? KIND_COLOR[k.id] : undefined }}>{k.label}</button>
                ))}
              </div>
              <div style={{ fontSize: 11.5, color: T.muted, marginTop: 5 }}>
                {KINDS.find(k => k.id === goal.kind)?.hint}{!goal.kindTouched && !rec ? ' · set from the amount (₹5L or more is large) until you pick one' : ''}
              </div>
            </Field>
            <Field name="Name"><input style={input} autoFocus value={goal.name} placeholder={rec ? 'Child school fee' : 'Car'} onChange={e => setGoal({ ...goal, name: e.target.value })} /></Field>
            <Field name={rec ? 'Amount each time (₹, in the first year)' : 'Amount needed (₹, in that year)'}>
              <input style={input} type="number" value={goal.amount} onChange={e => setAmount(e.target.value)} />
            </Field>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <Field name={rec ? 'First due · month' : 'Month (optional)'}>
                <select style={input} value={goal.month} onChange={e => setGoal({ ...goal, month: e.target.value })}>
                  <option value="">{rec ? 'June' : 'Any (June)'}</option>
                  {MON.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
                </select>
              </Field>
              <Field name={rec ? 'First due · year' : 'Year needed'}><input style={input} type="number" value={goal.year} onChange={e => setGoal({ ...goal, year: e.target.value })} /></Field>
            </div>
            {rec && <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10 }}>
                <Field name="Every (months)"><input style={input} type="number" value={goal.every} onChange={e => setGoal({ ...goal, every: e.target.value })} /></Field>
                <Field name="Rises each year (%)"><input style={input} type="number" value={goal.esc} onChange={e => setGoal({ ...goal, esc: e.target.value })} /></Field>
                <Field name="Until year (optional)"><input style={input} type="number" value={goal.endYear} placeholder="no end" onChange={e => setGoal({ ...goal, endYear: e.target.value })} /></Field>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <Field name="Spent from category (optional)">
                  <select style={input} value={goal.categoryId} onChange={e => setGoal({ ...goal, categoryId: e.target.value, subId: '' })}>
                    <option value="">Not linked</option>
                    {cats.map(c => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
                  </select>
                </Field>
                <Field name="Sub-category (optional)">
                  <select style={input} value={goal.subId} disabled={!goal.categoryId || !catSubs.length} onChange={e => setGoal({ ...goal, subId: e.target.value })}>
                    <option value="">Whole category</option>
                    {catSubs.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}
                  </select>
                </Field>
              </div>
              <div style={{ fontSize: 11.5, color: T.muted, marginTop: -4, marginBottom: 8 }}>Linked expenses are compared with the plan on the Goals &amp; Forecast tab.</div>
            </>}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 6 }}>
              <button style={btn()} onClick={() => setGoal(null)}>Cancel</button>
              <button style={btn(true)} disabled={!valid} onClick={saveGoal}>Save</button>
            </div>
          </Modal>
        )
      })()}
    </div>
  )
}
