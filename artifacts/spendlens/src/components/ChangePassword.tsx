import { useState } from 'react'
import { changePassword } from '../api'
import { T } from '../theme'
import { btn, Field, input, Modal } from './ui'

/** The signed-in user changes their own password (the current one is required). A forgotten password is reset on
 *  the server's computer with `python spendlens/reset_password.py <email>`, or by an admin in Admin › Users. */
export default function ChangePassword({ onClose }: { onClose: () => void }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')
  const [err, setErr] = useState('')
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)
  const problem = next && next.length < 8 ? 'Use at least 8 characters.' : again && next !== again ? 'The new passwords differ.' : ''
  const ok = !!current && next.length >= 8 && next === again && !busy
  const save = () => {
    setBusy(true); setErr('')
    changePassword(current, next).then(() => setDone(true)).catch(e => setErr(e.message)).finally(() => setBusy(false))
  }
  return (
    <Modal title="Change password" onClose={onClose}>
      {done ? (
        <>
          <div style={{ fontSize: 13, color: T.positive, marginBottom: 12 }}>Password changed. Use it the next time you sign in.</div>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}><button style={btn(true)} onClick={onClose}>Done</button></div>
        </>
      ) : (
        <form onSubmit={e => { e.preventDefault(); if (ok) save() }}>
          <Field name="Current password"><input style={input} type="password" autoComplete="current-password" value={current} onChange={e => setCurrent(e.target.value)} autoFocus /></Field>
          <Field name="New password"><input style={input} type="password" autoComplete="new-password" value={next} onChange={e => setNext(e.target.value)} /></Field>
          <Field name="New password again"><input style={input} type="password" autoComplete="new-password" value={again} onChange={e => setAgain(e.target.value)} /></Field>
          {(err || problem) && <div style={{ color: T.negative, fontSize: 12.5, marginBottom: 8 }}>{err || problem}</div>}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" style={btn()} onClick={onClose}>Cancel</button>
            <button type="submit" style={{ ...btn(true), opacity: ok ? 1 : 0.5 }} disabled={!ok}>{busy ? 'Saving…' : 'Change password'}</button>
          </div>
        </form>
      )}
    </Modal>
  )
}
