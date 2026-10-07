// One fixed colour per exposure, so a slice or line keeps its colour in every chart on the Asset Mix page.
export const MIX = ['Equity', 'Gold', 'Debt'] as const
export const COLORS: Record<string, string> = { Equity: '#7c74ff', Gold: '#f5b942', Debt: '#38bdf8' }
export const colorOf = (e: string) => COLORS[e] ?? '#a3e635'
