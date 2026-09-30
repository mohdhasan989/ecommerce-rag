import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Minus, Plus } from 'lucide-react';
import { Price, Rating, Skeleton } from './ui';
import { ratingOf } from '../utils/format';

export function ProductCard({ p }) {
  const img = p.images[0]?.image_url;
  return (
    <motion.div whileHover={{ y: -4 }} transition={{ duration: 0.2 }} className="card group h-full overflow-hidden transition-shadow hover:shadow-lift">
      <Link to={`/products/${p.id}`} className="block h-full">
        <div className="relative aspect-square overflow-hidden bg-slate-100">
          {img && <img src={img} alt={p.name} loading="lazy" className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105" />}
          {p.discount_price != null && <span className="absolute left-3 top-3 rounded-full bg-rose-600 px-2 py-0.5 text-xs font-medium text-white">Sale</span>}
          {p.stock === 0 && <span className="absolute right-3 top-3 rounded-full bg-slate-900 px-2 py-0.5 text-xs font-medium text-white">Sold out</span>}
        </div>
        <div className="space-y-1 p-3 sm:p-4">
          <p className="text-xs uppercase tracking-wide text-slate-400">{p.brand}</p>
          <h3 className="line-clamp-2 text-sm font-medium sm:text-base">{p.name}</h3>
          <Rating value={ratingOf(p.id)} />
          <Price p={p} />
        </div>
      </Link>
    </motion.div>
  );
}

export const GridSkeleton = ({ n = 8 }) => (
  <div className="grid grid-cols-2 gap-3 sm:gap-5 md:grid-cols-3 xl:grid-cols-4">
    {Array.from({ length: n }).map((_, i) => (
      <div key={i} className="card overflow-hidden"><Skeleton className="aspect-square rounded-none" /><div className="space-y-2 p-4"><Skeleton className="h-3 w-1/3" /><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-1/2" /></div></div>
    ))}
  </div>
);
export const ProductGrid = ({ items }) => (
  <div className="grid grid-cols-2 gap-3 sm:gap-5 md:grid-cols-3 xl:grid-cols-4">{items.map((p) => <ProductCard key={p.id} p={p} />)}</div>
);

export function Quantity({ value, onChange, max = 99, disabled }) {
  return (
    <div className="inline-flex items-center rounded-lg border border-slate-300 bg-white">
      <button type="button" aria-label="Decrease" disabled={disabled || value <= 1} onClick={() => onChange(value - 1)} className="p-2.5 text-slate-600 hover:bg-slate-50 disabled:opacity-40"><Minus size={14} /></button>
      <span className="w-9 text-center text-sm font-medium">{value}</span>
      <button type="button" aria-label="Increase" disabled={disabled || value >= max} onClick={() => onChange(value + 1)} className="p-2.5 text-slate-600 hover:bg-slate-50 disabled:opacity-40"><Plus size={14} /></button>
    </div>
  );
}
