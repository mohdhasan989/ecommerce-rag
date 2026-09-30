import axios from 'axios';

const api = axios.create({ baseURL: `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api`, timeout: 15000 });

api.interceptors.request.use((c) => {
  const t = localStorage.getItem('token');
  if (t) c.headers.Authorization = `Bearer ${t}`;
  return c;
});
api.interceptors.response.use((r) => r, (e) => {
  if (e.response?.status === 401 && localStorage.getItem('token')) {
    localStorage.removeItem('token');
    window.dispatchEvent(new Event('auth:logout'));
  }
  return Promise.reject(e);
});

export function errMsg(e) {
  const d = e?.response?.data?.error;
  if (d?.details?.length) return d.details.map((x) => x.message.replace(/^Value error, /, '')).join('. ');
  if (d?.message) return d.message;
  if (!e?.response) return 'Cannot reach the server. Please check your connection.';
  return 'Something went wrong. Please try again.';
}

const d = (p) => p.then((r) => r.data);

export const authApi = {
  login: (b) => d(api.post('/auth/login', b)),
  register: (b) => d(api.post('/auth/register', b)),
  me: () => d(api.get('/auth/me')),
  update: (b) => d(api.put('/auth/me', b)),
  changePassword: (b) => d(api.put('/auth/me/password', b)),
};
export const productApi = {
  list: (params) => d(api.get('/products', { params })),
  get: (id) => d(api.get(`/products/${id}`)),
  categories: () => d(api.get('/categories')),
};
export const cartApi = {
  get: () => d(api.get('/cart')),
  add: (product_id, quantity = 1) => d(api.post('/cart/items', { product_id, quantity })),
  update: (id, quantity) => d(api.put(`/cart/items/${id}`, { quantity })),
  remove: (id) => d(api.delete(`/cart/items/${id}`)),
};
export const orderApi = {
  list: () => d(api.get('/orders')),
  get: (id) => d(api.get(`/orders/${id}`)),
  create: (shipping) => d(api.post('/orders', { shipping })),
};
export const adminApi = {
  stats: () => d(api.get('/admin/stats')),
  products: (params) => d(api.get('/admin/products', { params })),
  product: (id) => d(api.get(`/admin/products/${id}`)),
  createProduct: (b) => d(api.post('/admin/products', b)),
  updateProduct: (id, b) => d(api.put(`/admin/products/${id}`, b)),
  deleteProduct: (id) => d(api.delete(`/admin/products/${id}`)),
  createCategory: (b) => d(api.post('/admin/categories', b)),
  updateCategory: (id, b) => d(api.put(`/admin/categories/${id}`, b)),
  deleteCategory: (id) => d(api.delete(`/admin/categories/${id}`)),
  orders: () => d(api.get('/admin/orders')),
  setOrderStatus: (id, status) => d(api.put(`/admin/orders/${id}/status`, { status })),
  users: () => d(api.get('/admin/users')),
  setUserActive: (id, is_active) => d(api.patch(`/admin/users/${id}/active`, { is_active })),
};
