import { useCallback, useEffect, useState } from 'react'
import {
  createHoldingGroup, deleteHoldingGroup, getHoldingGroups, getHoldings, getSipLog, moveHoldings, renameHoldingGroup, setHoldingSip,
  type Holding, type HoldingGroups, type SipLogRow,
} from '../../api'
import { T, fmt } from '../../theme'
import { AdminHeader, dangerBtn, smallBtn, btn, Card, Field, input, label, Modal } from '../ui'
import { CardChip, paletteAt } from '../../cardColors'

export default function HoldingGroupsTool() {
  const [data, setData] = useState<HoldingGroups>({ groups: [], others: { count: 0, present: 0 } })
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [log, setLog] = useState<SipLogRow[]>([])
  const [open, setOpen] = useState<string | null>(null)
  const [msg, setMsg] = useState<{ text: string; error?: boolean } | null>(null)
  const [editing, setEditing] = useState<{ id: number; name: string } | 'new' | null>(null)
  const [deleting, setDeleting] = useState<{ id: number; name: string; count: number } | null>(null)
  const [picked, setPicked] = useState<Set<number>>(new Set())
  const [target, setTarget] = useState('')

  const load = useCallback(async () => {
    try {
      const [g, h, l] = await Promise.all([getHoldingGroups(), getHoldings(), getSipLog()])
      setData(g); setHoldings(h); setLog(l)
    } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
  }, [])
  useEffect(() => { load() }, [load])

  const run = async (p: Promise<unknown>, ok?: string) => {
    try { await p; setMsg(ok ? { text: ok } : null); await load() } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
  }

  const others = holdings.filter(h => !h.grp)
  const togglePick = (id: number) => setPicked(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n })
  const moveTo = (ids: number[], grp: string) => {
    setPicked(new Set())
    run(moveHoldings(ids, grp), `${ids.length} holding${ids.length > 1 ? 's' : ''} moved to ${grp}`)
  }

  return (
    <div>
      <AdminHeader title="Holding groups" hint="Groups organise the Holdings page. Deleting a group never deletes holdings: they move to Others."
        action={<button style={btn(true)} onClick={() => setEditing('new')}>+ Add group</button>} />
      {msg && <div style={{ fontSize: 12.5, marginBottom: 12, color: msg.error ? T.negative : T.positive }}>{msg.text}</div>}

      {others.length > 0 && (
        <Card style={{ padding: 0, overflow: 'hidden', marginBottom: 18, border: `1px solid ${T.warn}55` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px', flexWrap: 'wrap' }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, fontSize: 14 }}>Others <span style={{ color: T.muted, fontWeight: 400 }}>· needs a group</span></div>
              <div style={{ fontSize: 11.5, color: T.muted, marginTop: 2 }}>{others.length} holding{others.length > 1 ? 's' : ''} · {fmt(data.others.present)}</div>
            </div>
            <select style={{ ...input, width: 'auto' }} value={target} onChange={e => setTarget(e.target.value)}>
              <option value="">Move selected to…</option>
              {data.groups.map(g => <option key={g.id}>{g.name}</option>)}
            </select>
            <button style={{ ...btn(true), opacity: picked.size && target ? 1 : 0.5 }} disabled={!picked.size || !target}
              onClick={() => moveTo([...picked], target)}>Move {picked.size || ''}</button>
          </div>
          {others.map(h => (
            <label key={h.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '9px 16px', borderTop: `1px solid ${T.hairline}`, cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={picked.has(h.id)} onChange={() => togglePick(h.id)} />
              <span style={{ flex: 1, minWidth: 0 }}>{h.name}</span>
              <span style={{ color: T.muted }}>{fmt(h.present)}</span>
            </label>
          ))}
        </Card>
      )}

      <div style={{ ...label, marginBottom: 8 }}>Groups</div>
      <Card style={{ padding: 0, overflow: 'hidden' }}>
        {data.groups.length === 0 && <div style={{ padding: 20, color: T.muted, fontSize: 13 }}>No groups yet.</div>}
        {data.groups.map((g, i) => {
          const members = holdings.filter(h => h.grp === g.name)
          const sipTotal = members.reduce((t, h) => t + (h.sip_day ? h.sip_amount : 0), 0)
          const expanded = open === g.name
          return (
            <div key={g.id} style={{ borderTop: i ? `1px solid ${T.hairline}` : undefined }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 16px' }}>
                <div onClick={() => setOpen(expanded ? null : g.name)} style={{ flex: 1, minWidth: 0, cursor: 'pointer' }}>
                  <div style={{ fontWeight: 600, fontSize: 13.5, display: 'flex', alignItems: 'center' }}>
                    <span style={{ display: 'inline-block', width: 18, color: T.muted, fontSize: 10 }}>{expanded ? '▼' : '▶'}</span>
                    <CardChip color={paletteAt(i)} name={g.name} size={20} />{g.name}
                  </div>
                  <div style={{ height: 4, borderRadius: 2, background: T.surface2, margin: '7px 0 0 18px', maxWidth: 360 }} title={`${data.groups.reduce((t, x) => t + x.present, 0) ? Math.round((g.present / data.groups.reduce((t, x) => t + x.present, 0)) * 100) : 0}% of the value in groups`}>
                    <div style={{ height: '100%', borderRadius: 2, background: paletteAt(i), width: `${data.groups.reduce((t, x) => t + x.present, 0) ? (g.present / data.groups.reduce((t, x) => t + x.present, 0)) * 100 : 0}%` }} />
                  </div>
                  <div style={{ fontSize: 11.5, color: T.muted, marginTop: 2, paddingLeft: 18 }}>
                    {g.count} holding{g.count === 1 ? '' : 's'}{g.count > 0 && <> · {fmt(g.present)}</>}{sipTotal > 0 && <> · SIP {fmt(sipTotal)}/mo</>}
                  </div>
                </div>
                <button style={smallBtn} onClick={() => setEditing({ id: g.id, name: g.name })}>Rename</button>
                <button style={dangerBtn}
                  onClick={() => g.count ? setDeleting(g) : run(deleteHoldingGroup(g.id), `${g.name} deleted`)}>Delete</button>
              </div>
              {expanded && (
                <div style={{ background: T.surface2, padding: '4px 16px 10px 34px' }}>
                  <div style={{ display: 'flex', gap: 10, fontSize: 11, color: T.muted, padding: '8px 0 4px' }}>
                    <span style={{ flex: 1 }}>Holding</span><span style={{ width: 110 }}>SIP ₹ / month</span><span style={{ width: 70 }}>Day</span><span style={{ width: 52 }} />
                  </div>
                  {members.length === 0 && <div style={{ fontSize: 12.5, color: T.muted, padding: '6px 0' }}>No holdings in this group yet.</div>}
                  {members.map(h => (
                    <SipRow key={`${h.id}:${h.sip_amount}:${h.sip_day}`} h={h}
                      onSave={(amt, day) => run(setHoldingSip(h.id, amt, day), amt && day ? `${h.name}: ₹${amt.toLocaleString('en-IN')} on day ${day}` : `${h.name}: SIP off`)} />
                  ))}
                  <div style={{ fontSize: 11.5, color: T.muted, paddingTop: 8 }}>
                    On the SIP day the amount is added to the holding's invested and present value. Your own edits to a value are never overwritten.
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </Card>

      {log.length > 0 && (
        <>
          <div style={{ ...label, margin: '22px 0 8px' }}>Recent SIPs applied</div>
          <Card style={{ padding: 0, overflow: 'hidden' }}>
            {log.slice(0, 12).map((r, i) => (
              <div key={r.id} style={{ display: 'flex', gap: 12, padding: '8px 16px', fontSize: 12.5, borderTop: i ? `1px solid ${T.hairline}` : undefined }}>
                <span style={{ width: 90, color: T.muted }}>{r.sip_date}</span>
                <span style={{ flex: 1, minWidth: 0 }}>{r.holding_name}</span>
                <span style={{ color: T.positive }}>+{fmt(r.amount)}</span>
              </div>
            ))}
          </Card>
        </>
      )}

      {editing && <NameDialog initial={editing === 'new' ? '' : editing.name} title={editing === 'new' ? 'Add group' : 'Rename group'} onClose={() => setEditing(null)}
        onSave={name => {
          const t = editing; setEditing(null)
          run(t === 'new' ? createHoldingGroup(name) : renameHoldingGroup(t.id, name), t === 'new' ? 'Group added' : 'Group renamed')
        }} />}
      {deleting && (
        <Modal title="Delete group?" onClose={() => setDeleting(null)}>
          <p style={{ fontSize: 13, color: T.muted, marginBottom: 16 }}>
            <b style={{ color: T.text }}>{deleting.name}</b> has {deleting.count} holding{deleting.count > 1 ? 's' : ''}. They will move to <b style={{ color: T.text }}>Others</b> so you can assign them to another group. Nothing is lost.
          </p>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button style={btn()} onClick={() => setDeleting(null)}>Cancel</button>
            <button style={{ ...btn(), background: T.danger, borderColor: T.danger, color: '#fff' }}
              onClick={() => { const d = deleting; setDeleting(null); run(deleteHoldingGroup(d.id), `${d.name} deleted – ${d.count} moved to Others`) }}>Delete and move to Others</button>
          </div>
        </Modal>
      )}
    </div>
  )
}

function NameDialog({ initial, title, onClose, onSave }: { initial: string; title: string; onClose: () => void; onSave: (name: string) => void }) {
  const [name, setName] = useState(initial)
  const ok = name.trim().length > 0
  return (
    <Modal title={title} onClose={onClose}>
      <Field name="Name">
        <input style={input} value={name} autoFocus onChange={e => setName(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && ok) onSave(name.trim()) }} />
      </Field>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <button style={btn()} onClick={onClose}>Cancel</button>
        <button style={{ ...btn(true), opacity: ok ? 1 : 0.5 }} disabled={!ok} onClick={() => onSave(name.trim())}>Save</button>
      </div>
    </Modal>
  )
}

function SipRow({ h, onSave }: { h: Holding; onSave: (amount: number, day: number) => void }) {
  const [amt, setAmt] = useState(h.sip_amount ? String(h.sip_amount) : '')
  const [day, setDay] = useState(h.sip_day ? String(h.sip_day) : '')
  const a = parseFloat(amt) || 0
  const d = Math.round(parseFloat(day) || 0)
  const dirty = a !== h.sip_amount || d !== h.sip_day
  const valid = a >= 0 && d >= 0 && d <= 31 && (a === 0 || d >= 1)
  const small = { ...input, padding: '5px 8px', fontSize: 12.5 }
  const save = () => { if (dirty && valid) onSave(a, a > 0 ? d : 0) }
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '4px 0', fontSize: 13 }}>
      <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{h.name}</span>
      <input style={{ ...small, width: 110 }} type="number" min={0} value={amt} placeholder="0" onChange={e => setAmt(e.target.value)} onKeyDown={e => e.key === 'Enter' && save()} />
      <input style={{ ...small, width: 70 }} type="number" min={1} max={31} value={day} placeholder="1-31" onChange={e => setDay(e.target.value)} onKeyDown={e => e.key === 'Enter' && save()} />
      <span style={{ width: 52 }}>
        {dirty && <button style={{ ...btn(true), padding: '4px 10px', fontSize: 12, opacity: valid ? 1 : 0.5 }} disabled={!valid} onClick={save}>Save</button>}
      </span>
    </div>
  )
}
