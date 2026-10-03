import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Package, Pencil, Plus, ScrollText, ShoppingBag, Trash2, Users } from 'lucide-react';
import useFetch from '../../hooks/useFetch';
import { adminApi, errMsg, productApi } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import { EmptyState, ErrorState, Field, FormError, Skeleton, Spinner, StatusBadge } from '../../components/ui';
import { dateStr, money } from '../../utils/format';

const Head = ({ title, children }) => <div className="mb-5 flex flex-wrap items-center justify-between gap-3"><h1 className="text-2xl">{title}</h1>{children}</div>;
const Table = ({ head, children }) => (
  <div className="card overflow-x-auto"><table className="w-full min-w-[640px] text-left text-sm">
    <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500"><tr>{head.map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr></thead>
    <tbody className="divide-y divide-slate-100 [&_td]:px-4 [&_td]:py-3">{children}</tbody></table></div>
);
const TableSkeleton = () => <div className="space-y-2">{[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-12" />)}</div>;

export function AdminDashboard() {
  const { data, loading, error, reload } = useFetch(() => adminApi.stats());
  if (loading) return <div><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-28" />)}</div><Skeleton className="mt-6 h-64" /></div>;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  const cards = [['Total products', data.total_products, Package], ['Total orders', data.total_orders, ShoppingBag], ['Total users', data.total_users, Users], ['Revenue', money(data.revenue), ShoppingBag]];
  return (
    <>
      <Head title="Dashboard" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(([l, v, I]) => <div key={l} className="card flex items-center justify-between p-5"><div><p className="text-sm text-slate-500">{l}</p><p className="mt-1 text-2xl font-semibold text-slate-900">{v}</p></div><span className="rounded-lg bg-brand-50 p-3 text-brand-600"><I size={20} /></span></div>)}
      </div>
      <h2 className="mb-3 mt-8 text-lg">Recent orders</h2>
      {data.recent_orders.length === 0 ? <EmptyState title="No orders yet" /> : (
        <Table head={['Order', 'Date', 'Customer ID', 'Amount', 'Status']}>
          {data.recent_orders.map((o) => <tr key={o.id}><td className="font-medium">#{o.id}</td><td>{dateStr(o.created_at)}</td><td>{o.user_id}</td><td>{money(o.total_amount)}</td><td><StatusBadge status={o.status} /></td></tr>)}
        </Table>
      )}
    </>
  );
}

export function AdminProducts() {
  const [search, setSearch] = useState('');
  const [q, setQ] = useState('');
  useEffect(() => { const t = setTimeout(() => setQ(search), 350); return () => clearTimeout(t); }, [search]);
  const { data, loading, error, reload } = useFetch(() => adminApi.products({ search: q || undefined, limit: 100 }), [q]);
  const toast = useToast();
  const del = async (p) => {
    if (!window.confirm(`Deactivate "${p.name}"? It will be hidden from the store.`)) return;
    try { await adminApi.deleteProduct(p.id); toast('Product deactivated'); reload(); } catch (e) { toast(errMsg(e), 'error'); }
  };
  return (
    <>
      <Head title="Products"><Link to="/admin/products/new" className="btn-primary"><Plus size={16} />Add product</Link></Head>
      <input className="input mb-4 max-w-sm" placeholder="Search products" value={search} onChange={(e) => setSearch(e.target.value)} />
      {loading ? <TableSkeleton /> : error ? <ErrorState message={error} onRetry={reload} /> : data.items.length === 0 ? <EmptyState title="No products found" /> : (
        <Table head={['Product', 'Category', 'Price', 'Stock', 'Status', '']}>
          {data.items.map((p) => (
            <tr key={p.id}>
              <td><div className="flex items-center gap-3"><img src={p.images[0]?.image_url} alt="" className="h-10 w-10 rounded-lg bg-slate-100 object-cover" /><div><p className="font-medium text-slate-900">{p.name}</p><p className="text-xs text-slate-400">{p.sku}</p></div></div></td>
              <td>{p.category_name || '—'}</td><td>{money(p.discount_price ?? p.price)}</td><td>{p.stock}</td>
              <td><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${p.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-600'}`}>{p.is_active ? 'Active' : 'Inactive'}</span></td>
              <td><div className="flex justify-end gap-1"><Link to={`/admin/products/${p.id}/edit`} aria-label="Edit" className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"><Pencil size={16} /></Link>
                <button aria-label="Deactivate" onClick={() => del(p)} className="rounded-lg p-2 text-slate-500 hover:bg-red-50 hover:text-red-600"><Trash2 size={16} /></button></div></td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}

export function ProductForm() {
  const { id } = useParams();
  const edit = !!id;
  const nav = useNavigate();
  const toast = useToast();
  const cats = useFetch(() => productApi.categories());
  const empty = { name: '', brand: '', sku: '', price: '', discount_price: '', stock: '0', category_id: '', description: '', images: '', is_active: true };
  const [f, setF] = useState(empty);
  const [loading, setLoading] = useState(edit);
  const [loadErr, setLoadErr] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!edit) return;
    adminApi.product(id).then((p) => setF({ name: p.name, brand: p.brand || '', sku: p.sku, price: String(p.price), discount_price: p.discount_price ?? '', stock: String(p.stock),
      category_id: p.category_id || '', description: p.description || '', images: p.images.map((i) => i.image_url).join('\n'), is_active: p.is_active })).catch((e) => setLoadErr(errMsg(e))).finally(() => setLoading(false));
  }, [id, edit]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value });

  const submit = async (e) => {
    e.preventDefault(); setErr('');
    const price = parseFloat(f.price), disc = f.discount_price === '' ? null : parseFloat(f.discount_price);
    if (!f.name.trim() || !f.sku.trim()) return setErr('Name and SKU are required');
    if (!(price > 0)) return setErr('Enter a valid price');
    if (disc !== null && !(disc > 0 && disc < price)) return setErr('Discount price must be greater than 0 and lower than price');
    if (!(parseInt(f.stock, 10) >= 0)) return setErr('Stock must be 0 or more');
    const body = { name: f.name.trim(), brand: f.brand.trim() || null, sku: f.sku.trim(), price, discount_price: disc, stock: parseInt(f.stock, 10),
      category_id: f.category_id ? Number(f.category_id) : null, description: f.description.trim() || null, is_active: f.is_active,
      image_urls: f.images.split('\n').map((s) => s.trim()).filter(Boolean) };
    setBusy(true);
    try { edit ? await adminApi.updateProduct(id, body) : await adminApi.createProduct(body); toast(edit ? 'Product updated' : 'Product created'); nav('/admin/products'); }
    catch (x) { setErr(errMsg(x)); } finally { setBusy(false); }
  };
  if (loading) return <Skeleton className="h-96" />;
  if (loadErr) return <ErrorState message={loadErr} />;
  return (
    <>
      <Head title={edit ? 'Edit product' : 'Add product'} />
      <form onSubmit={submit} noValidate className="card grid max-w-3xl gap-4 p-5 sm:grid-cols-2">
        <div className="sm:col-span-2"><FormError>{err}</FormError></div>
        <Field className="sm:col-span-2" label="Name" value={f.name} onChange={set('name')} />
        <Field label="Brand" value={f.brand} onChange={set('brand')} />
        <Field label="SKU" value={f.sku} onChange={set('sku')} />
        <Field label="Price" type="number" step="0.01" min="0" value={f.price} onChange={set('price')} />
        <Field label="Discount price (optional)" type="number" step="0.01" min="0" value={f.discount_price} onChange={set('discount_price')} />
        <Field label="Stock" type="number" min="0" value={f.stock} onChange={set('stock')} />
        <label className="block"><span className="mb-1 block text-sm font-medium text-slate-700">Category</span>
          <select className="input" value={f.category_id} onChange={set('category_id')}><option value="">None</option>{cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <label className="block sm:col-span-2"><span className="mb-1 block text-sm font-medium text-slate-700">Description</span><textarea rows={4} className="input" value={f.description} onChange={set('description')} /></label>
        <label className="block sm:col-span-2"><span className="mb-1 block text-sm font-medium text-slate-700">Image URLs (one per line)</span><textarea rows={3} className="input" value={f.images} onChange={set('images')} placeholder="https://..." /></label>
        <label className="flex items-center gap-2 text-sm sm:col-span-2"><input type="checkbox" checked={f.is_active} onChange={set('is_active')} />Active (visible in store)</label>
        <div className="flex gap-3 sm:col-span-2"><button className="btn-primary" disabled={busy}>{busy ? <Spinner /> : edit ? 'Save changes' : 'Create product'}</button><Link to="/admin/products" className="btn-outline">Cancel</Link></div>
      </form>
    </>
  );
}

export function AdminCategories() {
  const { data, loading, error, reload } = useFetch(() => productApi.categories());
  const toast = useToast();
  const [f, setF] = useState({ id: null, name: '', description: '' });
  const [err, setErr] = useState('');
  const save = async (e) => {
    e.preventDefault(); setErr('');
    if (!f.name.trim()) return setErr('Name is required');
    const body = { name: f.name.trim(), description: f.description.trim() || null };
    try { f.id ? await adminApi.updateCategory(f.id, body) : await adminApi.createCategory(body); toast('Category saved'); setF({ id: null, name: '', description: '' }); reload(); }
    catch (x) { setErr(errMsg(x)); }
  };
  const del = async (c) => { if (!window.confirm(`Delete "${c.name}"?`)) return; try { await adminApi.deleteCategory(c.id); toast('Category deleted'); reload(); } catch (x) { toast(errMsg(x), 'error'); } };
  return (
    <>
      <Head title="Categories" />
      <form onSubmit={save} noValidate className="card mb-5 grid max-w-3xl gap-3 p-4 sm:grid-cols-[1fr_2fr_auto]">
        <div className="sm:col-span-3"><FormError>{err}</FormError></div>
        <input className="input" placeholder="Name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <input className="input" placeholder="Description" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
        <div className="flex gap-2"><button className="btn-primary">{f.id ? 'Update' : 'Add'}</button>{f.id && <button type="button" className="btn-outline" onClick={() => setF({ id: null, name: '', description: '' })}>Cancel</button>}</div>
      </form>
      {loading ? <TableSkeleton /> : error ? <ErrorState message={error} onRetry={reload} /> : (
        <Table head={['Name', 'Description', '']}>
          {data.map((c) => <tr key={c.id}><td className="font-medium text-slate-900">{c.name}</td><td>{c.description || '—'}</td>
            <td><div className="flex justify-end gap-1"><button aria-label="Edit" className="rounded-lg p-2 hover:bg-slate-100" onClick={() => setF({ id: c.id, name: c.name, description: c.description || '' })}><Pencil size={16} /></button>
              <button aria-label="Delete" className="rounded-lg p-2 hover:bg-red-50 hover:text-red-600" onClick={() => del(c)}><Trash2 size={16} /></button></div></td></tr>)}
        </Table>
      )}
    </>
  );
}

const STATUSES = ['PENDING', 'PROCESSING', 'SHIPPED', 'DELIVERED', 'CANCELLED'];
export function AdminOrders() {
  const { data, loading, error, reload } = useFetch(() => adminApi.orders());
  const toast = useToast();
  const change = async (o, s) => { try { await adminApi.setOrderStatus(o.id, s); toast(`Order #${o.id} is now ${s}`); reload(); } catch (e) { toast(errMsg(e), 'error'); } };
  return (
    <>
      <Head title="Orders" />
      {loading ? <TableSkeleton /> : error ? <ErrorState message={error} onRetry={reload} /> : data.length === 0 ? <EmptyState title="No orders yet" /> : (
        <Table head={['Order', 'Date', 'Ship to', 'Items', 'Amount', 'Status']}>
          {data.map((o) => <tr key={o.id}><td className="font-medium">#{o.id}</td><td>{dateStr(o.created_at)}</td><td>{o.shipping_address.full_name}, {o.shipping_address.city}</td><td>{o.items.length}</td><td>{money(o.total_amount)}</td>
            <td><select className="input py-1.5" value={o.status} onChange={(e) => change(o, e.target.value)}>{STATUSES.map((s) => <option key={s}>{s}</option>)}</select></td></tr>)}
        </Table>
      )}
    </>
  );
}

export function AdminUsers() {
  const { data, loading, error, reload } = useFetch(() => adminApi.users());
  const toast = useToast();
  const toggle = async (u) => { try { await adminApi.setUserActive(u.id, !u.is_active); toast(u.is_active ? 'User deactivated' : 'User activated'); reload(); } catch (e) { toast(errMsg(e), 'error'); } };
  return (
    <>
      <Head title="Users" />
      {loading ? <TableSkeleton /> : error ? <ErrorState message={error} onRetry={reload} /> : (
        <Table head={['Name', 'Email', 'Role', 'Joined', 'Status', '']}>
          {data.map((u) => <tr key={u.id}><td className="font-medium text-slate-900">{u.name}</td><td>{u.email}</td><td>{u.role}</td><td>{dateStr(u.created_at)}</td>
            <td><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${u.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-600'}`}>{u.is_active ? 'Active' : 'Inactive'}</span></td>
            <td className="text-right">{u.role !== 'ADMIN' && <button className="btn-outline py-1.5" onClick={() => toggle(u)}>{u.is_active ? 'Deactivate' : 'Activate'}</button>}</td></tr>)}
        </Table>
      )}
    </>
  );
}

const RATING_TONE = {
  1: 'bg-red-100 text-red-800',
  2: 'bg-amber-100 text-amber-800',
  3: 'bg-emerald-100 text-emerald-800',
};

export function AdminAuditLogs() {
  const { data, loading, error, reload } = useFetch(() => adminApi.auditLogs({ limit: 100 }));
  const { data: ratings, loading: ratingsLoading, reload: reloadRatings } = useFetch(
    () => adminApi.chatFeedback({ limit: 100 }),
  );
  const refresh = () => { reload(); reloadRatings(); };

  const total = ratings?.length || 0;
  const average = total
    ? (ratings.reduce((sum, r) => sum + r.rating, 0) / total).toFixed(2)
    : null;
  const cards = [
    ['Feedback received', total, ScrollText],
    ['Average rating', average ?? '-', ScrollText],
    ['Chat conversations rated', new Set(ratings?.map((r) => r.conversation_id)).size, Users],
  ];

  return (
    <>
      <Head title="Audit Log">
        <button className="btn-outline" onClick={refresh}>Refresh</button>
      </Head>

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        {cards.map(([l, v, I]) => (
          <div key={l} className="card flex items-center justify-between p-5">
            <div>
              <p className="text-sm text-slate-500">{l}</p>
              <p className="mt-1 text-2xl font-semibold text-slate-900">{v}</p>
            </div>
            <span className="rounded-lg bg-brand-50 p-3 text-brand-600"><I size={20} /></span>
          </div>
        ))}
      </div>

      <h2 className="mb-3 text-lg">Chatbot experience feedback</h2>
      {ratingsLoading ? <TableSkeleton /> : !ratings?.length ? (
        <EmptyState title="No feedback yet" />
      ) : (
        <Table head={['Rating', 'Experience', 'Conversation', 'User', 'Received']}>
          {ratings.map((r) => (
            <tr key={r.id}>
              <td className="font-semibold text-slate-900">{r.rating}</td>
              <td><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${RATING_TONE[r.rating]}`}>{['', 'Bad', 'Neutral', 'Excellent'][r.rating]}</span></td>
              <td className="font-mono text-xs text-slate-500">{r.conversation_id}</td>
              <td>{r.user_id ? `#${r.user_id}` : 'Anonymous'}</td>
              <td>{dateStr(r.created_at)}</td>
            </tr>
          ))}
        </Table>
      )}

      <h2 className="mb-3 mt-8 text-lg">Event trail</h2>
      {loading ? <TableSkeleton /> : error ? <ErrorState message={error} onRetry={reload} /> : !data?.length ? (
        <EmptyState title="No audit events yet" />
      ) : (
        <Table head={['Event', 'Details', 'User', 'When']}>
          {data.map((e) => (
            <tr key={e.id}>
              <td><span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-700">{e.action}</span></td>
              <td className="text-slate-600">{e.details}</td>
              <td>{e.user_id ? `#${e.user_id}` : 'Anonymous'}</td>
              <td>{dateStr(e.created_at)}</td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
