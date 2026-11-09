import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { getMe, login as apiLogin, logout as apiLogout, type Me, type ModuleId } from './api'

interface AuthState {
  me: Me | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
  can: (m: ModuleId) => boolean
}

const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(() => getMe().then(setMe).catch(() => setMe(null)), [])
  useEffect(() => { refresh().finally(() => setLoading(false)) }, [refresh])
  useEffect(() => {
    const out = () => setMe(null)
    window.addEventListener('spendlens:signed-out', out)
    return () => window.removeEventListener('spendlens:signed-out', out)
  }, [])

  const value: AuthState = {
    me, loading, refresh,
    login: async (email, password) => { setMe(await apiLogin(email, password)) },
    logout: async () => { await apiLogout().catch(() => null); setMe(null) },
    can: m => !!me?.modules.includes(m),
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth(): AuthState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth outside AuthProvider')
  return v
}
