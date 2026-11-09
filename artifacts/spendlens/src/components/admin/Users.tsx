import { useCallback, useEffect, useState } from 'react'
import { createAdminUser, getAdminUsers, setUserModules, updateAdminUser, type AdminUser, type ModuleId, type ModuleInfo } from '../../api'
import { useAuth } from '../../auth'
import { T } from '../../theme'
import { Switch } from '../reminderUi'
import { AdminHeader, btn, Card, dangerBtn, Field, input, Modal, smallBtn } from '../ui'

type Msg = { text: string; error?: boolean } | null

// One-click bundles for the common plans; they only fill in the switches.
const PRESETS: { label: string; modules: ModuleId[] }[] = [
  { label: 'Expense', modules: ['expense'] },
  { label: 'Expense + Holdings', modules: ['expense', 'holdings'] },
  { label: 'Expense + Ledger + Holdings', modules: ['expense', 'ledger', 'holdings'] },
  { label: 'Everything', modules: ['expense', 'holdings', 'ledger', 'cards'] },
]

function NewUser({ modules, onClose, onDone }: { modules: ModuleInfo[]; onClose: () => void; onDone: () => void }) {
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<'user' | 'admin'>('user')
  const [picked, setPicked] = useState<ModuleId[]>(['expense'])
  const [error, setError] = useState('')
  const toggle = (m: ModuleId, on: boolean) => setPicked(p => (on ? [...p, m] : p.filter(x => x !== m)))

  const save = async () => {
    try { await createAdminUser({ email, name, password, role, modules: picked }); onDone(); onClose() } catch (e) { setError((e as Error).message) }
  }
  return (
    <Modal title="Add user" onClose={onClose}>
      <Field name="Email"><input style={input} type="email" value={email} onChange={e => setEmail(e.target.value)} autoFocus /></Field>
      <Field name="Name"><input style={input} value={name} onChange={e => setName(e.target.value)} /></Field>
      <Field name="Temporary password (min 8)"><input style={input} type="text" value={password} onChange={e => setPassword(e.target.value)} autoComplete="off" /></Field>
      <Field name="Role">
        <select style={input} value={role} onChange={e => setRole(e.target.value as 'user' | 'admin')}>
          <option value="user">User (modules below)</option>
          <option value="admin">Admin (everything, plus this page)</option>
        </select>
      </Field>
      {role === 'user' && (
        <Field name="Modules">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
            {PRESETS.map(p => <button key={p.label} type="button" style={smallBtn} onClick={() => setPicked(p.modules)}>{p.label}</button>)}
          </div>
          {modules.map(m => (
            <div key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '4px 0' }}>
              <Switch checked={picked.includes(m.id)} onChange={v => toggle(m.id, v)} label={m.label} />
              <span style={{ fontSize: 13 }}>{m.label}</span>
            </div>
          ))}
        </Field>
      )}
      {error && <p style={{ color: T.danger, fontSize: 12.5, marginBottom: 10 }}>{error}</p>}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <button style={btn()} onClick={onClose}>Cancel</button>
        <button style={btn(true)} onClick={save} disabled={!email || password.length < 8}>Create</button>
      </div>
    </Modal>
  )
}

function ResetPassword({ user, onClose, onDone }: { user: AdminUser; onClose: () => void; onDone: () => void }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const save = async () => {
    try { await updateAdminUser(user.id, { password }); onDone(); onClose() } catch (e) { setError((e as Error).message) }
  }
  return (
    <Modal title={`New password for ${user.email}`} onClose={onClose}>
      <p style={{ color: T.muted, fontSize: 12.5, marginBottom: 12 }}>They are signed out everywhere and must use this password next time.</p>
      <Field name="New password (min 8)"><input style={input} type="text" value={password} onChange={e => setPassword(e.target.value)} autoComplete="off" autoFocus /></Field>
      {error && <p style={{ color: T.danger, fontSize: 12.5, marginBottom: 10 }}>{error}</p>}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <button style={btn()} onClick={onClose}>Cancel</button>
        <button style={btn(true)} onClick={save} disabled={password.length < 8}>Set password</button>
      </div>
    </Modal>
  )
}

