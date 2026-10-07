import { useCallback, useEffect, useState } from 'react'
import { addGoal, deleteGoal, getMix, getPortfolioPlan, saveMixPlan, savePortfolioPlan, updateGoal, type PortfolioPlan } from '../../api'
import { MIX, colorOf } from '../../exposure'
import { CardChip } from '../../cardColors'
import { useGroupColor } from '../../groupColors'
import { T, fmt } from '../../theme'
import { AdminHeader, dangerBtn, smallBtn, btn, Card, Field, input, label, Modal } from '../ui'

type GoalDraft = { id?: number; name: string; amount: string; year: string }

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
  const [msg, setMsg] = useState<{ text: string; error?: boolean } | null>(null)

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
    const body = { name: goal.name, target_amount: Number(goal.amount), target_year: Number(goal.year) }
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
          <div style={{ flex: 1, fontWeight: 700, fontSize: 14 }}>Goals <span style={{ color: T.muted, fontWeight: 400 }}>· amounts in the year they are needed</span></div>
          <button style={btn(true)} onClick={() => setGoal({ name: '', amount: '', year: String(new Date().getFullYear() + 5) })}>+ Add goal</button>
        </div>
        {plan.goals.map(g => (
          <div key={g.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '9px 16px', borderTop: `1px solid ${T.hairline}`, fontSize: 13 }}>
            <span style={{ flex: 1, fontWeight: 600 }}>{g.name}</span>
            <span style={{ fontSize: 11, fontWeight: 600, padding: '2px 9px', borderRadius: 10, color: urgency(g.target_year), background: `${urgency(g.target_year)}22` }}>in {Math.max(0, g.target_year - new Date().getFullYear())} yrs</span>
            <span style={{ color: T.muted }}>{g.target_year}</span>
            <span style={{ width: 90, textAlign: 'right' }}>{fmt(g.target_amount)}</span>
            <button style={smallBtn} onClick={() => setGoal({ id: g.id, name: g.name, amount: String(g.target_amount), year: String(g.target_year) })}>Edit</button>
            <button style={dangerBtn} onClick={() => run(deleteGoal(g.id), 'Goal removed')}>Delete</button>
          </div>
        ))}
        {!plan.goals.length && <div style={{ padding: '10px 16px', color: T.muted, fontSize: 13 }}>No goals yet.</div>}
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

      {goal && (
        <Modal title={goal.id ? 'Edit goal' : 'New goal'} onClose={() => setGoal(null)}>
          <Field name="Name"><input style={input} autoFocus value={goal.name} onChange={e => setGoal({ ...goal, name: e.target.value })} /></Field>
          <Field name="Amount needed (₹, in that year)"><input style={input} type="number" value={goal.amount} onChange={e => setGoal({ ...goal, amount: e.target.value })} /></Field>
          <Field name="Year needed"><input style={input} type="number" value={goal.year} onChange={e => setGoal({ ...goal, year: e.target.value })} /></Field>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 6 }}>
            <button style={btn()} onClick={() => setGoal(null)}>Cancel</button>
            <button style={btn(true)} disabled={!goal.name.trim() || !(Number(goal.amount) > 0) || !(Number(goal.year) > 2000)} onClick={saveGoal}>Save</button>
          </div>
        </Modal>
      )}
    </div>
  )
}
