import { createElement } from 'react'

/** A card's colour comes from the server (`color`): the one you chose in Admin, or else one no other card uses, kept
 *  once handed out. Colour alone cannot keep many hues apart for everyone, so wherever a card is named it also wears
 *  its initials in a chip; and every colour is different from every other card's. */
/** Colours for things that are not cards but want the same look (holding groups), by their place in a fixed list. */
export const PALETTE = ['#7c74ff', '#f5b942', '#38bdf8', '#f472b6', '#3ecf8e', '#fb7c4a', '#e2e8f0', '#a3e635', '#c084fc', '#2dd4bf', '#f87171']
export const paletteAt = (i: number) => PALETTE[((i % PALETTE.length) + PALETTE.length) % PALETTE.length]

export const cardColor = (color: string | undefined) => color || '#94a3b8'

/** Two letters that stand for a card: "ICICI Rubyx" gives IR, "Spare card 3" gives S3. */
export function initials(name: string) {
  const words = name.replace(/ ···\d+$/, '').split(/\s+/).filter(Boolean)
  const second = words.slice(1).find(w => /^\d+$/.test(w)) ?? words[1]?.[0] ?? words[0]?.[1] ?? ''
  return ((words[0]?.[0] ?? '') + second).toUpperCase()
}

/** The small coloured square that stands for a card next to its name. */
export const dotStyle = (color: string | undefined, size = 9) => ({
  display: 'inline-block', width: size, height: size, borderRadius: 3, background: cardColor(color), marginRight: 7, flexShrink: 0,
} as const)

/** A card's colour with its initials inside. */
export function CardChip({ color, name, size = 20 }: { color: string | undefined; name: string; size?: number }) {
  return createElement('span', {
    title: name,
    style: {
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: size, height: size, borderRadius: 5,
      background: cardColor(color), color: '#0b0d14', fontSize: Math.round(size * 0.46), fontWeight: 800, marginRight: 7,
      flexShrink: 0, letterSpacing: -0.3, lineHeight: 1, verticalAlign: 'middle',
    },
  }, initials(name))
}
