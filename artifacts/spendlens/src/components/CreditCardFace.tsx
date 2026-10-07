import { cardColor } from '../cardColors'

/** A card drawn like the real thing, follows the theme: the card's own colour shows as a glow and an accent edge.
 *  Children (the stats) sit inside the card, below the number. */
export default function CreditCardFace({ color, issuer, name, last4, network, status, onClick, hero, children }: {
  color: string | undefined; issuer: string; name: string; last4?: string; network?: string; status?: string; onClick?: () => void
  hero?: React.ReactNode; children?: React.ReactNode
}) {
  const base = cardColor(color)
  const product = name.replace(/ ···\d+$/, '')
  const closed = status === 'closed'
  return (
    <div onClick={onClick} role={onClick ? 'button' : undefined} style={{
      position: 'relative', aspectRatio: '1.586', width: '100%', borderRadius: 16, padding: '12px 18px', boxSizing: 'border-box', minHeight: 'min-content', // grows rather than clipping the stats
      color: 'var(--text)', cursor: onClick ? 'pointer' : 'default', overflow: 'hidden', display: 'flex', flexDirection: 'column', gap: 4,
      background: `radial-gradient(circle at 100% 0%, ${base}33 0%, transparent 55%), linear-gradient(145deg, var(--surface2) 0%, var(--surface) 100%)`,
      border: '1px solid var(--border)', borderTop: `3px solid ${base}`,
      boxShadow: '0 4px 14px rgba(0,0,0,0.16)',
      filter: closed ? 'grayscale(0.9)' : 'none', opacity: closed ? 0.6 : 1,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: 0.8, textTransform: 'uppercase', color: 'var(--text)' }}>{issuer || product}</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {closed && <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: 1, border: '1px solid currentColor', borderRadius: 4, padding: '1px 5px' }}>CLOSED</span>}
          {network && <span style={{ fontSize: 13, fontWeight: 800, fontStyle: 'italic', letterSpacing: 0.4 }}>{network}</span>}
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ width: 32, height: 23, borderRadius: 5, flexShrink: 0, background: 'linear-gradient(135deg, #e9d28a, #b8932f)', boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.25)' }} />
        <div style={{ fontFamily: 'ui-monospace, Menlo, Consolas, monospace', fontSize: 15, letterSpacing: 2, whiteSpace: 'nowrap' }}>
          •••• •••• •••• {last4 || '••••'}
        </div>
      </div>
      {issuer && <div style={{ fontSize: 11.5, fontWeight: 600, opacity: 0.85, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{product}</div>}
      {hero && <div style={{ flex: 1, display: 'flex', alignItems: 'center' }}>{hero}</div>}
      {children && <div style={{ borderTop: '1px solid var(--hairline)', paddingTop: 6, marginTop: hero ? 0 : 'auto' }}>{children}</div>}
    </div>
  )
}
