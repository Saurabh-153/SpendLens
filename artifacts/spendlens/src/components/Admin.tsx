import { useState, type ComponentType } from 'react'
import { T } from '../theme'
import { label } from './ui'
import Categories from './admin/Categories'
import Subcategories from './admin/Subcategories'
import Targets from './admin/Targets'
import HoldingGroups from './admin/HoldingGroups'
import HoldingColumns from './admin/HoldingColumns'
import PortfolioPlan from './admin/PortfolioPlan'
import Prices from './admin/Prices'
import CardsAdmin from './admin/CardsAdmin'
import Appearance from './admin/Appearance'
import Heroes from './admin/Heroes'

interface AdminTool { group: string; id: string; label: string; icon: string; component: ComponentType }

// Each section has a colour that tints its icons and active item.
const GROUP_COLOR: Record<string, string> = { Expense: '#7c74ff', Portfolio: '#3ecf8e', Cards: '#f5b942', General: '#38bdf8' }

// Add new admin tools here; the menu and deep links (?page=admin&tool=<id>) pick them up.
const ADMIN_TOOLS: AdminTool[] = [
  { group: 'Expense', id: 'categories', label: 'Categories', icon: '🗂️', component: Categories },
  { group: 'Expense', id: 'subcategories', label: 'Sub-categories', icon: '🔖', component: Subcategories },
  { group: 'Expense', id: 'targets', label: 'Targets & Budget', icon: '🎯', component: Targets },
  { group: 'Portfolio', id: 'holding-groups', label: 'Holding groups', icon: '🧺', component: HoldingGroups },
  { group: 'Portfolio', id: 'holding-columns', label: 'Holdings columns', icon: '🧱', component: HoldingColumns },
  { group: 'Portfolio', id: 'portfolio-plan', label: 'Goals & targets', icon: '🏁', component: PortfolioPlan },
  { group: 'Portfolio', id: 'prices', label: 'Prices', icon: '💹', component: Prices },
  { group: 'Cards', id: 'cards', label: 'Cards', icon: '💳', component: CardsAdmin },
  { group: 'General', id: 'appearance', label: 'Appearance', icon: '🎨', component: Appearance },
  { group: 'General', id: 'heroes', label: 'Heroes', icon: '🦸', component: Heroes },
]

export default function Admin() {
  const [toolId, setToolId] = useState(() => {
    const t = new URLSearchParams(location.search).get('tool')
    return ADMIN_TOOLS.some(x => x.id === t) ? t! : ADMIN_TOOLS[0].id
  })
  const tool = ADMIN_TOOLS.find(t => t.id === toolId) ?? ADMIN_TOOLS[0]
  const Tool = tool.component
  const groups = [...new Set(ADMIN_TOOLS.map(t => t.group))]

  const select = (id: string) => {
    setToolId(id)
    const url = new URL(location.href)
    url.searchParams.set('page', 'admin')
    url.searchParams.set('tool', id)
    history.replaceState(null, '', url)
  }

  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', minHeight: 'calc(100vh - 48px)' }}>
      <aside style={{ width: 210, flexShrink: 0, padding: '20px 12px', borderRight: `1px solid ${T.border}`, alignSelf: 'stretch' }}>
        {groups.map(g => (
          <div key={g} style={{ marginBottom: 18 }}>
            <div style={{ ...label, padding: '0 10px 8px', display: 'flex', alignItems: 'center', gap: 7 }}>
              <span style={{ width: 7, height: 7, borderRadius: 2, background: GROUP_COLOR[g] ?? T.accent }} />{g}
            </div>
            {ADMIN_TOOLS.filter(t => t.group === g).map(t => (
              <button key={t.id} onClick={() => select(t.id)} style={{
                display: 'flex', alignItems: 'center', gap: 10, width: '100%', textAlign: 'left', padding: '8px 10px', marginBottom: 3, borderRadius: 8,
                border: 'none', cursor: 'pointer', fontSize: 13.5, fontWeight: 500,
                background: t.id === tool.id ? `linear-gradient(90deg, ${GROUP_COLOR[g] ?? T.accent}2e, ${T.surface2})` : 'transparent',
                boxShadow: t.id === tool.id ? `inset 3px 0 0 ${GROUP_COLOR[g] ?? T.accent}` : 'none',
                color: t.id === tool.id ? T.text : T.muted,
              }}>
                <span style={{ width: 26, height: 26, borderRadius: 7, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 14,
                  background: `${GROUP_COLOR[g] ?? T.accent}22`, flexShrink: 0 }}>{t.icon}</span>
                {t.label}
              </button>
            ))}
          </div>
        ))}
      </aside>
      <main style={{ flex: 1, minWidth: 0, padding: 20, maxWidth: 1040 }}>
        <Tool />
      </main>
    </div>
  )
}
