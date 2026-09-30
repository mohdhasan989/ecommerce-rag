import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { cartApi } from '../services/api';
import { useAuth } from './AuthContext';

const Ctx = createContext(null);
export const useCart = () => useContext(Ctx);

export function CartProvider({ children }) {
  const { user } = useAuth();
  const [cart, setCart] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    if (!user) { setCart(null); return; }
    setLoading(true); setError(null);
    try { setCart(await cartApi.get()); } catch (e) { setError(e); } finally { setLoading(false); }
  }, [user]);
  useEffect(() => { refresh(); }, [refresh]);

  const wrap = (fn) => async (...a) => { const c = await fn(...a); setCart(c); return c; };
  return (
    <Ctx.Provider value={{ cart, loading, error, refresh, count: cart?.item_count || 0,
      add: wrap(cartApi.add), update: wrap(cartApi.update), remove: wrap(cartApi.remove) }}>
      {children}
    </Ctx.Provider>
  );
}
