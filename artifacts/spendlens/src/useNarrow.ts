import { useEffect, useState } from 'react'

/** True while the window is at most `px` wide; follows resizes. */
export function useNarrow(px = 700) {
  const q = `(max-width:${px}px)`
  const [narrow, setNarrow] = useState(() => window.matchMedia(q).matches)
  useEffect(() => {
    const m = window.matchMedia(q), f = () => setNarrow(m.matches)
    m.addEventListener('change', f)
    return () => m.removeEventListener('change', f)
  }, [q])
  return narrow
}
