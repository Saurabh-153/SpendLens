import { Fragment, useCallback, useEffect, useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import {
  compareDatabases, getDbHistory, getDbOverview, switchDatabase,
  type Abnormality, type DbCard, type DbHistory, type DbKind, type DbOverview, type DbTableRow, type SyncRun,
} from '../../api'
import { T } from '../../theme'
import { AdminHeader, btn, Card, label, Modal } from '../ui'

const NAME: Record<DbKind, string> = { postgresql: 'PostgreSQL', sqlite: 'SQLite' }
const TRIGGER: Record<string, string> = {
  save: 'After a save', periodic: 'Every 15 min', startup: 'Server start', shutdown: 'Server stop',
  switch: 'Switch', recovery: 'Reconnected', manual: 'By hand',
}
const LEVEL: Record<Abnormality['level'], { colour: string; icon: string; word: string }> = {
  critical: { colour: T.negative, icon: '✕', word: 'Problem' },
  warning: { colour: T.warn, icon: '!', word: 'Check' },
  info: { colour: T.muted, icon: 'i', word: 'Note' },
}
const n = (v: number | null | undefined) => (v == null ? '–' : v.toLocaleString('en-IN'))
const dir = (d: string) => d.replace('postgresql', 'PostgreSQL').replace('sqlite', 'SQLite').replace('→', ' → ')

function ago(iso: string | null | undefined): string {
  if (!iso) return 'never'
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return when(iso)
}
const when = (iso: string) => new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
const size = (b: number | null | undefined) => (b == null ? '–' : b >= 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.round(b / 1024)} KB`)
const changeText = (r: Pick<SyncRun, 'rows_added' | 'rows_changed' | 'rows_removed' | 'tables_changed'>) => {
  if (r.tables_changed == null) return 'first copy: the starting point'
  const parts = [r.rows_added ? `${n(r.rows_added)} added` : '', r.rows_changed ? `${n(r.rows_changed)} changed` : '',
    r.rows_removed ? `${n(r.rows_removed)} removed` : ''].filter(Boolean)
  return parts.length ? `${parts.join(', ')} in ${r.tables_changed} table${r.tables_changed === 1 ? '' : 's'}` : 'no changes'
}

const pill = (colour: string): CSSProperties => ({
  display: 'inline-flex', alignItems: 'center', gap: 6, fontWeight: 600, fontSize: 12.5, padding: '3px 10px', borderRadius: 999,
  color: colour, background: `${colour}1f`,
})
const th: CSSProperties = { ...label, textAlign: 'left', padding: '6px 10px', whiteSpace: 'nowrap' }
const td: CSSProperties = { padding: '7px 10px', borderTop: `1px solid ${T.hairline}`, whiteSpace: 'nowrap', fontSize: 13 }
const num: CSSProperties = { ...td, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }

function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <Card style={{ padding: '14px 16px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
        <div style={{ fontWeight: 700, fontSize: 15, flex: 1 }}>{title}</div>
        {aside}
      </div>
      {children}
    </Card>
  )
}

/** Settings › Database: which database is main, how well the copy keeps up, everything synced, and the switch. */
export default function Database() {
  const [ov, setOv] = useState<DbOverview | null>(null)
  const [hist, setHist] = useState<DbHistory | null>(null)
  const [msg, setMsg] = useState<{ text: string; error?: boolean } | null>(null)
  const [confirm, setConfirm] = useState<DbKind | null>(null)
  const [busy, setBusy] = useState<'switch' | 'compare' | null>(null)
  const [filter, setFilter] = useState<'all' | 'changed' | 'differs'>('all')

  const load = useCallback(() => Promise.all([getDbOverview(), getDbHistory(14)])
    .then(([o, h]) => { setOv(o); setHist(h) })
    .catch(e => setMsg({ text: (e as Error).message, error: true })), [])
  useEffect(() => {
    load()
    const id = setInterval(load, 15000)
    return () => clearInterval(id)
  }, [load])

  const doSwitch = async (to: DbKind) => {
    setConfirm(null); setBusy('switch'); setMsg(null)
    try {
      await switchDatabase(to)
      setMsg({ text: `${NAME[to]} is now the main database. Everything was copied and checked first.` })
    } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
    finally { setBusy(null); load() }
  }
  const doCompare = async () => {
    setBusy('compare'); setMsg(null)
    try {
      const r = await compareDatabases()
      setMsg(r.ok ? { text: `All ${r.tables.length} tables match, row by row.` }
        : { text: `${r.differs} table${r.differs === 1 ? '' : 's'} differ${r.differs === 1 ? 's' : ''}${r.pending ? ` (${r.pending} save${r.pending === 1 ? '' : 's'} were still waiting to sync, so some difference is expected)` : ''}.`, error: !r.pending })
    } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
    finally { setBusy(null); load() }
  }

  if (!ov) return <div style={{ color: msg?.error ? T.negative : T.muted, fontSize: 13 }}>{msg?.text ?? 'Loading…'}</div>

  if (!ov.can_switch || !ov.kpis) {
    return (
      <div>
        <AdminHeader title="Database" hint="Where your data lives." />
        <Card style={{ padding: '16px 18px' }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>Running on SQLite only</div>
          <div style={{ fontSize: 13, color: T.muted, lineHeight: 1.6 }}>
            PostgreSQL isn't set up. Add <code>DATABASE_URL</code> to <code>.env.local</code> in the project folder and restart
            the server to use it as the main database, with SQLite kept as a checked copy.
          </div>
        </Card>
      </div>
    )
  }

  const k = ov.kpis
  const other: DbKind = ov.primary === 'postgresql' ? 'sqlite' : 'postgresql'
  const fallback = ov.mode === 'read-only-fallback'
  const worst = ov.abnormalities[0]?.level
  const status = fallback ? { colour: T.negative, text: '✕ Read-only: main database down' }
    : worst === 'critical' ? { colour: T.negative, text: '✕ Out of sync' }
      : k.pending ? { colour: T.warn, text: `● ${k.pending} save${k.pending === 1 ? '' : 's'} syncing` }
        : worst === 'warning' ? { colour: T.warn, text: '! Needs a look' }
          : { colour: T.positive, text: '✓ In sync' }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <AdminHeader title="Database"
        hint="One database takes your saves; the other is kept as a checked copy of it. Every copy and switch is recorded here for 90 days."
        action={<div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button style={{ ...btn(), opacity: busy ? 0.6 : 1 }} disabled={!!busy || fallback} onClick={doCompare}
            title="Check every table in both databases, row by row">{busy === 'compare' ? 'Comparing…' : 'Compare now'}</button>
          <button style={{ ...btn(true), opacity: busy || ov.switching ? 0.6 : 1 }} disabled={!!busy || ov.switching}
            onClick={() => setConfirm(other)}>{busy === 'switch' || ov.switching ? 'Switching…' : `Make ${NAME[other]} the main database`}</button>
        </div>} />

      {msg && <div role="status" style={{ fontSize: 13, color: msg.error ? T.negative : T.positive }}>{msg.text}</div>}

      <Card style={{ padding: '11px 16px', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', fontSize: 13.5 }}>
        <span style={pill(status.colour)}>{status.text}</span>
        <span><b>{NAME[ov.primary]}</b> <span style={{ color: T.muted }}>→</span> <b>{NAME[other]}</b></span>
        <span style={{ color: T.muted }}>· last verified copy {ago(ov.copy?.updated_at)}{ov.last_compare && <> · last compared {ago(ov.last_compare.at)} ({ov.last_compare.ok ? 'all matched' : `${ov.last_compare.differs} differed`})</>}</span>
      </Card>

      {ov.abnormalities.length > 0 && (
        <Card style={{ padding: '6px 16px' }}>
          {ov.abnormalities.map((a, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, padding: '9px 0', borderTop: i ? `1px solid ${T.hairline}` : undefined, alignItems: 'flex-start' }}>
              <span aria-hidden="true" style={{ width: 20, height: 20, borderRadius: '50%', flexShrink: 0, display: 'grid', placeItems: 'center', fontSize: 11, fontWeight: 700, color: '#fff', background: LEVEL[a.level].colour }}>{LEVEL[a.level].icon}</span>
              <div style={{ fontSize: 13, lineHeight: 1.5 }}>
                <b>{LEVEL[a.level].word}: {a.title}.</b> <span style={{ color: T.muted }}>{a.detail}</span>
              </div>
            </div>
          ))}
        </Card>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
        <Kpi title="Last sync" value={k.last_sync ? ago(k.last_sync.at) : 'never'}
          sub={k.last_sync ? <>{k.last_sync.ok ? <>took <b>{((k.last_sync.duration_ms ?? 0) / 1000).toFixed(1)} s</b></> : <b style={{ color: T.negative }}>failed</b>} · {TRIGGER[k.last_sync.trigger] ?? k.last_sync.trigger}</> : 'No copy recorded yet'} />
        <Kpi title="Data in sync" value={n(k.in_sync.rows)}
          sub={<>rows · <b style={{ color: k.in_sync.matching === k.in_sync.tables ? undefined : T.negative }}>{k.in_sync.matching} / {k.in_sync.tables}</b> tables match</>} />
        <Kpi title="Synced today" value={n(k.today.rows_changed)}
          sub={<>rows changed in <b>{k.today.tables_changed}</b> table{k.today.tables_changed === 1 ? '' : 's'} · <b>{k.today.syncs}</b> syncs</>} />
        <Kpi title="Sync health" value={k.health_7d.rate == null ? '–' : `${Math.floor(k.health_7d.rate * 1000) / 10}%`}
          sub={<>of <b>{n(k.health_7d.syncs)}</b> syncs in 7 days · <b style={{ color: k.health_7d.failed ? T.negative : undefined }}>{k.health_7d.failed}</b> failed</>} />
        <Kpi title="Waiting to sync" value={n(k.pending)} sub={k.pending ? 'saves not copied yet; the copy follows within ~10 s' : 'every save has been copied'} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto minmax(0,1fr)', gap: 12, alignItems: 'stretch' }}>
        <DbBox db={ov.main} fallback={fallback} />
        <div aria-hidden="true" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: T.muted, fontSize: 11.5, textAlign: 'center', gap: 4 }}>
          <svg width="56" height="20" viewBox="0 0 56 20"><path d="M2 10h46" stroke="currentColor" strokeWidth="2" fill="none" /><path d="M42 4l8 6-8 6" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
          copy after saves<br />and every 15 min
        </div>
        {ov.copy && <DbBox db={ov.copy} />}
      </div>

      {hist && <Section title="Rows synced per day" aside={<span style={{ fontSize: 12, color: T.muted }}>last 14 days · hover a day</span>}><DayChart days={hist.days} /></Section>}

      <Section title="Table by table" aside={
        <div role="group" aria-label="Show" style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {([['all', `All ${ov.tables.length}`], ['changed', 'Changed in last sync'], ['differs', 'Differs']] as const).map(([id, text]) => (
            <button key={id} onClick={() => setFilter(id)} aria-pressed={filter === id}
              style={{ ...btn(), padding: '3px 11px', fontSize: 12, borderRadius: 999, ...(filter === id ? { background: T.text, color: T.bg, borderColor: T.text } : {}) }}>{text}</button>
          ))}
        </div>}>
        <TableList rows={ov.tables} filter={filter} main={NAME[ov.primary]} copy={NAME[other]} />
      </Section>

      {hist && (
        <Section title="Sync log" aside={<span style={{ fontSize: 12, color: T.muted }}>every copy, kept {hist.keep_days} days</span>}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead><tr><th style={th}>When</th><th style={th}>Direction</th><th style={th}>Why</th><th style={th}>Changed</th><th style={{ ...th, textAlign: 'right' }}>Took</th><th style={th}>Result</th></tr></thead>
              <tbody>
                {hist.runs.length === 0 && <tr><td style={{ ...td, color: T.muted }} colSpan={6}>No copies recorded yet.</td></tr>}
                {hist.runs.slice(0, 15).map(r => (
                  <tr key={r.id}>
                    <td style={td}>{when(r.at)}</td><td style={td}>{dir(r.direction)}</td><td style={td}>{TRIGGER[r.trigger] ?? r.trigger}</td>
                    <td style={td}>{r.ok ? changeText(r) : '–'}</td>
                    <td style={num}>{r.duration_ms != null ? `${(r.duration_ms / 1000).toFixed(1)} s` : '–'}</td>
                    <td style={{ ...td, whiteSpace: 'normal' }}>{r.ok
                      ? <span style={{ color: T.positive, fontWeight: 600 }}>✓ Verified, {r.tables_total} tables</span>
                      : <><span style={{ color: T.negative, fontWeight: 600 }}>✕ Failed</span> <span style={{ color: T.muted }}>{r.error}</span></>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {hist && hist.switches.length > 0 && (
        <Section title="Main database changes">
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead><tr><th style={th}>When</th><th style={th}>Main database</th><th style={th}>Copied first</th><th style={{ ...th, textAlign: 'right' }}>Pause</th></tr></thead>
              <tbody>
                {hist.switches.map(s => (
                  <tr key={s.id}>
                    <td style={td}>{when(s.at)}</td>
                    <td style={td}>{NAME[s.from_kind]} → <b>{NAME[s.to_kind]}</b></td>
                    <td style={{ ...td, whiteSpace: 'normal' }}>{s.ok ? (s.rows_total != null ? `${n(s.rows_total)} rows, ${s.tables_total} tables, verified` : 'used the existing copy')
                      : <span style={{ color: T.negative }}>✕ Not switched: {s.error}</span>}</td>
                    <td style={num}>{(s.pause_ms / 1000).toFixed(1)} s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      <div style={{ fontSize: 12.5, color: T.muted, lineHeight: 1.6 }}>
        Later, with logins, this page moves to Admin › System and is shown to admins only; the numbers cover the whole
        installation, with a per-user breakdown added then.
      </div>

      {confirm && (
        <Modal title={`Make ${NAME[confirm]} the main database?`} onClose={() => setConfirm(null)}>
          <ol style={{ fontSize: 13, color: T.muted, lineHeight: 1.7, paddingLeft: 18, margin: '0 0 14px' }}>
            <li>Saving pauses for a few seconds.</li>
            <li>Everything in {NAME[ov.primary]} is copied into {NAME[confirm]} and checked table by table
              {fallback && ov.primary === 'postgresql' ? <> (PostgreSQL is down, so the copy from {ago(ov.copy?.updated_at)} is used)</> : null}.</li>
            <li>{NAME[confirm]} takes your saves from then on, and {NAME[ov.primary]} is kept as the copy.</li>
          </ol>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button style={btn()} onClick={() => setConfirm(null)}>Cancel</button>
            <button style={btn(true)} onClick={() => doSwitch(confirm)}>Switch to {NAME[confirm]}</button>
          </div>
        </Modal>
      )}
    </div>
  )
}

function Kpi({ title, value, sub }: { title: string; value: string; sub: ReactNode }) {
  return (
    <Card style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
      <span style={label}>{title}</span>
      <span style={{ fontSize: 24, fontWeight: 700, lineHeight: 1.15, fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-display, inherit)' }}>{value}</span>
      <span style={{ fontSize: 12, color: T.muted, lineHeight: 1.45 }}>{sub}</span>
    </Card>
  )
}

function DbBox({ db, fallback }: { db: DbCard; fallback?: boolean }) {
  const main = db.role === 'main'
  const facts: [string, ReactNode][] = [
    ['Status', db.reachable
      ? <span style={{ color: T.positive, fontWeight: 600 }}>● Reachable{db.latency_ms != null ? <span style={{ color: T.muted, fontWeight: 400 }}> · answers in {db.latency_ms} ms</span> : null}</span>
      : <span style={{ color: T.negative, fontWeight: 600 }}>● Can’t be reached</span>],
    [main ? 'Takes' : 'Updated', main ? (fallback ? 'nothing until it is back' : 'every save')
      : <>{ago(db.updated_at)}{db.last_error ? <span style={{ color: T.warn }}> · last try failed: {db.last_error}</span> : null}</>],
    ['Rows', db.rows != null ? `${n(db.rows)} in ${db.tables} tables` : '–'],
    ['Size', size(db.size_bytes)],
    ...(main ? [['Last save', db.last_save_at ? ago(db.last_save_at) : 'none since the server started'] as [string, ReactNode]] : []),
    ['Where', <code style={{ fontSize: 12 }}>{db.where ?? '–'}</code>],
  ]
  return (
    <Card style={{ padding: '13px 15px', borderColor: main ? T.accent : undefined }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontWeight: 700, fontSize: 15, flex: 1 }}>{db.name}</span>
        <span style={{ ...label, letterSpacing: 0.4, padding: '2px 9px', borderRadius: 999, color: main ? '#fff' : T.muted, background: main ? T.accent : T.surface2 }}>{main ? 'Main' : 'Copy'}</span>
      </div>
      <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '3px 14px', fontSize: 12.5, margin: 0 }}>
        {facts.map(([k, v]) => <Fragment key={k}><dt style={{ color: T.muted }}>{k}</dt><dd style={{ margin: 0, minWidth: 0, overflowWrap: 'anywhere' }}>{v}</dd></Fragment>)}
      </dl>
    </Card>
  )
}

function DayChart({ days }: { days: DbHistory['days'] }) {
  const [hover, setHover] = useState<number | null>(null)
  const W = 1000, H = 200, PL = 44, PR = 8, PT = 16, PB = 26
  const top = Math.max(10, ...days.map(d => d.rows_changed))
  const step = Math.pow(10, Math.floor(Math.log10(top)))
  const max = Math.ceil(top / step) * step
  const ticks = [0, max / 2, max]
  const plotW = W - PL - PR, plotH = H - PT - PB, slot = plotW / days.length, bw = Math.min(34, slot - 10)
  const label = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
  const h = hover != null ? days[hover] : null
  return (
    <div style={{ position: 'relative' }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', display: 'block', overflow: 'visible' }} role="img"
        aria-label={`Rows synced per day over the last ${days.length} days; ${days.reduce((s, d) => s + d.failed, 0)} failed syncs`}>
        {ticks.map(v => {
          const y = PT + plotH - (v / max) * plotH
          return <g key={v}><line x1={PL} x2={W - PR} y1={y} y2={y} stroke="var(--hairline)" />
            <text x={PL - 8} y={y + 4} textAnchor="end" fontSize="11" fill="var(--muted)">{v >= 1000 ? `${v / 1000}k` : v}</text></g>
        })}
        {days.map((d, i) => {
          const bh = (d.rows_changed / max) * plotH, x = PL + i * slot + (slot - bw) / 2, y = PT + plotH - bh
          const r = Math.min(4, bh / 2)
          return (
            <g key={d.date}>
              {bh > 0 && <path d={`M${x},${PT + plotH}V${y + r}Q${x},${y} ${x + r},${y}H${x + bw - r}Q${x + bw},${y} ${x + bw},${y + r}V${PT + plotH}Z`}
                fill={T.accent} opacity={hover == null || hover === i ? 1 : 0.55} />}
              {d.failed > 0 && <g><circle cx={x + bw / 2} cy={y - 11} r={7} fill={T.negative} stroke="var(--surface)" strokeWidth="2" />
                <text x={x + bw / 2} y={y - 7.5} textAnchor="middle" fontSize="10" fontWeight="700" fill="#fff">!</text></g>}
              <text x={x + bw / 2} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--muted)">{i === days.length - 1 ? 'Today' : new Date(`${d.date}T00:00:00`).getDate()}</text>
              <rect x={PL + i * slot} y={PT} width={slot} height={plotH} fill="transparent" tabIndex={0}
                aria-label={`${label(d.date)}: ${d.rows_changed} rows changed, ${d.syncs} syncs, ${d.failed} failed`}
                onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(i)} onBlur={() => setHover(null)} />
            </g>
          )
        })}
      </svg>
      {h && hover != null && (
        <div style={{ position: 'absolute', pointerEvents: 'none', left: `${((PL + hover * slot + slot / 2) / W) * 100}%`, top: 0, transform: 'translate(-50%, -100%)',
          background: T.text, color: T.bg, fontSize: 12, borderRadius: 8, padding: '6px 9px', whiteSpace: 'nowrap', lineHeight: 1.45 }}>
          <b>{label(h.date)}</b><br />{n(h.rows_changed)} rows changed · {h.syncs} syncs{h.failed ? <><br />{h.failed} failed</> : null}
        </div>
      )}
      {days.every(d => d.syncs === 0) && <div style={{ fontSize: 12.5, color: T.muted, marginTop: 6 }}>No copies recorded in the last 14 days yet.</div>}
    </div>
  )
}

function TableList({ rows, filter, main, copy }: { rows: DbTableRow[]; filter: 'all' | 'changed' | 'differs'; main: string; copy: string }) {
  const shown = useMemo(() => rows.filter(r => filter === 'all'
    || (filter === 'changed' && r.last_change.some(Boolean))
    || (filter === 'differs' && (r.main_rows !== r.copy_rows || r.compared_match === false))), [rows, filter])
  const areas = [...new Set(shown.map(r => r.area))]
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <thead><tr><th style={th}>Table</th><th style={{ ...th, textAlign: 'right' }}>{main}</th><th style={{ ...th, textAlign: 'right' }}>{copy}</th><th style={{ ...th, textAlign: 'right' }}>Last sync</th><th style={th}>Status</th></tr></thead>
        <tbody>
          {shown.length === 0 && <tr><td style={{ ...td, color: T.muted }} colSpan={5}>{filter === 'differs' ? 'Nothing differs: every table has the same rows in both databases.' : 'Nothing changed in the last sync.'}</td></tr>}
          {areas.map(a => [
            <tr key={a}><td colSpan={5} style={{ ...td, background: T.surface2, fontWeight: 600, fontSize: 12, color: T.muted }}>{a}</td></tr>,
            ...shown.filter(r => r.area === a).map(r => {
              const [added, changed, removed] = r.last_change
              const differs = r.main_rows !== r.copy_rows || r.compared_match === false
              return (
                <tr key={r.name}>
                  <td style={td}><code style={{ fontSize: 12.5 }}>{r.name}</code></td>
                  <td style={num}>{n(r.main_rows)}</td>
                  <td style={num}>{n(r.copy_rows)}</td>
                  <td style={{ ...num, fontSize: 12 }}>{added || changed || removed
                    ? <>{added ? <span style={{ color: T.positive }}>+{added} </span> : null}{changed ? <span>~{changed} </span> : null}{removed ? <span style={{ color: T.negative }}>−{removed}</span> : null}</>
                    : <span style={{ color: T.muted }}>–</span>}</td>
                  <td style={td}>{differs
                    ? <span style={{ color: T.negative, fontWeight: 600 }}>✕ Differs</span>
                    : <span style={{ color: T.positive, fontWeight: 600 }}>✓ Match{r.compared_match ? <span style={{ color: T.muted, fontWeight: 400 }}> · checked row by row</span> : null}</span>}</td>
                </tr>
              )
            }),
          ])}
        </tbody>
      </table>
    </div>
  )
}
