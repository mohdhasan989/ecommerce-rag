import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Check, ChevronLeft, ChevronRight, Search, ShoppingCart } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import useFetch from '../hooks/useFetch';
import { errMsg, productApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useCart } from '../context/CartContext';
import { useToast } from '../context/ToastContext';
import { EmptyState, ErrorState, Price, Rating, Skeleton, Spinner } from '../components/ui';
import { GridSkeleton, ProductGrid, Quantity } from '../components/product';
import { ratingOf } from '../utils/format';

export function Products() {
  const [sp, setSp] = useSearchParams();
  const q = sp.get('search') || '', cat = sp.get('category_id') || '', min = sp.get('min') || '', max = sp.get('max') || '';
  const sort = sp.get('sort') || 'newest', page = Number(sp.get('page') || 1);
  const [term, setTerm] = useState(q);
  const [lo, setLo] = useState(min), [hi, setHi] = useState(max);
  const set = (patch) => {
    const n = new URLSearchParams(sp);
    Object.entries({ page: '', ...patch }).forEach(([k, v]) => (v ? n.set(k, v) : n.delete(k)));
    setSp(n);
  };
  useEffect(() => { const t = setTimeout(() => term !== q && set({ search: term }), 400); return () => clearTimeout(t); }, [term]); // eslint-disable-line
  const cats = useFetch(() => productApi.categories());
  const { data, loading, error, reload } = useFetch(() => productApi.list({
    search: q || undefined, category_id: cat || undefined, min_price: min || undefined, max_price: max || undefined, sort, page, limit: 12 }), [q, cat, min, max, sort, page]);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.limit)) : 1;
  const clear = () => { setTerm(''); setLo(''); setHi(''); setSp({}); };

  return (
    <div className="container-x py-8">
      <h1 className="text-3xl">Products</h1>
      <div className="card mt-6 grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1.4fr_1fr]">
        <div className="relative"><Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><input className="input pl-9" placeholder="Search products or brands" value={term} onChange={(e) => setTerm(e.target.value)} /></div>
        <select className="input" value={cat} onChange={(e) => set({ category_id: e.target.value })} aria-label="Category">
          <option value="">All categories</option>{cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); set({ min: lo, max: hi }); }}>
          <input className="input" type="number" min="0" placeholder="Min $" value={lo} onChange={(e) => setLo(e.target.value)} aria-label="Min price" />
          <input className="input" type="number" min="0" placeholder="Max $" value={hi} onChange={(e) => setHi(e.target.value)} aria-label="Max price" />
          <button className="btn-outline px-3">Go</button>
        </form>
        <select className="input" value={sort} onChange={(e) => set({ sort: e.target.value })} aria-label="Sort">
          <option value="newest">Newest</option><option value="price_asc">Price: low to high</option><option value="price_desc">Price: high to low</option><option value="name">Name A–Z</option>
        </select>
      </div>
      <div className="mt-6">
        {loading ? <GridSkeleton n={8} /> : error ? <ErrorState message={error} onRetry={reload} /> : data.items.length === 0 ? (
          <EmptyState title="No products found" text="Try changing your search or filters."><button className="btn-outline" onClick={clear}>Clear filters</button></EmptyState>
        ) : (<>
          <p className="mb-4 text-sm text-slate-500">{data.total} product{data.total !== 1 && 's'}</p>
          <ProductGrid items={data.items} />
          {pages > 1 && (
            <div className="mt-8 flex items-center justify-center gap-3">
              <button className="btn-outline" disabled={page <= 1} onClick={() => set({ page: String(page - 1) })}><ChevronLeft size={16} />Prev</button>
              <span className="text-sm text-slate-600">Page {page} of {pages}</span>
              <button className="btn-outline" disabled={page >= pages} onClick={() => set({ page: String(page + 1) })}>Next<ChevronRight size={16} /></button>
            </div>
          )}
        </>)}
      </div>
    </div>
  );
}

export function ProductDetails() {
  const { id } = useParams();
  const { data: p, loading, error, reload } = useFetch(() => productApi.get(id), [id]);
  const { user } = useAuth();
  const { add } = useCart();
  const toast = useToast();
  const nav = useNavigate();
  const [qty, setQty] = useState(1);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [img, setImg] = useState(0);

  const addToCart = async () => {
    if (!user) return nav('/login', { state: { from: `/products/${id}` } });
    setBusy(true);
    try { await add(p.id, qty); setDone(true); toast('Added to cart'); setTimeout(() => setDone(false), 1600); }
    catch (e) { toast(errMsg(e), 'error'); } finally { setBusy(false); }
  };

  if (loading) return <div className="container-x grid gap-8 py-10 md:grid-cols-2"><Skeleton className="aspect-square" /><div className="space-y-4"><Skeleton className="h-4 w-24" /><Skeleton className="h-8 w-3/4" /><Skeleton className="h-6 w-32" /><Skeleton className="h-24" /><Skeleton className="h-12" /></div></div>;
  if (error) return <div className="container-x py-10"><ErrorState message={error} onRetry={reload} /></div>;
  const out = p.stock === 0;
  return (
    <div className="container-x py-8">
      <Link to="/products" className="mb-5 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900"><ChevronLeft size={16} />Back to products</Link>
      <div className="grid gap-8 md:grid-cols-2 md:gap-12">
        <div>
          <div className="card overflow-hidden"><img src={p.images[img]?.image_url} alt={p.name} className="aspect-square w-full object-cover" /></div>
          {p.images.length > 1 && <div className="mt-3 flex gap-2">{p.images.map((im, i) => <button key={im.id} onClick={() => setImg(i)} className={`h-16 w-16 overflow-hidden rounded-lg border-2 ${i === img ? 'border-brand-600' : 'border-transparent'}`}><img src={im.image_url} alt="" className="h-full w-full object-cover" /></button>)}</div>}
        </div>
        <div>
          <p className="text-sm uppercase tracking-wide text-slate-400">{p.brand} {p.category_name && `· ${p.category_name}`}</p>
          <h1 className="mt-1 text-3xl">{p.name}</h1>
          <div className="mt-3 flex items-center gap-4"><Rating value={ratingOf(p.id)} />
            <span className={`text-sm font-medium ${out ? 'text-red-600' : p.stock <= 10 ? 'text-amber-600' : 'text-emerald-600'}`}>{out ? 'Out of stock' : p.stock <= 10 ? `Only ${p.stock} left` : 'In stock'}</span></div>
          <div className="mt-4"><Price p={p} large /></div>
          <p className="mt-5 leading-relaxed text-slate-600">{p.description}</p>
          <p className="mt-2 text-xs text-slate-400">SKU: {p.sku}</p>
          <div className="mt-7 flex flex-wrap items-center gap-4">
            <Quantity value={qty} onChange={setQty} max={Math.max(p.stock, 1)} disabled={out} />
            <motion.button whileTap={{ scale: 0.97 }} className="btn-primary min-w-44 px-6 py-3" disabled={out || busy} onClick={addToCart}>
              <AnimatePresence mode="wait" initial={false}>
                <motion.span key={done ? 'd' : 'a'} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} className="inline-flex items-center gap-2">
                  {busy ? <Spinner /> : done ? <><Check size={16} />Added!</> : <><ShoppingCart size={16} />Add to cart</>}
                </motion.span>
              </AnimatePresence>
            </motion.button>
          </div>
        </div>
      </div>
    </div>
  );
}
