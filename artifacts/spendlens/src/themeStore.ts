// One place defines every theme. The neutral colours go onto <html> as CSS variables (so the whole app restyles at
// once); accent colours are read from here by theme.ts at render time, and the app remounts when the theme changes.

export type ThemeId = 'light' | 'dark' | 'midnight' | 'aurora' | 'dusk' | 'paper' | 'terminal' | 'cmf' | 'cmf-black' | 'ios' | 'ios-dark'
export type ThemePref = ThemeId | 'auto'

interface Palette {
  bg: string; surface: string; surface2: string; border: string; hairline: string; text: string; muted: string
  sideBg: string; dangerBorder: string; today: string
  bgFull?: string   // page background; a gradient for the atmospheric themes
  font?: string
  displayFont?: string   // headings and the logo
  displayWeight?: string // weight for the display face
  radius?: string        // card corner radius
  navBg?: string         // translucent top bar (with navBlur, the iOS frosted-glass look)
  navBlur?: string
}
export interface ThemeDef {
  id: ThemeId; label: string; sub: string; mode: 'light' | 'dark'
  accent: string; accent2: string; palette: Palette
}

const glow = (a: string, b: string, base: string) =>
  `radial-gradient(900px 520px at 85% -8%, ${a}, transparent 60%), radial-gradient(800px 500px at -5% 105%, ${b}, transparent 60%), ${base}`

// A fine grid of dots, the signature Nothing / CMF surface.
const dots = (dot: string, base: string) => `radial-gradient(circle, ${dot} 1px, transparent 1.5px) 0 0 / 16px 16px, ${base}`
const DOT_FONT = "Doto, 'DotGothic16', ui-monospace, Consolas, monospace"

const IOS_FONT = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', Inter, system-ui, sans-serif"

export const THEMES: ThemeDef[] = [
  { id: 'light', label: 'Light', sub: 'Clean and bright', mode: 'light', accent: '#6c63ff', accent2: '#3ecf8e',
    palette: { bg: '#f3f5fa', surface: '#ffffff', surface2: '#edf0f7', border: '#dbe0ec', hairline: 'rgba(15,23,42,0.09)', text: '#1a2033', muted: '#5d6882', sideBg: '#f0f2f8', dangerBorder: '#f3b7c0', today: '#b45309' } },
  { id: 'dark', label: 'Dark', sub: 'The classic', mode: 'dark', accent: '#6c63ff', accent2: '#3ecf8e',
    palette: { bg: '#0f1117', surface: '#181c27', surface2: '#1e2332', border: '#252b3b', hairline: 'rgba(255,255,255,0.05)', text: '#e4e8f0', muted: '#7a85a0', sideBg: '#1d2232', dangerBorder: '#5a2a32', today: '#facc15' } },
  { id: 'midnight', label: 'Midnight', sub: 'Deep navy with an electric cyan glow', mode: 'dark', accent: '#22d3ee', accent2: '#818cf8',
    palette: { bg: '#05070f', surface: '#0b1020', surface2: '#121a30', border: '#1c2745', hairline: 'rgba(120,160,255,0.08)', text: '#e6f0ff', muted: '#7f93b8', sideBg: '#0e1528', dangerBorder: '#5a2a3a', today: '#facc15',
      bgFull: glow('rgba(34,211,238,.13)', 'rgba(129,140,248,.10)', '#05070f') } },
  { id: 'aurora', label: 'Aurora', sub: 'Northern-lights green and teal', mode: 'dark', accent: '#34d399', accent2: '#a78bfa',
    palette: { bg: '#07130f', surface: '#0d1f19', surface2: '#12291f', border: '#1b3a2d', hairline: 'rgba(120,255,200,0.07)', text: '#e3f7ee', muted: '#7fa896', sideBg: '#0f241c', dangerBorder: '#5a2a32', today: '#fde047',
      bgFull: glow('rgba(52,211,153,.16)', 'rgba(167,139,250,.12)', '#07130f') } },
  { id: 'dusk', label: 'Dusk', sub: 'Plum evening with a pink-orange sunset', mode: 'dark', accent: '#f472b6', accent2: '#fb923c',
    palette: { bg: '#150d1f', surface: '#1e1330', surface2: '#281a40', border: '#3a2760', hairline: 'rgba(255,170,230,0.08)', text: '#f5e9ff', muted: '#a58bc9', sideBg: '#231638', dangerBorder: '#6a2a45', today: '#fde047',
      bgFull: glow('rgba(244,114,182,.16)', 'rgba(251,146,60,.10)', '#150d1f') } },
  { id: 'paper', label: 'Paper', sub: 'Warm cream, like a ledger book', mode: 'light', accent: '#b45309', accent2: '#4d7c0f',
    palette: { bg: '#f5efe3', surface: '#fffaf0', surface2: '#efe6d3', border: '#e0d4ba', hairline: 'rgba(90,60,20,0.12)', text: '#3b2f1e', muted: '#7d6c52', sideBg: '#f1e9d6', dangerBorder: '#e6b3a8', today: '#be123c',
      font: "Georgia, 'Times New Roman', serif" } },
  { id: 'cmf', label: 'CMF', sub: 'Nothing-style: warm grey, signal orange, dot-matrix', mode: 'light', accent: '#ff5a1f', accent2: '#2f9e6b',
    palette: { bg: '#e8e8e5', surface: '#f7f7f5', surface2: '#ecece9', border: '#d4d4cf', hairline: 'rgba(0,0,0,0.10)', text: '#141414', muted: '#6a6a66', sideBg: '#efefec', dangerBorder: '#f0b4a8', today: '#141414',
      bgFull: dots('rgba(0,0,0,.13)', '#e8e8e5'), displayFont: DOT_FONT, displayWeight: '800' } },
  { id: 'cmf-black', label: 'CMF Black', sub: 'Pure black, signal orange, dot-matrix', mode: 'dark', accent: '#ff5a1f', accent2: '#4ade80',
    palette: { bg: '#000000', surface: '#0e0e0e', surface2: '#181818', border: '#2a2a2a', hairline: 'rgba(255,255,255,0.08)', text: '#f2f2ef', muted: '#8a8a85', sideBg: '#121212', dangerBorder: '#5a2a22', today: '#ffffff',
      bgFull: dots('rgba(255,255,255,.12)', '#000000'), displayFont: DOT_FONT, displayWeight: '800' } },
  { id: 'ios', label: 'iPhone', sub: 'iOS: system blue, soft grey, frosted glass', mode: 'light', accent: '#007aff', accent2: '#34c759',
    palette: { bg: '#f2f2f7', surface: '#ffffff', surface2: '#e9e9ee', border: '#d8d8de', hairline: 'rgba(60,60,67,0.14)', text: '#000000', muted: '#76767b', sideBg: '#f7f7fa', dangerBorder: '#ffc2be', today: '#ff3b30',
      font: IOS_FONT, displayFont: IOS_FONT, radius: '16px', navBg: 'rgba(249,249,249,0.78)', navBlur: 'saturate(180%) blur(20px)' } },
  { id: 'ios-dark', label: 'iPhone Dark', sub: 'iOS dark: true black, system blue', mode: 'dark', accent: '#0a84ff', accent2: '#30d158',
    palette: { bg: '#000000', surface: '#1c1c1e', surface2: '#2c2c2e', border: '#38383a', hairline: 'rgba(84,84,88,0.45)', text: '#ffffff', muted: '#98989f', sideBg: '#161618', dangerBorder: '#5a2a2a', today: '#ff453a',
      font: IOS_FONT, displayFont: IOS_FONT, radius: '16px', navBg: 'rgba(28,28,30,0.72)', navBlur: 'saturate(180%) blur(20px)' } },
  { id: 'terminal', label: 'Terminal', sub: 'Green phosphor and monospace', mode: 'dark', accent: '#22ff66', accent2: '#00e5ff',
    palette: { bg: '#000000', surface: '#050b05', surface2: '#0a150a', border: '#133313', hairline: 'rgba(60,255,100,0.10)', text: '#b6ffb6', muted: '#5a9a5a', sideBg: '#08110a', dangerBorder: '#5a2a2a', today: '#ffe600',
      font: "'JetBrains Mono', ui-monospace, 'Cascadia Mono', Consolas, monospace" } },
]

