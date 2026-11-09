import { useState, type FormEvent } from 'react'
import { resetPasswordLocal } from '../api'
import { useAuth } from '../auth'
import { T } from '../theme'
import { btn, card, Field, input } from './ui'

export default function Login() {
  const { login } = useAuth()
  const [mode, setMode] = useState<'signin' | 'reset'>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [again, setAgain] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true); setError('')
    try { await login(email, password) } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }
  const reset = async (e: FormEvent) => {
    e.preventDefault()
    if (password.length < 8) return setError('Use at least 8 characters.')
    if (password !== again) return setError('The two passwords differ.')
    setBusy(true); setError('')
    try {
      await resetPasswordLocal(email, password, code)
      setMode('signin'); setAgain(''); setCode(''); setNotice('Password reset. Sign in with the new password.')
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }
  const switchTo = (m: 'signin' | 'reset') => { setMode(m); setError(''); setNotice(''); setPassword(''); setAgain(''); setCode('') }
  const link = { background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: T.accent, fontSize: 12.5 }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      {mode === 'signin' ? (
        <form onSubmit={submit} style={{ ...card, padding: 28, width: 360, maxWidth: '100%' }}>
          <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>💰 SpendLens</div>
          <p style={{ color: T.muted, fontSize: 13, marginBottom: 20 }}>Sign in to continue.</p>
          <Field name="Email"><input style={input} type="email" autoComplete="username" autoFocus value={email} onChange={e => setEmail(e.target.value)} /></Field>
          <Field name="Password"><input style={input} type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} /></Field>
          {notice && <p style={{ color: T.positive, fontSize: 12.5, marginBottom: 12 }}>{notice}</p>}
          {error && <p style={{ color: T.danger, fontSize: 12.5, marginBottom: 12 }}>{error}</p>}
          <button type="submit" disabled={busy || !email || !password} style={{ ...btn(true), width: '100%', opacity: busy || !email || !password ? 0.6 : 1 }}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
          <div style={{ marginTop: 14, textAlign: 'center' }}><button type="button" style={link} onClick={() => switchTo('reset')}>Forgot password?</button></div>
        </form>
      ) : (
        <form onSubmit={reset} style={{ ...card, padding: 28, width: 360, maxWidth: '100%' }}>
          <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>Reset password</div>
          <p style={{ color: T.muted, fontSize: 12.5, marginBottom: 20, lineHeight: 1.5 }}>
            Works only in a browser on the computer running SpendLens, with the reset code printed in the window where the
            backend is running. From anywhere else, ask an admin to reset it in Admin › Users.
          </p>
          <Field name="Email"><input style={input} type="email" autoComplete="username" autoFocus value={email} onChange={e => setEmail(e.target.value)} /></Field>
          <Field name="New password"><input style={input} type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} /></Field>
          <Field name="New password again"><input style={input} type="password" autoComplete="new-password" value={again} onChange={e => setAgain(e.target.value)} /></Field>
          <Field name="Reset code (from the backend window)"><input style={input} autoComplete="one-time-code" spellCheck={false} placeholder="ABCD-EFGH" value={code} onChange={e => setCode(e.target.value)} /></Field>
          {error && <p style={{ color: T.danger, fontSize: 12.5, marginBottom: 12 }}>{error}</p>}
          <button type="submit" disabled={busy || !email || !password || !again || !code} style={{ ...btn(true), width: '100%', opacity: busy || !email || !password || !again || !code ? 0.6 : 1 }}>
            {busy ? 'Resetting…' : 'Reset password'}
          </button>
          <div style={{ marginTop: 14, textAlign: 'center' }}><button type="button" style={link} onClick={() => switchTo('signin')}>Back to sign in</button></div>
        </form>
      )}
    </div>
  )
}
