import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { LayoutDashboard, LogOut, Menu, Package, ShoppingBag, ShoppingCart, Store, Tags, User, Users, X } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useCart } from '../context/CartContext';

const linkCls = ({ isActive }) => `text-sm font-medium transition-colors ${isActive ? 'text-brand-600' : 'text-slate-600 hover:text-slate-900'}`;

function Navbar() {
  const { user, logout } = useAuth();
  const { count } = useCart();
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  const nav = useNavigate();
  useEffect(() => setOpen(false), [pathname]);
  const out = () => { logout(); nav('/'); };

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="container-x flex h-16 items-center justify-between">
        <Link to="/" className="flex items-center gap-2 text-lg font-bold text-slate-900"><ShoppingBag className="text-brand-600" size={22} />Shoply</Link>
        <nav className="hidden items-center gap-8 md:flex">
          <NavLink to="/" end className={linkCls}>Home</NavLink>
          <NavLink to="/products" className={linkCls}>Products</NavLink>
          {user?.role === 'ADMIN' && <NavLink to="/admin" className={linkCls}>Admin</NavLink>}
        </nav>
        <div className="flex items-center gap-2">
          <Link to="/cart" aria-label="Cart" className="relative rounded-lg p-2 text-slate-600 hover:bg-slate-100">
            <ShoppingCart size={20} />
            {count > 0 && <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand-600 px-1 text-[10px] font-semibold text-white">{count}</span>}
          </Link>
          <div className="hidden items-center gap-2 md:flex">
            {user ? (
              <div className="group relative">
                <button className="btn-outline py-2"><User size={16} />{user.name.split(' ')[0]}</button>
                <div className="invisible absolute right-0 top-full w-44 pt-2 opacity-0 transition group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100">
                  <div className="card overflow-hidden py-1 text-sm shadow-lift">
                    <Link className="block px-4 py-2 hover:bg-slate-50" to="/profile">Profile</Link>
                    <Link className="block px-4 py-2 hover:bg-slate-50" to="/orders">My orders</Link>
                    <button className="block w-full px-4 py-2 text-left text-red-600 hover:bg-slate-50" onClick={out}>Log out</button>
                  </div>
                </div>
              </div>
            ) : (<><Link to="/login" className="btn-outline py-2">Log in</Link><Link to="/register" className="btn-primary py-2">Sign up</Link></>)}
          </div>
          <button className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 md:hidden" aria-label="Menu" onClick={() => setOpen(!open)}>{open ? <X size={22} /> : <Menu size={22} />}</button>
        </div>
      </div>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden border-t border-slate-100 bg-white md:hidden">
            <div className="container-x flex flex-col gap-1 py-3 text-sm">
              {[['/', 'Home'], ['/products', 'Products'], ...(user ? [['/profile', 'Profile'], ['/orders', 'My orders']] : [['/login', 'Log in'], ['/register', 'Sign up']]), ...(user?.role === 'ADMIN' ? [['/admin', 'Admin dashboard']] : [])].map(([to, l]) => (
                <Link key={to} to={to} className="rounded-lg px-3 py-2.5 font-medium hover:bg-slate-50">{l}</Link>
              ))}
              {user && <button onClick={out} className="rounded-lg px-3 py-2.5 text-left font-medium text-red-600 hover:bg-slate-50">Log out</button>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}

function Footer() {
  return (
    <footer className="mt-20 border-t border-slate-200 bg-white">
      <div className="container-x grid gap-8 py-12 sm:grid-cols-2 lg:grid-cols-4">
        <div><div className="flex items-center gap-2 font-bold text-slate-900"><ShoppingBag className="text-brand-600" size={20} />Shoply</div>
          <p className="mt-3 text-sm text-slate-500">Quality products, fair prices and fast delivery.</p></div>
        <div><h4 className="mb-3 text-sm font-semibold text-slate-900">Shop</h4><ul className="space-y-2 text-sm text-slate-500"><li><Link to="/products">All products</Link></li><li><Link to="/cart">Cart</Link></li><li><Link to="/orders">Orders</Link></li></ul></div>
        <div><h4 className="mb-3 text-sm font-semibold text-slate-900">Account</h4><ul className="space-y-2 text-sm text-slate-500"><li><Link to="/login">Log in</Link></li><li><Link to="/register">Register</Link></li><li><Link to="/profile">Profile</Link></li></ul></div>
        <div><h4 className="mb-3 text-sm font-semibold text-slate-900">Support</h4><p className="text-sm text-slate-500">support@shoply.example<br />Mon–Sat, 9am–6pm</p></div>
      </div>
      <div className="border-t border-slate-100 py-4 text-center text-xs text-slate-400">© {new Date().getFullYear()} Shoply. All rights reserved.</div>
    </footer>
  );
}

export function MainLayout() {
  const { pathname } = useLocation();
  return (
    <div className="flex min-h-screen flex-col">
      <Navbar />
      <motion.main key={pathname} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25 }} className="flex-1"><Outlet /></motion.main>
      <Footer />
    </div>
  );
}

const ADMIN_LINKS = [['/admin', 'Dashboard', LayoutDashboard, true], ['/admin/products', 'Products', Package], ['/admin/categories', 'Categories', Tags], ['/admin/orders', 'Orders', ShoppingBag], ['/admin/users', 'Users', Users]];

export function AdminLayout() {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  const { user, logout } = useAuth();
  const nav = useNavigate();
  useEffect(() => setOpen(false), [pathname]);
  return (
    <div className="min-h-screen bg-slate-50">
      {open && <div className="fixed inset-0 z-30 bg-slate-900/40 lg:hidden" onClick={() => setOpen(false)} />}
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-slate-200 bg-white transition-transform duration-300 lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex h-16 items-center gap-2 border-b border-slate-100 px-5 font-bold text-slate-900"><ShoppingBag className="text-brand-600" size={20} />Shoply Admin</div>
        <nav className="flex-1 space-y-1 p-3">
          {ADMIN_LINKS.map(([to, label, Icon, end]) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${isActive ? 'bg-brand-50 text-brand-700' : 'text-slate-600 hover:bg-slate-50'}`}><Icon size={18} />{label}</NavLink>
          ))}
        </nav>
        <div className="space-y-1 border-t border-slate-100 p-3">
          <Link to="/" className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50"><Store size={18} />View store</Link>
          <button onClick={() => { logout(); nav('/login'); }} className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-red-600 hover:bg-slate-50"><LogOut size={18} />Log out</button>
        </div>
      </aside>
      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-200 bg-white/90 px-4 backdrop-blur sm:px-6">
          <button className="rounded-lg p-2 hover:bg-slate-100 lg:hidden" aria-label="Open menu" onClick={() => setOpen(true)}><Menu size={22} /></button>
          <span className="ml-auto text-sm text-slate-500">Signed in as <b className="text-slate-800">{user?.name}</b></span>
        </header>
        <motion.main key={pathname} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-4 sm:p-6"><Outlet /></motion.main>
      </div>
    </div>
  );
}
