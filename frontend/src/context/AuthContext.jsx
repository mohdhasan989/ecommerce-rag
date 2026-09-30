import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { authApi } from '../services/api';

const Ctx = createContext(null);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(!!localStorage.getItem('token'));

  useEffect(() => {
    if (!localStorage.getItem('token')) return;
    authApi.me().then(setUser).catch(() => localStorage.removeItem('token')).finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    const h = () => setUser(null);
    window.addEventListener('auth:logout', h);
    return () => window.removeEventListener('auth:logout', h);
  }, []);

  const finish = (res) => { localStorage.setItem('token', res.access_token); setUser(res.user); return res.user; };
  const login = useCallback(async (email, password) => finish(await authApi.login({ email, password })), []);
  const register = useCallback(async (name, email, password) => finish(await authApi.register({ name, email, password })), []);
  const logout = useCallback(() => { localStorage.removeItem('token'); setUser(null); }, []);

  return <Ctx.Provider value={{ user, loading, login, register, logout, setUser }}>{children}</Ctx.Provider>;
}
