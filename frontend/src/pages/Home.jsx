import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, Footprints, Headphones, Shirt, ShieldCheck, Tag, Truck, Watch, RefreshCw } from 'lucide-react';
import useFetch from '../hooks/useFetch';
import { productApi } from '../services/api';
import { ErrorState, Skeleton } from '../components/ui';
import { GridSkeleton, ProductGrid } from '../components/product';

const ICONS = { Electronics: Headphones, Clothing: Shirt, Shoes: Footprints, Accessories: Watch };
const rise = { hidden: { opacity: 0, y: 24 }, show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: 'easeOut' } } };

export default function Home() {
  const cats = useFetch(() => productApi.categories());
  const feat = useFetch(() => productApi.list({ limit: 12 }));
  const featured = feat.data ? [...feat.data.items].sort((a, b) => (b.discount_price ? 1 : 0) - (a.discount_price ? 1 : 0)).slice(0, 4) : [];

  return (
    <>
      <section className="bg-gradient-to-b from-brand-50 to-slate-50">
        <div className="container-x grid items-center gap-10 py-14 md:grid-cols-2 md:py-20">
          <motion.div initial="hidden" animate="show" variants={{ show: { transition: { staggerChildren: 0.12 } } }}>
            <motion.span variants={rise} className="inline-block rounded-full bg-white px-3 py-1 text-xs font-medium text-brand-700 shadow-card">New season arrivals</motion.span>
            <motion.h1 variants={rise} className="mt-4 text-4xl leading-tight sm:text-5xl">Everything you love, <span className="text-brand-600">delivered to you.</span></motion.h1>
            <motion.p variants={rise} className="mt-4 max-w-md text-slate-600">Discover electronics, fashion, shoes and accessories from brands you trust — at prices that make sense.</motion.p>
            <motion.div variants={rise} className="mt-7 flex flex-wrap gap-3">
              <Link to="/products" className="btn-primary px-6 py-3">Shop now <ArrowRight size={16} /></Link>
              <Link to="/products?sort=price_asc" className="btn-outline px-6 py-3">Best prices</Link>
            </motion.div>
          </motion.div>
          <motion.div initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.7 }} className="overflow-hidden rounded-2xl shadow-lift">
            <img src="https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=1000&q=80" alt="Store shelves" className="aspect-[4/3] w-full object-cover" />
          </motion.div>
        </div>
      </section>

      <section className="container-x -mt-2 grid gap-4 py-8 sm:grid-cols-3">
        {[[Truck, 'Free shipping', 'On orders over $100'], [RefreshCw, 'Easy returns', '30-day return window'], [ShieldCheck, 'Secure checkout', 'Your data stays protected']].map(([I, t, s]) => (
          <div key={t} className="card flex items-center gap-4 p-4"><span className="rounded-lg bg-brand-50 p-2.5 text-brand-600"><I size={20} /></span><div><p className="text-sm font-semibold text-slate-900">{t}</p><p className="text-xs text-slate-500">{s}</p></div></div>
        ))}
      </section>

      <section className="container-x py-8">
        <h2 className="mb-5 text-2xl">Shop by category</h2>
        {cats.error ? <ErrorState message={cats.error} onRetry={cats.reload} /> : (
          <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-4">
            {cats.loading ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />) : cats.data.map((c) => {
              const Icon = ICONS[c.name] || Tag;
              return (
                <Link key={c.id} to={`/products?category_id=${c.id}`} className="card group flex flex-col items-center gap-3 p-6 text-center transition hover:-translate-y-1 hover:shadow-lift">
                  <span className="rounded-full bg-brand-50 p-3 text-brand-600 transition group-hover:bg-brand-600 group-hover:text-white"><Icon size={22} /></span>
                  <span className="text-sm font-semibold text-slate-900">{c.name}</span>
                </Link>
              );
            })}
          </div>
        )}
      </section>

      <section className="container-x py-8">
        <div className="mb-5 flex items-end justify-between"><h2 className="text-2xl">Featured products</h2><Link to="/products" className="text-sm font-medium text-brand-600 hover:underline">View all</Link></div>
        {feat.loading ? <GridSkeleton n={4} /> : feat.error ? <ErrorState message={feat.error} onRetry={feat.reload} /> : <ProductGrid items={featured} />}
      </section>

      <section className="container-x py-8">
        <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="flex flex-col items-start justify-between gap-5 rounded-2xl bg-slate-900 p-8 text-white sm:flex-row sm:items-center sm:p-12">
          <div><p className="text-sm font-medium text-brand-300">Limited time</p><h2 className="mt-1 text-2xl text-white sm:text-3xl">Save up to 30% on selected items</h2><p className="mt-2 text-slate-300">Discounted prices are already applied — no code needed.</p></div>
          <Link to="/products?sort=price_asc" className="btn bg-white px-6 py-3 text-slate-900 hover:bg-slate-100">Browse deals</Link>
        </motion.div>
      </section>
    </>
  );
}
