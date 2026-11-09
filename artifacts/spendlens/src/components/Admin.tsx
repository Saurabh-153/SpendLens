import { useState, type ComponentType } from 'react'
import { T } from '../theme'
import { useAuth } from '../auth'
import type { ModuleId } from '../api'
import { label } from './ui'
import Categories from './admin/Categories'
import Subcategories from './admin/Subcategories'
import Targets from './admin/Targets'
import Reminders from './admin/Reminders'
import HoldingGroups from './admin/HoldingGroups'
import HoldingColumns from './admin/HoldingColumns'
import PortfolioPlan from './admin/PortfolioPlan'
import Prices from './admin/Prices'
import CardsAdmin from './admin/CardsAdmin'
import Appearance from './admin/Appearance'
import Database from './admin/Database'
import Heroes from './admin/Heroes'
import Users from './admin/Users'
import AccessRequests from './admin/AccessRequests'

interface AdminTool { group: string; id: string; label: string; icon: string; component: ComponentType; hidden?: boolean; module?: ModuleId; adminOnly?: boolean }
// `module`: shown only to people who have that module. `adminOnly`: shown only to admins.

// Each section has a colour that tints its icons and active item.
const GROUP_COLOR: Record<string, string> = { Expense: '#7c74ff', Portfolio: '#3ecf8e', Cards: '#f5b942', General: '#38bdf8' }

// Add new admin tools here; the menu and deep links (?page=admin&tool=<id>) pick them up.
const ADMIN_TOOLS: AdminTool[] = [
  { group: 'Expense', id: 'categories', label: 'Categories & Sub-categories', icon: '🗂️', component: Categories, module: 'expense' },
  { group: 'Expense', id: 'subcategories', label: 'Review entries', icon: '🔖', component: Subcategories, module: 'expense', hidden: true },   // not in the menu; opened by the Expense page's "need a sub-category" button
  { group: 'Expense', id: 'targets', label: 'Targets & Budget', icon: '🎯', component: Targets, module: 'expense' },
  { group: 'Expense', id: 'reminders', label: 'Reminders', icon: '🔔', component: Reminders, module: 'expense' },
  { group: 'Portfolio', id: 'holding-groups', label: 'Holding groups', icon: '🧺', component: HoldingGroups, module: 'holdings' },
  { group: 'Portfolio', id: 'holding-columns', label: 'Holdings columns', icon: '🧱', component: HoldingColumns, module: 'holdings' },
  { group: 'Portfolio', id: 'portfolio-plan', label: 'Goals & targets', icon: '🏁', component: PortfolioPlan, module: 'holdings' },
  { group: 'Portfolio', id: 'prices', label: 'Prices', icon: '💹', component: Prices, module: 'holdings' },
  { group: 'Cards', id: 'cards', label: 'Cards', icon: '💳', component: CardsAdmin, module: 'cards' },
  { group: 'General', id: 'appearance', label: 'Appearance', icon: '🎨', component: Appearance },
  { group: 'General', id: 'database', label: 'Database', icon: '🗄️', component: Database, adminOnly: true },
  { group: 'General', id: 'heroes', label: 'Heroes', icon: '🦸', component: Heroes },
  { group: 'General', id: 'users', label: 'Users & modules', icon: '👥', component: Users, adminOnly: true },
  { group: 'General', id: 'access-requests', label: 'Access requests', icon: '📨', component: AccessRequests, adminOnly: true },
]

export default function Admin() {
  const { me, can } = useAuth()
  const isAdmin = me?.role === 'admin'
  const tools = ADMIN_TOOLS.filter(t => (!t.adminOnly || isAdmin) && (!t.module || can(t.module)))   // a tool only appears for someone who may use it
  const MENU_TOOLS = tools.filter(t => !t.hidden)
  const [toolId, setToolId] = useState(() => {
    const t = new URLSearchParams(location.search).get('tool')
    return tools.some(x => x.id === t) ? t! : tools[0].id
  })
  const tool = tools.find(t => t.id === toolId) ?? tools[0]
  const Tool = tool.component
  const groups = [...new Set(MENU_TOOLS.map(t => t.group))]

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
            {MENU_TOOLS.filter(t => t.group === g).map(t => (
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
                {t.id === 'access-requests' && !!me?.pending_requests && (
                  <span style={{ marginLeft: 'auto', minWidth: 18, height: 18, padding: '0 5px', borderRadius: 9, background: T.warn, color: '#000', fontSize: 11, fontWeight: 700, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>{me.pending_requests}</span>
                )}
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