const KEY = 'spendlens.theme'
const MODE_KEY = 'spendlens.theme.mode'   // read by the inline script in index.html, to avoid a flash before this module loads
const media = window.matchMedia('(prefers-color-scheme: dark)')
const byId = (id: string) => THEMES.find(t => t.id === id)

export function getThemePref(): ThemePref {
  try { const v = localStorage.getItem(KEY); if (v === 'auto' || byId(v ?? '')) return v as ThemePref } catch { /* private window */ }
  return 'auto'
}

export const resolveTheme = (p: ThemePref = getThemePref()): ThemeDef => byId(p === 'auto' ? (media.matches ? 'dark' : 'light') : p)!

let current = resolveTheme()
let version = 0
const listeners = new Set<() => void>()
export const currentTheme = () => current
export const themeVersion = () => version
export const subscribeTheme = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn) } }

function apply() {
  current = resolveTheme()
  const root = document.documentElement, p = current.palette
  root.dataset.theme = current.mode   // light / dark: picks the overlay + shadow variables in index.css
  const vars: Record<string, string> = {
    '--bg': p.bg, '--surface': p.surface, '--surface2': p.surface2, '--border': p.border, '--hairline': p.hairline,
    '--text': p.text, '--muted': p.muted, '--side-bg': p.sideBg, '--danger-border': p.dangerBorder, '--today': p.today,
    '--bg-full': p.bgFull ?? p.bg, '--font': p.font ?? 'Inter, system-ui, sans-serif', '--font-display': p.displayFont ?? 'inherit', '--display-weight': p.displayWeight ?? '500',
    '--radius': p.radius ?? '10px', '--nav-bg': p.navBg ?? p.surface, '--nav-blur': p.navBlur ?? 'none', '--scroll': p.border,
  }
  for (const [k, v] of Object.entries(vars)) root.style.setProperty(k, v)
  version++
  listeners.forEach(f => f())
}

export function setThemePref(p: ThemePref) {
  try { localStorage.setItem(KEY, p); localStorage.setItem(MODE_KEY, resolveTheme(p).mode) } catch { /* private window */ }
  apply()
}

/** Call once at start-up: applies the saved choice and follows the OS setting while it is "auto". */
export function initTheme() {
  apply()
  media.addEventListener('change', () => { if (getThemePref() === 'auto') apply() })
}
