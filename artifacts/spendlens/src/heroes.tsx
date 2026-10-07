import { useState, type ReactNode } from 'react'

// Full-body flat-illustration figures on a 160 x 200 canvas, each in a signature pose. They are stylised drawings, not
// official artwork: to use your own picture for a hero, drop a transparent PNG at public/heroes/<id>.png and rebuild.
export interface Hero { id: string; name: string; universe: 'Marvel' | 'DC'; pose: string; quips: string[]; art: ReactNode }

const SKIN = '#f1c9a5'
const round = { strokeLinecap: 'round', strokeLinejoin: 'round', fill: 'none' } as const

export const HEROES: Hero[] = [
  {
    id: 'ironman', name: 'Iron Man', universe: 'Marvel', pose: 'Repulsor blast',
    quips: ['Jarvis, log that expense.', 'I am Iron Man… and your budget is under review.', 'Genius, billionaire, playboy. You? Stay under the cap.'],
    art: (
      <>
        <path d="M56 70 L40 104 L48 124" stroke="#b91c1c" strokeWidth="15" {...round} />
        <circle cx="49" cy="127" r="8" fill="#f5b301" />
        <path d="M70 126 L64 184" stroke="#b91c1c" strokeWidth="19" {...round} /><path d="M90 126 L96 184" stroke="#b91c1c" strokeWidth="19" {...round} />
        <path d="M54 182 H76 V196 H52Z" fill="#f5b301" /><path d="M84 182 H106 L108 196 H84Z" fill="#f5b301" />
        <circle cx="66" cy="152" r="6" fill="#f5b301" /><circle cx="94" cy="152" r="6" fill="#f5b301" />
        <path d="M54 64 H106 L98 128 H62Z" fill="#b91c1c" /><path d="M66 70 H94 L90 98 H70Z" fill="#f5b301" />
        <rect x="62" y="116" width="36" height="9" fill="#f5b301" />
        <circle cx="80" cy="84" r="13" fill="#67e8f9" opacity=".45" className="hero-pulse" /><circle cx="80" cy="84" r="7.5" fill="#e0f7ff" />
        <circle cx="54" cy="68" r="11" fill="#f5b301" /><circle cx="106" cy="68" r="11" fill="#f5b301" />
        <path d="M106 68 L134 52 L148 32" stroke="#b91c1c" strokeWidth="15" {...round} />
        <path d="M152 27 L170 6 M152 27 L176 24 M152 27 L164 -2" stroke="#67e8f9" strokeWidth="3" strokeLinecap="round" className="hero-pulse" />
        <circle cx="152" cy="27" r="21" fill="#67e8f9" opacity=".5" className="hero-pulse" /><circle cx="152" cy="27" r="11" fill="#f5b301" /><circle cx="152" cy="27" r="6" fill="#e0f7ff" />
        <path d="M80 14 C95 14 101 27 100 42 C99 55 91 63 80 67 C69 63 61 55 60 42 C59 27 65 14 80 14Z" fill="#b91c1c" />
        <path d="M80 25 C91 25 95 35 94 45 C93 55 87 61 80 64 C73 61 67 55 66 45 C65 35 69 25 80 25Z" fill="#f5b301" />
        <path d="M69 41 L78 44 L78 48 L70 46Z" fill="#e0f7ff" /><path d="M91 41 L82 44 L82 48 L90 46Z" fill="#e0f7ff" />
        <path d="M75 57 H85" stroke="#b91c1c" strokeWidth="2.5" strokeLinecap="round" />
      </>
    ),
  },
  {
    id: 'hulk', name: 'Hulk', universe: 'Marvel', pose: 'Roaring flex',
    quips: ['HULK SMASH overspending!', 'Hulk no like red numbers.', 'You wouldn’t like me when I see your food bill.'],
    art: (
      <>
        <path d="M64 146 L60 184" stroke="#4caf50" strokeWidth="27" {...round} /><path d="M96 146 L100 184" stroke="#4caf50" strokeWidth="27" {...round} />
        <ellipse cx="57" cy="192" rx="17" ry="7" fill="#3d8b40" /><ellipse cx="103" cy="192" rx="17" ry="7" fill="#3d8b40" />
        <path d="M36 66 Q80 50 124 66 L112 130 H48Z" fill="#4caf50" />
        <path d="M80 72 V106 M52 92 Q66 106 80 98 Q94 106 108 92 M68 112 H92 M70 120 H90" stroke="#3d8b40" strokeWidth="3" strokeLinecap="round" fill="none" />
        <path d="M46 124 H114 L120 166 L84 158 L76 158 L40 166Z" fill="#7e22ce" />
        <path d="M42 74 L14 82 L20 42" stroke="#4caf50" strokeWidth="25" {...round} /><path d="M118 74 L146 82 L140 42" stroke="#4caf50" strokeWidth="25" {...round} />
        <circle cx="20" cy="32" r="15" fill="#4caf50" /><circle cx="140" cy="32" r="15" fill="#4caf50" />
        <path d="M14 26 H26 M134 26 H146" stroke="#3d8b40" strokeWidth="2" />
        <circle cx="80" cy="44" r="22" fill="#4caf50" />
        <path d="M57 42 C56 18 104 18 103 42 C97 31 63 31 57 42Z" fill="#161616" />
        <path d="M62 41 L78 47 M98 41 L82 47" stroke="#14351a" strokeWidth="4.5" strokeLinecap="round" />
        <circle cx="70" cy="48" r="3.4" fill="#fff" /><circle cx="90" cy="48" r="3.4" fill="#fff" /><circle cx="70.6" cy="48.4" r="1.6" fill="#111" /><circle cx="89.4" cy="48.4" r="1.6" fill="#111" />
        <path d="M66 56 Q80 74 94 56 Q80 61 66 56Z" fill="#14351a" /><path d="M70 58 H90" stroke="#fff" strokeWidth="2.6" strokeDasharray="3 2" />
      </>
    ),
  },
  {
    id: 'superman', name: 'Superman', universe: 'DC', pose: 'Hands on hips',
    quips: ['Up, up and away… from impulse buys.', 'Faster than a speeding EMI.', 'Truth, justice and a balanced budget.'],
    art: (
      <>
        <path d="M52 62 Q16 112 32 188 L80 154 L128 188 Q144 112 108 62Z" fill="#b91c1c" className="hero-cape" />
        <path d="M70 128 L66 182" stroke="#1d4ed8" strokeWidth="17" {...round} /><path d="M90 128 L94 182" stroke="#1d4ed8" strokeWidth="17" {...round} />
        <path d="M56 174 H78 V196 H54Z" fill="#c1121f" /><path d="M82 174 H104 L106 196 H82Z" fill="#c1121f" />
        <path d="M54 64 H106 L98 116 H62Z" fill="#1d4ed8" />
        <path d="M60 114 H100 L96 140 H64Z" fill="#c1121f" /><rect x="60" y="110" width="40" height="6" fill="#facc15" />
        <path d="M80 70 L97 74 L95 91 C94 99 87 103 80 106 C73 103 66 99 65 91 L63 74Z" fill="#facc15" />
        <path d="M80 75 L92 78 L90 90 C89 95 85 98 80 101 C75 98 71 95 70 90 L68 78Z" fill="#c1121f" />
        <text x="80" y="95" textAnchor="middle" fontFamily="Georgia, serif" fontWeight="900" fontSize="19" fill="#facc15">S</text>
        <path d="M54 68 L32 96 L58 112" stroke="#1d4ed8" strokeWidth="14" {...round} /><path d="M106 68 L128 96 L102 112" stroke="#1d4ed8" strokeWidth="14" {...round} />
        <circle cx="61" cy="113" r="6.5" fill={SKIN} /><circle cx="99" cy="113" r="6.5" fill={SKIN} />
        <rect x="74" y="55" width="12" height="12" fill="#e0b48f" />
        <ellipse cx="80" cy="38" rx="15" ry="19" fill={SKIN} />
        <path d="M64 34 C64 15 96 15 96 34 C92 26 80 23 72 27 C68 29 65 31 64 34Z" fill="#111" /><path d="M80 22 q7 4 3 10" stroke="#111" strokeWidth="3" fill="none" strokeLinecap="round" />
        <circle cx="74" cy="40" r="2" fill="#1f2937" /><circle cx="86" cy="40" r="2" fill="#1f2937" /><path d="M73 48 Q80 53 87 48" stroke="#a5532f" strokeWidth="2" fill="none" strokeLinecap="round" />
      </>
    ),
  },
  {
    id: 'batman', name: 'Batman', universe: 'DC', pose: 'Cape spread',
    quips: ['I’m Batman. Save first, brood later.', 'The night is dark. Your credit-card bill is darker.', 'It’s not who I am underneath, it’s what you spend that defines you.'],
    art: (
      <>
        <path d="M58 58 L4 108 L22 106 L28 150 L46 132 L58 172 L80 142 L102 172 L114 132 L132 150 L138 106 L156 108 L102 58Z" fill="#111827" className="hero-cape" />
        <path d="M70 128 L66 182" stroke="#374151" strokeWidth="17" {...round} /><path d="M90 128 L94 182" stroke="#374151" strokeWidth="17" {...round} />
        <path d="M56 176 H78 V196 H54Z" fill="#0b0f19" /><path d="M82 176 H104 L106 196 H82Z" fill="#0b0f19" />
        <path d="M54 64 H106 L98 126 H62Z" fill="#4b5563" />
        <ellipse cx="80" cy="86" rx="15" ry="9" fill="#facc15" />
        <path d="M80 81 L72 79 L67 85 L74 84 L77 90 L80 86 L83 90 L86 84 L93 85 L88 79Z" fill="#111827" />
        <rect x="60" y="116" width="40" height="8" fill="#facc15" />
        <path d="M54 68 L32 104 L36 128" stroke="#4b5563" strokeWidth="14" {...round} /><path d="M106 68 L128 104 L124 128" stroke="#4b5563" strokeWidth="14" {...round} />
        <path d="M34 112 L36 132" stroke="#0b0f19" strokeWidth="15" strokeLinecap="round" /><path d="M126 112 L124 132" stroke="#0b0f19" strokeWidth="15" strokeLinecap="round" />
        <rect x="74" y="55" width="12" height="12" fill="#0b0f19" />
        <path d="M63 28 L67 6 L76 19 L84 19 L93 6 L97 28 C99 44 92 58 80 62 C68 58 61 44 63 28Z" fill="#0b0f19" />
        <path d="M68 46 C74 43 86 43 92 46 C91 54 86 60 80 61 C74 60 69 54 68 46Z" fill={SKIN} />
        <path d="M66 36 L77 39 L77 43 L68 41Z" fill="#fff" /><path d="M94 36 L83 39 L83 43 L92 41Z" fill="#fff" /><path d="M76 54 H84" stroke="#8a5a3a" strokeWidth="1.8" strokeLinecap="round" />
      </>
    ),
  },
  {
    id: 'wonderwoman', name: 'Wonder Woman', universe: 'DC', pose: 'Bracers crossed',
    quips: ['The lasso of truth says: check your budget.', 'Fight for what you saved.', 'Stronger than any overdraft.'],
    art: (
      <>
        <path d="M58 22 C52 60 50 90 58 116 L102 116 C110 90 108 60 102 22 C96 8 64 8 58 22Z" fill="#1f2430" />
        <path d="M72 128 L68 182" stroke={SKIN} strokeWidth="15" {...round} /><path d="M88 128 L92 182" stroke={SKIN} strokeWidth="15" {...round} />
        <path d="M58 150 L80 150 L78 196 H56Z" fill="#c1121f" /><path d="M80 150 L102 150 L104 196 H82Z" fill="#c1121f" />
        <path d="M58 112 H102 L112 148 H48Z" fill="#1e40af" />
        <g fill="#fff"><circle cx="62" cy="126" r="1.7" /><circle cx="78" cy="132" r="1.7" /><circle cx="94" cy="126" r="1.7" /><circle cx="70" cy="140" r="1.7" /><circle cx="88" cy="141" r="1.7" /><circle cx="104" cy="138" r="1.7" /><circle cx="56" cy="141" r="1.7" /></g>
        <path d="M58 66 H102 L98 114 H62Z" fill="#c1121f" />
        <path d="M64 74 L80 66 L96 74 L89 83 L80 78 L71 83Z" fill="#facc15" /><rect x="62" y="108" width="36" height="6" fill="#facc15" />
        <path d="M60 72 L102 98" stroke={SKIN} strokeWidth="12" {...round} /><path d="M100 72 L58 98" stroke={SKIN} strokeWidth="12" {...round} />
        <path d="M92 91 L104 99" stroke="#cbd5e1" strokeWidth="14" strokeLinecap="round" /><path d="M68 91 L56 99" stroke="#cbd5e1" strokeWidth="14" strokeLinecap="round" />
        <rect x="74" y="54" width="12" height="12" fill="#e0b48f" />
        <ellipse cx="80" cy="38" rx="15" ry="19" fill={SKIN} />
        <path d="M65 30 Q80 18 95 30" stroke="#facc15" strokeWidth="4.5" fill="none" strokeLinecap="round" />
        <path d="M80 20 L81.5 23.6 L85.4 23.8 L82.4 26.2 L83.4 30 L80 27.8 L76.6 30 L77.6 26.2 L74.6 23.8 L78.5 23.6Z" fill="#c1121f" />
        <circle cx="74" cy="40" r="2.2" fill="#1f2430" /><circle cx="86" cy="40" r="2.2" fill="#1f2430" /><path d="M75 49 Q80 53 85 49" stroke="#c0263a" strokeWidth="3" fill="none" strokeLinecap="round" />
      </>
    ),
  },
]

