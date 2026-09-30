import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import { useAuth } from './context/AuthContext';
import { PageSpinner } from './components/ui';
import { AdminLayout, MainLayout } from './components/layout';
import Home from './pages/Home';
import { ProductDetails, Products } from './pages/Shop';
import { Cart, Checkout } from './pages/CartCheckout';
import { Login, Profile, Register } from './pages/AuthPages';
import { OrderDetails, Orders } from './pages/OrderPages';
import { AdminCategories, AdminDashboard, AdminOrders, AdminProducts, AdminUsers, ProductForm } from './pages/admin/Admin';

function Guard({ admin }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <PageSpinner />;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  if (admin && user.role !== 'ADMIN') return <Navigate to="/" replace />;
  return <Outlet />;
}
function ScrollTop() { const { pathname } = useLocation(); useEffect(() => window.scrollTo(0, 0), [pathname]); return null; }

export default function App() {
  return (
    <>
      <ScrollTop />
      <Routes>
        <Route element={<MainLayout />}>
          <Route index element={<Home />} />
          <Route path="products" element={<Products />} />
          <Route path="products/:id" element={<ProductDetails />} />
          <Route path="login" element={<Login />} />
          <Route path="register" element={<Register />} />
          <Route element={<Guard />}>
            <Route path="cart" element={<Cart />} />
            <Route path="checkout" element={<Checkout />} />
            <Route path="profile" element={<Profile />} />
            <Route path="orders" element={<Orders />} />
            <Route path="orders/:id" element={<OrderDetails />} />
          </Route>
          <Route path="*" element={<div className="container-x py-24 text-center"><h1 className="text-3xl">Page not found</h1></div>} />
        </Route>
        <Route element={<Guard admin />}>
          <Route path="admin" element={<AdminLayout />}>
            <Route index element={<AdminDashboard />} />
            <Route path="products" element={<AdminProducts />} />
            <Route path="products/new" element={<ProductForm />} />
            <Route path="products/:id/edit" element={<ProductForm />} />
            <Route path="categories" element={<AdminCategories />} />
            <Route path="orders" element={<AdminOrders />} />
            <Route path="users" element={<AdminUsers />} />
          </Route>
        </Route>
      </Routes>
    </>
  );
}
