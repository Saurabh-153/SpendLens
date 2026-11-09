import type { ExposureData } from '../api'
import { colorOf } from '../exposure'
import { T } from '../theme'

const H = 210, BW = 46, X1 = 30, X2 = 150, PAD = 3

/** Today's split and the target split as two stacked columns, joined slice to slice, so a slice that should grow fans
 *  out and one that should shrink narrows. Without targets only today's column is drawn. */
export default function TodayVsTarget({ rows, active, onPick }: {
  rows: ExposureData['exposures']; active: string | null; onPick: (n: string | null) => void
}) {
  const parts = rows.filter(r => r.present > 0 || (r.target ?? 0) > 0)
  const hasTargets = parts.some(r => r.target != null)
  const tSum = parts.reduce((s, r) => s + (r.target ?? 0), 0) || 100
  let ya = 0, yb = 0
  const W = hasTargets ? X2 + BW + 30 : X1 + BW + 30
  return (
    <svg width={W} height={H + 26} viewBox={`0 0 ${W} ${H + 26}`} role="img" style={{ display: 'block', flexShrink: 0 }}
      aria-label={`Today ${parts.map(r => `${r.name} ${Math.round(r.pct)}%`).join(', ')}${hasTargets ? `; target ${parts.map(r => `${r.name} ${r.target ?? 0}%`).join(', ')}` : ''}`}>
      {parts.map(r => {
        const ha = (r.pct / 100) * H, hb = ((r.target ?? 0) / tSum) * H
        const a = ya, b = yb
        ya += ha; yb += hb
        const fade = active != null && active !== r.name ? 0.25 : 1
        const c = colorOf(r.name)
        return (
          <g key={r.name} opacity={fade} style={{ transition: 'opacity .15s', cursor: 'default' }} onMouseEnter={() => onPick(r.name)} onMouseLeave={() => onPick(null)}>
            {hasTargets && (
              <path d={`M${X1 + BW},${a + PAD / 2}L${X2},${b + PAD / 2}L${X2},${b + hb - PAD / 2}L${X1 + BW},${a + ha - PAD / 2}Z`} fill={c} opacity={0.16} />
            )}
            {ha > PAD && <rect x={X1} y={a + PAD / 2} width={BW} height={ha - PAD} rx={5} fill={c}><title>{`${r.name} today ${r.pct.toFixed(1)}%`}</title></rect>}
            {ha > 18 && <text x={X1 + BW / 2} y={a + ha / 2 + 4} textAnchor="middle" fontSize="11.5" fontWeight="650" fill="#fff">{Math.round(r.pct)}%</text>}
            {hasTargets && hb > PAD && (
              <rect x={X2} y={b + PAD / 2} width={BW} height={hb - PAD} rx={5} fill={c} fillOpacity={0.45} stroke={c} strokeDasharray="4 3">
                <title>{`${r.name} target ${r.target ?? 0}%`}</title>
              </rect>
            )}
            {hasTargets && hb > 18 && <text x={X2 + BW / 2} y={b + hb / 2 + 4} textAnchor="middle" fontSize="11.5" fontWeight="650" fill={T.text}>{r.target}%</text>}
          </g>
        )
      })}
      <text x={X1 + BW / 2} y={H + 20} textAnchor="middle" fontSize="12" fill={T.muted}>Today</text>
      {hasTargets && <text x={X2 + BW / 2} y={H + 20} textAnchor="middle" fontSize="12" fill={T.muted}>Target</text>}
    </svg>
  )
}