/** The figure at the given height. A picture at /heroes/<id>.png (your own file) wins over the drawing. */
export function HeroArt({ hero, size = 190 }: { hero: Hero; size?: number }) {
  const [custom, setCustom] = useState(true)
  const w = Math.round(size * 0.8)
  if (custom) return <img src={`/heroes/${hero.id}.png`} alt="" width={w} height={size} onError={() => setCustom(false)} style={{ display: 'block', objectFit: 'contain', objectPosition: 'bottom' }} />
  return <svg viewBox="0 0 160 200" width={w} height={size} aria-hidden="true" style={{ display: 'block', overflow: 'visible' }}>{hero.art}</svg>
}

const KEY = 'spendlens.heroes'

/** The ids the user has switched on; every hero is on until they choose otherwise. */
export function getEnabledHeroes(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? 'null')
    if (Array.isArray(v)) return v.filter((id): id is string => HEROES.some(h => h.id === id))
  } catch { /* private window or bad JSON */ }
  return HEROES.map(h => h.id)
}

export function setEnabledHeroes(ids: string[]) {
  try { localStorage.setItem(KEY, JSON.stringify(ids)) } catch { /* private window */ }
}

/** Ask the corner widget to pop a hero up now (used by the Admin preview button). */
export const previewHero = (id: string) => window.dispatchEvent(new CustomEvent('spendlens:hero', { detail: id }))