export default function Users() {
  const { me } = useAuth()
  const [modules, setModules] = useState<ModuleInfo[]>([])
  const [users, setUsers] = useState<AdminUser[]>([])
  const [adding, setAdding] = useState(false)
  const [resetting, setResetting] = useState<AdminUser | null>(null)
  const [msg, setMsg] = useState<Msg>(null)

  const load = useCallback(() => getAdminUsers().then(r => { setModules(r.modules); setUsers(r.users) }).catch(e => setMsg({ text: e.message, error: true })), [])
  useEffect(() => { load() }, [load])

  const run = async (p: Promise<unknown>, ok?: string) => {
    try { await p; setMsg(ok ? { text: ok } : null); await load() } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
  }
  const toggle = (u: AdminUser, m: ModuleId, on: boolean) =>
    run(setUserModules(u.id, on ? [...u.modules, m] : u.modules.filter(x => x !== m)))

  return (
    <div>
      <AdminHeader title="Users & modules" hint="Choose which modules each person can use. Turning one off only locks it - their data is kept. A user can ask for a locked module; those requests are under Access requests."
        action={<button style={btn(true)} onClick={() => setAdding(true)}>+ Add user</button>} />
      {msg && <p style={{ color: msg.error ? T.danger : T.positive, fontSize: 12.5, marginBottom: 10 }}>{msg.text}</p>}
      <Card style={{ padding: 0, overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: 'left', color: T.muted, fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.6 }}>
              <th style={{ padding: '12px 14px' }}>User</th>
              {modules.map(m => <th key={m.id} style={{ padding: '12px 8px', textAlign: 'center' }}>{m.label}</th>)}
              <th style={{ padding: '12px 14px' }} />
            </tr>
          </thead>
          <tbody>
            {users.map(u => {
              const admin = u.role === 'admin'
              return (
                <tr key={u.id} style={{ borderTop: `1px solid ${T.hairline}`, opacity: u.is_active ? 1 : 0.5 }}>
                  <td style={{ padding: '10px 14px' }}>
                    <div style={{ fontWeight: 600 }}>{u.name || u.email}{admin && <span style={{ marginLeft: 8, fontSize: 10.5, color: T.accent }}>ADMIN</span>}{!u.is_active && <span style={{ marginLeft: 8, fontSize: 10.5, color: T.danger }}>INACTIVE</span>}</div>
                    {u.name && <div style={{ color: T.muted, fontSize: 12 }}>{u.email}</div>}
                    {!!u.pending?.length && <div style={{ color: T.warn, fontSize: 11.5 }}>Asked for: {u.pending.join(', ')}</div>}
                  </td>
                  {modules.map(m => (
                    <td key={m.id} style={{ padding: '10px 8px', textAlign: 'center' }}>
                      {admin ? <span style={{ color: T.muted }} title="Admins have every module">✓</span>
                        : <Switch checked={u.modules.includes(m.id)} onChange={v => toggle(u, m.id, v)} label={`${m.label} for ${u.email}`} />}
                    </td>
                  ))}
                  <td style={{ padding: '10px 14px', whiteSpace: 'nowrap', textAlign: 'right' }}>
                    {!admin && (
                      <select aria-label={`Plan for ${u.email}`} value="" style={{ ...smallBtn, marginRight: 6 }}
                        onChange={e => { const p = PRESETS.find(x => x.label === e.target.value); if (p) run(setUserModules(u.id, p.modules)) }}>
                        <option value="">Apply plan…</option>
                        {PRESETS.map(p => <option key={p.label} value={p.label}>{p.label}</option>)}
                      </select>
                    )}
                    <button style={{ ...smallBtn, marginRight: 6 }} onClick={() => setResetting(u)}>Reset password</button>
                    {u.id !== me?.id && (u.is_active
                      ? <button style={dangerBtn} onClick={() => run(updateAdminUser(u.id, { is_active: false }), `${u.email} deactivated`)}>Deactivate</button>
                      : <button style={smallBtn} onClick={() => run(updateAdminUser(u.id, { is_active: true }), `${u.email} reactivated`)}>Reactivate</button>)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </Card>
      {adding && <NewUser modules={modules} onClose={() => setAdding(false)} onDone={load} />}
      {resetting && <ResetPassword user={resetting} onClose={() => setResetting(null)} onDone={() => { setMsg({ text: 'Password changed' }); load() }} />}
    </div>
  )
}
