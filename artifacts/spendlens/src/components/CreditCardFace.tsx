import type { CSSProperties, ReactNode } from 'react'
import { cardColor } from '../cardColors'

/** Every size on the tile is a share of its width (cqw), clamped so nothing gets unreadable, so the text always fits
 *  the fixed credit-card shape whatever the column width. `cq` builds one: cq(2.9, 9, 12) is 2.9% of the width, between 9 and 12px. */
export const cq = (w: number, min: number, max: number) => `clamp(${min}px, ${w}cqw, ${max}px)`

/** A card as a flat tile in the shape of a credit card: issuer and network, golden chip with the masked number, the name,
 *  then `hero` (the headline numbers), `children` (the stats, under a hairline) and `footer`. */
export default function CreditCardFace({ color, issuer, name, last4, network, status, onClick, hero, children, footer }: {
  color: string | undefined; issuer: string; name: string; last4?: string; network?: string; status?: string; onClick?: () => void
  hero?: ReactNode; children?: ReactNode; footer?: ReactNode
}) {
  const product = name.replace(/ ···\d+$/, '')
  const closed = status === 'closed'
  const chip: CSSProperties = {
    width: '9.4cqw', height: '6.8cqw', borderRadius: '1.4cqw', flexShrink: 0, position: 'relative',
    background: 'linear-gradient(135deg, #e9d28a, #b8932f)', boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.25)',
  }
  const line = (top: string): CSSProperties => ({ position: 'absolute', left: 0, right: 0, top, height: 1, background: 'rgba(0,0,0,0.22)' })
  return (
    <div style={{ containerType: 'inline-size', minWidth: 0 }}>
      <div onClick={onClick} role={onClick ? 'button' : undefined} tabIndex={onClick ? 0 : undefined}
        onKeyDown={onClick ? e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } } : undefined}
        style={{
          width: '100%', aspectRatio: '1.586', boxSizing: 'border-box', padding: '5cqw 5.4cqw 4.4cqw', borderRadius: '4.2cqw', overflow: 'hidden',
          display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
          background: 'var(--surface)', border: '1px solid var(--border)', boxShadow: '0 1px 2px rgba(0,0,0,0.12)', color: 'var(--text)',
          cursor: onClick ? 'pointer' : 'default', filter: closed ? 'grayscale(0.9)' : 'none', opacity: closed ? 0.6 : 1,
        }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '2cqw' }}>
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: '1.8cqw', minWidth: 0, fontSize: cq(2.9, 9, 12), fontWeight: 800,
            letterSpacing: '0.08em', textTransform: 'uppercase', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            <i style={{ width: '2.4cqw', height: '2.4cqw', borderRadius: '50%', background: cardColor(color), flexShrink: 0 }} />
            {issuer || product}
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '1.6cqw', fontSize: cq(3.1, 9, 13), fontWeight: 800, fontStyle: 'italic', color: 'var(--muted)' }}>
            {closed && <span style={{ fontSize: cq(2.4, 8.5, 10.5), fontStyle: 'normal', fontWeight: 600, padding: '0.15em 0.75em', borderRadius: 999, background: 'var(--surface2)' }}>Closed</span>}
            {network}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '3cqw' }}>
          <div style={chip}><i style={line('33%')} /><i style={line('66%')} /></div>
          <div style={{ fontFamily: 'ui-monospace, Menlo, Consolas, monospace', fontSize: cq(3.9, 10, 16), letterSpacing: '0.14em', whiteSpace: 'nowrap' }}>
            •••• •••• •••• {last4 || '••••'}
          </div>
        </div>
        {issuer && <div style={{ fontSize: cq(3.3, 10, 13.5), fontWeight: 650, color: 'var(--muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginTop: '-0.6cqw' }}>{product}</div>}
        {hero}
        {(children || footer) && (
          <div>
            {children && <div style={{ borderTop: '1px solid var(--hairline)', paddingTop: '2.6cqw' }}>{children}</div>}
            {footer && <div style={{ marginTop: '1.6cqw' }}>{footer}</div>}
          </div>
        )}
      </div>
    </div>
  )
}
