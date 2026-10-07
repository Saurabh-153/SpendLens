import { useEffect, useState } from 'react'
import { getHoldingGroups } from './api'
import { paletteAt } from './cardColors'

let cache: Promise<string[]> | null = null
const load = () => (cache ??= getHoldingGroups().then(g => g.groups.map(x => x.name)).catch(() => { cache = null; return [] as string[] }))

/** A holding group's colour, by its place in the Admin list of groups, so it is the same on Holdings and Wealth.
 *  A group not in the list (or before it loads) takes the next free place. */
export function useGroupColor(extra: string[] = []) {
  const [names, setNames] = useState<string[]>([])
  useEffect(() => { load().then(setNames) }, [])
  const all = [...names, ...extra.filter(n => !names.includes(n))]
  return (group: string) => paletteAt(Math.max(all.indexOf(group), 0))
}
