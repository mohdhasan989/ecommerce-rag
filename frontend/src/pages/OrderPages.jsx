import { Link, useParams } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import useFetch from '../hooks/useFetch';
import { orderApi } from '../services/api';
import { EmptyState, ErrorState, Skeleton, StatusBadge } from '../components/ui';
import { dateStr, money } from '../utils/format';

export function Orders() {
  const { data, loading, error, reload } = useFetch(() => orderApi.list());
  return (
    <div className="container-x py-8">
      <h1 className="text-3xl">My orders</h1>
      <div className="mt-6">
        {loading ? <div className="space-y-3">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-20" />)}</div> : error ? <ErrorState message={error} onRetry={reload} /> : data.length === 0 ? (
          <EmptyState title="No orders yet" text="When you place an order it will appear here."><Link to="/products" className="btn-primary">Start shopping</Link></EmptyState>
        ) : (
          <div className="space-y-3">
            {data.map((o) => (
              <div key={o.id} className="card flex flex-wrap items-center justify-between gap-3 p-4">
                <div><p className="font-semibold text-slate-900">Order #{o.id}</p><p className="text-sm text-slate-500">{dateStr(o.created_at)} · {o.items.length} item{o.items.length !== 1 && 's'}</p></div>
                <StatusBadge status={o.status} />
                <p className="font-semibold text-slate-900">{money(o.total_amount)}</p>
                <Link to={`/orders/${o.id}`} className="btn-outline py-2">View order</Link>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function OrderDetails() {
  const { id } = useParams();
  const { data: o, loading, error, reload } = useFetch(() => orderApi.get(id), [id]);
  if (loading) return <div className="container-x space-y-4 py-10"><Skeleton className="h-10 w-64" /><Skeleton className="h-64" /></div>;
  if (error) return <div className="container-x py-10"><ErrorState message={error} onRetry={reload} /></div>;
  const a = o.shipping_address;
  return (
    <div className="container-x py-8">
      <Link to="/orders" className="mb-4 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900"><ChevronLeft size={16} />All orders</Link>
      <div className="flex flex-wrap items-center gap-3"><h1 className="text-3xl">Order #{o.id}</h1><StatusBadge status={o.status} /></div>
      <p className="mt-1 text-sm text-slate-500">Placed on {dateStr(o.created_at)}</p>
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="card divide-y divide-slate-100 lg:col-span-2">
          {o.items.map((i) => (
            <div key={i.id} className="flex gap-4 p-4">
              <div className="h-16 w-16 shrink-0 overflow-hidden rounded-lg bg-slate-100">{i.image_url && <img src={i.image_url} alt="" className="h-full w-full object-cover" />}</div>
              <div className="min-w-0 flex-1"><Link to={`/products/${i.product_id}`} className="line-clamp-1 font-medium text-slate-900">{i.product_name}</Link><p className="text-sm text-slate-500">{i.quantity} × {money(i.price)}</p></div>
              <p className="font-semibold text-slate-900">{money(i.subtotal)}</p>
            </div>
          ))}
          <div className="flex justify-between p-4 font-semibold text-slate-900"><span>Total</span><span>{money(o.total_amount)}</span></div>
        </div>
        <div className="card h-fit p-5"><h2 className="mb-2 text-lg">Shipping information</h2>
          <p className="text-sm leading-relaxed text-slate-600">{a.full_name}<br />{a.address}<br />{a.city} {a.postal_code}<br />{a.phone}</p></div>
      </div>
    </div>
  );
}
