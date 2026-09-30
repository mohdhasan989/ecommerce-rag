import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Trash2 } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useCart } from '../context/CartContext';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { errMsg, orderApi } from '../services/api';
import { EmptyState, ErrorState, Field, FormError, Skeleton, Spinner } from '../components/ui';
import { Quantity } from '../components/product';
import { money } from '../utils/format';

function Summary({ cart, children }) {
  return (
    <aside className="card h-fit space-y-3 p-5 lg:sticky lg:top-24">
      <h2 className="text-lg">Order summary</h2>
      <div className="flex justify-between text-sm"><span>Subtotal ({cart.item_count} items)</span><span>{money(cart.subtotal)}</span></div>
      <div className="flex justify-between text-sm"><span>Shipping</span><span className="text-emerald-600">Free</span></div>
      <div className="flex justify-between border-t border-slate-100 pt-3 text-base font-semibold text-slate-900"><span>Total</span><span>{money(cart.total)}</span></div>
      {children}
    </aside>
  );
}

export function Cart() {
  const { cart, loading, error, refresh, update, remove } = useCart();
  const toast = useToast();
  const [busyId, setBusyId] = useState(null);
  const run = async (id, fn) => { setBusyId(id); try { await fn(); } catch (e) { toast(errMsg(e), 'error'); } finally { setBusyId(null); } };

  if (loading && !cart) return <div className="container-x grid gap-6 py-10 lg:grid-cols-3"><div className="space-y-3 lg:col-span-2">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}</div><Skeleton className="h-48" /></div>;
  if (error) return <div className="container-x py-10"><ErrorState message={errMsg(error)} onRetry={refresh} /></div>;
  if (!cart || cart.items.length === 0) return <div className="container-x py-16"><EmptyState title="Your cart is empty" text="Add something you like and it will show up here."><Link to="/products" className="btn-primary">Start shopping</Link></EmptyState></div>;

  return (
    <div className="container-x py-8">
      <h1 className="text-3xl">Shopping cart</h1>
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="space-y-3 lg:col-span-2">
          <AnimatePresence initial={false}>
            {cart.items.map((it) => (
              <motion.div key={it.id} layout exit={{ opacity: 0, height: 0 }} className={`card flex gap-4 p-3 sm:p-4 ${busyId === it.id ? 'opacity-60' : ''}`}>
                <Link to={`/products/${it.product.id}`} className="h-24 w-24 shrink-0 overflow-hidden rounded-lg bg-slate-100 sm:h-28 sm:w-28"><img src={it.product.images[0]?.image_url} alt={it.product.name} className="h-full w-full object-cover" /></Link>
                <div className="flex min-w-0 flex-1 flex-col justify-between gap-2">
                  <div className="flex justify-between gap-2">
                    <div className="min-w-0"><Link to={`/products/${it.product.id}`} className="line-clamp-2 text-sm font-medium text-slate-900 sm:text-base">{it.product.name}</Link><p className="text-xs text-slate-500">{money(it.unit_price)} each</p></div>
                    <button aria-label="Remove item" className="h-fit rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600" onClick={() => run(it.id, () => remove(it.id))}><Trash2 size={16} /></button>
                  </div>
                  <div className="flex items-center justify-between">
                    <Quantity value={it.quantity} max={it.product.stock} disabled={busyId === it.id} onChange={(q) => run(it.id, () => update(it.id, q))} />
                    <span className="font-semibold text-slate-900">{money(it.line_total)}</span>
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
        <Summary cart={cart}><Link to="/checkout" className="btn-primary w-full py-3">Proceed to checkout</Link></Summary>
      </div>
    </div>
  );
}

export function Checkout() {
  const { cart, loading, refresh } = useCart();
  const { user } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({ full_name: user?.name || '', address: '', city: '', postal_code: '', phone: '' });
  const [errs, setErrs] = useState({});
  const [apiErr, setApiErr] = useState('');
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const validate = () => {
    const e = {};
    if (f.full_name.trim().length < 2) e.full_name = 'Enter your full name';
    if (f.address.trim().length < 3) e.address = 'Enter your street address';
    if (f.city.trim().length < 2) e.city = 'Enter your city';
    if (f.postal_code.trim().length < 3) e.postal_code = 'Enter a valid postal code';
    if (!/^[+\d][\d\s-]{5,18}$/.test(f.phone.trim())) e.phone = 'Enter a valid phone number';
    setErrs(e);
    return !Object.keys(e).length;
  };
  const submit = async (ev) => {
    ev.preventDefault(); setApiErr('');
    if (!validate()) return;
    setBusy(true);
    try { const o = await orderApi.create(Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v.trim()]))); await refresh(); nav(`/orders/${o.id}`, { replace: true }); }
    catch (e) { setApiErr(errMsg(e)); } finally { setBusy(false); }
  };

  if (loading && !cart) return <div className="container-x py-10"><Skeleton className="h-96" /></div>;
  if (!cart || !cart.items.length) return <div className="container-x py-16"><EmptyState title="Nothing to check out" text="Your cart is empty."><Link to="/products" className="btn-primary">Browse products</Link></EmptyState></div>;

  return (
    <div className="container-x py-8">
      <h1 className="text-3xl">Checkout</h1>
      <form onSubmit={submit} noValidate className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="card space-y-4 p-5 lg:col-span-2">
          <h2 className="text-lg">Shipping information</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field className="sm:col-span-2" label="Full name" value={f.full_name} onChange={set('full_name')} error={errs.full_name} autoComplete="name" />
            <Field className="sm:col-span-2" label="Street address" value={f.address} onChange={set('address')} error={errs.address} autoComplete="street-address" />
            <Field label="City" value={f.city} onChange={set('city')} error={errs.city} />
            <Field label="Postal code" value={f.postal_code} onChange={set('postal_code')} error={errs.postal_code} />
            <Field className="sm:col-span-2" label="Phone" type="tel" value={f.phone} onChange={set('phone')} error={errs.phone} />
          </div>
          <FormError>{apiErr}</FormError>
        </div>
        <Summary cart={cart}>
          <ul className="max-h-48 space-y-2 overflow-auto border-t border-slate-100 pt-3 text-sm">
            {cart.items.map((i) => <li key={i.id} className="flex justify-between gap-2"><span className="truncate">{i.quantity} × {i.product.name}</span><span>{money(i.line_total)}</span></li>)}
          </ul>
          <button className="btn-primary w-full py-3" disabled={busy}>{busy ? <Spinner /> : 'Place order'}</button>
        </Summary>
      </form>
    </div>
  );
}
