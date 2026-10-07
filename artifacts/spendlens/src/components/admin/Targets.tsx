import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getBudgetHistory, getCategories, getCategoryTargets, setBudget, setCategoryTarget,
  type BudgetEntry, type Category, type TargetEntry,
} from '../../api'
import { currentMonth, monthLabel } from '../../months'
import { T, fmtFull } from '../../theme'
import { AdminHeader, btn, Card, input, label } from '../ui'

const budgetFor = (history: BudgetEntry[], month: string): BudgetEntry =>
  [...history].filter(h => h.from_month <= month).sort((a, b) => b.from_month.localeCompare(a.from_month))[0] ?? history[0]

export default function Targets() {
  const [month, setMonth] = useState(currentMonth())
  const [cats, setCats] = useState<Category[]>([])
  const [history, setHistory] = useState<BudgetEntry[]>([])
  const [targets, setTargets] = useState<Record<number, number>>({})
  const [income, setIncome] = useState(0)
  const [savings, setSavings] = useState(0)
  const [orig, setOrig] = useState<{ targets: Record<number, number>; income: number; savings: number } | null>(null)
  const [msg, setMsg] = useState<{ text: string; error?: boolean } | null>(null)
  const [saving, setSaving] = useState(false)
  const [balId, setBalId] = useState<number | null>(null)   // category that absorbs changes so that targets + saving stay at 100%
  const [histCat, setHistCat] = useState<number | null>(null)
  const [histRows, setHistRows] = useState<TargetEntry[]>([])

  const load = useCallback(async () => {
    if (!month) return
    try {
      const [c, h] = await Promise.all([getCategories(month), getBudgetHistory()])
      const shown = c.filter(x => !x.archived)
      const t = Object.fromEntries(shown.map(x => [x.id, x.target_pct]))
      const b = budgetFor(h, month)
      setBalId(prev => (prev != null && shown.some(x => x.id === prev) ? prev : shown.find(x => /misc/i.test(x.name))?.id ?? null))
      setCats(shown); setHistory(h); setTargets(t); setIncome(b.income); setSavings(b.savings_amount)
      setOrig({ targets: t, income: b.income, savings: b.savings_amount })
    } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
  }, [month])
  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (histCat == null) { setHistRows([]); return }
    getCategoryTargets(histCat).then(setHistRows).catch(() => setHistRows([]))
  }, [histCat, history, orig])

  const changed = useMemo(
    () => orig ? cats.filter(c => targets[c.id] !== orig.targets[c.id]) : [],
    [cats, targets, orig])
  const budgetChanged = !!orig && (income !== orig.income || savings !== orig.savings)
  const dirty = changed.length > 0 || budgetChanged

  const sum = Math.round(cats.reduce((x, c) => x + (targets[c.id] ?? 0), 0) * 100) / 100   // expense target, % of salary
  const cap = income - savings
  const savingsPct = income ? (savings / income) * 100 : 0
  const total = sum + savingsPct
  const unallocated = 100 - total
  const over = unallocated < -0.005 || savings > income
  const balanced = Math.abs(unallocated) <= 0.005
  const r2 = (v: number) => Math.round(v * 100) / 100
  const r4 = (v: number) => Math.round(v * 10000) / 10000
  // Linked fields: the one being typed in keeps its raw text; its partner is derived from it.
  const [draft, setDraft] = useState<{ key: string; text: string } | null>(null)
  const shown = (key: string, derived: number) => (draft?.key === key ? draft.text : String(derived))
  const clampPct = (v: number) => Math.min(100, Math.max(0, v))   // full precision: a typed ₹ amount must round-trip exactly
  // Saving is fixed: whatever changes (a target, salary or saving), the balancing category takes up the difference.
  const rebalance = (t: Record<number, number>, inc: number, sav: number) => {
    if (balId == null) return t
    const others = cats.reduce((x, c) => (c.id === balId ? x : x + (t[c.id] ?? 0)), 0)
    const room = 100 - (inc ? (sav / inc) * 100 : 0) - others
    return { ...t, [balId]: Math.max(0, Math.round(room * 1e8) / 1e8) }
  }
  const applyBudget = (inc: number, sav: number) => { setIncome(inc); setSavings(sav); setTargets(t => rebalance(t, inc, sav)) }
  const setTargetPct = (id: number, pct: number) => {
    const next = { ...targets, [id]: clampPct(pct) }
    setTargets(id === balId ? next : rebalance(next, income, savings))
  }
  const setTargetAmt = (id: number, amt: number) => setTargetPct(id, income ? (amt / income) * 100 : 0)
  const money = (v: string) => Math.max(0, Math.round(parseFloat(v) || 0))   // whole rupees

  const save = async () => {
    setSaving(true); setMsg(null)
    try {
      await Promise.all([
        ...changed.map(c => setCategoryTarget(c.id, month, targets[c.id])),
        ...(budgetChanged ? [setBudget({ from_month: month, income, savings_amount: savings })] : []),
      ])
      await load()
      setMsg({ text: `Saved. New values apply from ${monthLabel(month)} onward; earlier months are unchanged.` })
    } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
    setSaving(false)
  }

  const th: React.CSSProperties = { ...label, padding: '10px 14px', textAlign: 'left', background: T.surface2 }
  const td: React.CSSProperties = { padding: '6px 14px', fontSize: 13 }

  return (
    <div>
      <AdminHeader title="Targets & Budget" hint="Edit a target as % or ₹ a month and the other follows. Changes apply from the chosen month; earlier months stay as they were." />

      <label style={{ display: 'inline-block', marginBottom: 18 }}>
        <div style={{ ...label, marginBottom: 5 }}>Applies from</div>
        <input style={{ ...input, width: 170 }} type="month" value={month} onChange={e => e.target.value && setMonth(e.target.value)} />
      </label>

      <Card style={{ marginBottom: 20 }}>
        <div style={{ ...label, marginBottom: 14 }}>Salary &amp; savings · valid in {monthLabel(month)}</div>
        <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <label>
            <div style={{ ...label, marginBottom: 5 }}>Total salary (₹)</div>
            <input style={{ ...input, width: 160 }} type="number" min={0} value={shown('b:income', income)}
              onChange={e => { setDraft({ key: 'b:income', text: e.target.value }); applyBudget(money(e.target.value), savings) }}
              onBlur={() => setDraft(null)} />
          </label>
          <label>
            <div style={{ ...label, marginBottom: 5 }}>Total saving (₹)</div>
            <input style={{ ...input, width: 160 }} type="number" min={0} value={shown('b:savings', savings)}
              onChange={e => { setDraft({ key: 'b:savings', text: e.target.value }); applyBudget(income, Math.min(income, money(e.target.value))) }}
              onBlur={() => setDraft(null)} />
          </label>
          <label title="Linked to total saving">
            <div style={{ ...label, marginBottom: 5 }}>Saving (%)</div>
            <input style={{ ...input, width: 100 }} type="number" min={0} max={100} step={0.1}
              value={shown('s:pct', r4(savingsPct))}
              onChange={e => { setDraft({ key: 's:pct', text: e.target.value }); applyBudget(income, Math.min(income, Math.round((income * clampPct(parseFloat(e.target.value) || 0)) / 100))) }}
              onBlur={() => setDraft(null)} />
          </label>
          <label title="Salary minus total saving. Editing it changes total saving.">
            <div style={{ ...label, marginBottom: 5 }}>Budget cap (₹)</div>
            <input style={{ ...input, width: 160 }} type="number" min={0} value={shown('b:cap', cap)}
              onChange={e => { setDraft({ key: 'b:cap', text: e.target.value }); applyBudget(income, Math.max(0, income - Math.min(income, money(e.target.value)))) }}
              onBlur={() => setDraft(null)} />
          </label>
          <label title="Total saving stays fixed. When you change a target, salary or saving, this category absorbs the difference so everything adds up to 100%.">
            <div style={{ ...label, marginBottom: 5 }}>Balancing category</div>
            <select style={{ ...input, width: 190 }} value={balId ?? ''} onChange={e => setBalId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">None (manual)</option>
              {cats.map(c => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
            </select>
          </label>
        </div>

        <div style={{ display: 'flex', height: 10, borderRadius: 5, overflow: 'hidden', background: T.surface2, margin: '18px 0 10px' }}>
          <div style={{ width: `${Math.min(100, savingsPct)}%`, background: T.accent2 }} title="Savings" />
          {cats.filter(c => (targets[c.id] ?? 0) > 0).map(c => (
            <div key={c.id} style={{ width: `${Math.max(0, (targets[c.id] ?? 0))}%`, background: c.color || T.accent, borderLeft: `1px solid ${T.surface}` }} title={`${c.name} ${targets[c.id]}%`} />
          ))}
        </div>
        <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', fontSize: 12.5 }}>
          <span><span style={{ color: T.accent2 }}>●</span> Saving {r2(savingsPct)}% · {fmtFull(savings)}</span>
          <span><span style={{ color: T.accent }}>●</span> Expense target {sum}% · {fmtFull(Math.round((income * sum) / 100))}</span>
          <span style={{ fontWeight: 600, color: over ? T.negative : balanced ? T.positive : T.warn }}>
            {over ? (balId != null ? `Over by ${r2(-unallocated)}% - even with the balancing category at 0%, reduce another target or the saving` : `Over by ${r2(-unallocated)}% - reduce targets or savings`)
              : balanced ? 'Balanced: expense target + saving = 100% of salary'
              : `Unallocated ${r2(unallocated)}% · ${fmtFull(Math.round((income * unallocated) / 100))}`}
          </span>
        </div>
      </Card>

      <Card style={{ padding: 0, overflow: 'hidden', marginBottom: 20 }}>
        <div style={{ padding: '14px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={label}>Category targets (% of income)</span>
          <span style={{ fontSize: 12, color: T.muted }}>Expense target = {sum}% of salary</span>
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead><tr><th style={th}>Category</th><th style={{ ...th, textAlign: 'right', width: 130 }}>Target %</th><th style={{ ...th, textAlign: 'right', width: 160 }}>₹ / month</th></tr></thead>
          <tbody>
            {cats.map(c => (
              <tr key={c.id} style={{ borderTop: `1px solid ${T.hairline}` }}>
                <td style={td}>
                  <span style={{ display: 'inline-block', width: 9, height: 9, borderRadius: 3, background: c.color || T.accent, marginRight: 9 }} />{c.icon} {c.name}{c.id === balId && <span style={{ color: T.muted, fontSize: 11 }} title="Absorbs changes made to other targets or to saving"> · balancing</span>}
                </td>
                <td style={{ ...td, textAlign: 'right' }}>
                  <input style={{ ...input, width: 90, textAlign: 'right', borderColor: targets[c.id] !== orig?.targets[c.id] ? T.accent : T.border }} type="number" min={0} max={100} step={0.1}
                    value={shown(`t:${c.id}:pct`, r4(targets[c.id] ?? 0))}
                    onChange={e => { setDraft({ key: `t:${c.id}:pct`, text: e.target.value }); setTargetPct(c.id, parseFloat(e.target.value) || 0) }}
                    onBlur={() => setDraft(null)} />
                </td>
                <td style={{ ...td, textAlign: 'right' }}>
                  <input style={{ ...input, width: 120, textAlign: 'right', borderColor: targets[c.id] !== orig?.targets[c.id] ? T.accent : T.border }} type="number" min={0} step={100}
                    value={shown(`t:${c.id}:amt`, Math.round((income * (targets[c.id] ?? 0)) / 100))}
                    onChange={e => { setDraft({ key: `t:${c.id}:amt`, text: e.target.value }); setTargetAmt(c.id, parseFloat(e.target.value) || 0) }}
                    onBlur={e => { setTargetAmt(c.id, Math.round(parseFloat(e.target.value) || 0)); setDraft(null) }} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 28, flexWrap: 'wrap' }}>
        <button style={{ ...btn(true), opacity: dirty && !saving && !over ? 1 : 0.5 }} disabled={!dirty || saving || over} onClick={save}>
          {saving ? 'Saving…' : `Save from ${monthLabel(month)}`}
        </button>
        <button style={btn()} disabled={!dirty || saving} onClick={load}>Reset</button>
        {over && <span style={{ fontSize: 12.5, color: T.negative }}>Can't save: targets + saving exceed salary by {fmtFull(Math.round((income * -unallocated) / 100))}. Lower a target or the saving, or pick a balancing category.</span>}
        {msg && <span style={{ fontSize: 12.5, color: msg.error ? T.negative : T.positive }}>{msg.text}</span>}
      </div>

      <Card>
        <div style={{ ...label, marginBottom: 12 }}>Change history</div>
        <div style={{ fontSize: 12.5, color: T.muted, marginBottom: 8 }}>Salary &amp; saving</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 18 }}>
          {history.map(h => (
            <span key={h.from_month} style={{ fontSize: 12, background: T.surface2, border: `1px solid ${T.border}`, borderRadius: 6, padding: '4px 9px' }}>
              {h.from_month === '0000-00' ? 'Initially' : `From ${monthLabel(h.from_month)}`}: {fmtFull(h.income)} · 
            </span>
          ))}
        </div>
        <div style={{ fontSize: 12.5, color: T.muted, marginBottom: 8 }}>Category target</div>
        <select style={{ ...input, width: 'auto', marginBottom: 10 }} value={histCat ?? ''} onChange={e => setHistCat(e.target.value ? Number(e.target.value) : null)}>
          <option value="">Choose category…</option>
          {cats.map(c => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
        </select>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {histRows.map(r => (
            <span key={r.from_month} style={{ fontSize: 12, background: T.surface2, border: `1px solid ${T.border}`, borderRadius: 6, padding: '4px 9px' }}>
              {r.from_month === '0000-00' ? 'Initially' : `From ${monthLabel(r.from_month)}`}: {r.target_pct}%
            </span>
          ))}
        </div>
      </Card>
    </div>
  )
}
