import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'
import { api } from '../lib/api'

interface AuthContextType {
  isAuthenticated: boolean
  loading: boolean
  login: (pin: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('talkquote_token')
    if (token) {
      setIsAuthenticated(true)
    }
    setLoading(false)
  }, [])

  const login = async (pin: string) => {
    const { token } = await api.auth.login(pin)
    localStorage.setItem('talkquote_token', token)
    setIsAuthenticated(true)
  }

  const logout = () => {
    localStorage.removeItem('talkquote_token')
    setIsAuthenticated(false)
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
