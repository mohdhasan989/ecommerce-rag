// Runs the frontend's real service layer against a live backend.
// Usage: npx vite-node tests/api-integration.mjs   (backend must be running, seeded)
const store = {};
globalThis.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => (store[k] = String(v)), removeItem: (k) => delete store[k] };
globalThis.window = { dispatchEvent() {}, addEventListener() {} };
globalThis.Event = class { constructor(t) { this.type = t; } };
const { authApi, productApi, cartApi, orderApi, adminApi, errMsg } = await import('../src/services/api.js');

let fail = 0;
const ok = (c, m) => { console.log(`${c ? 'PASS' : 'FAIL'}  ${m}`); if (!c) fail++; };
const t = async (m, fn) => { try { ok(await fn(), m); } catch (e) { ok(false, `${m} -> ${errMsg(e)}`); } };

// NOTE: runs against a persistent MySQL database, so counts are captured as a
// baseline and compared relatively. Re-running this file must stay green.
await t('products load from API (with images)', async () => { const r = await productApi.list({ limit: 100 }); return r.total > 0 && r.items[0].images.length > 0; });
await t('category filter + price filter + sort', async () => { const c = (await productApi.categories()).find((x) => x.name === 'Shoes'); const r = await productApi.list({ category_id: c.id, max_price: 100, sort: 'price_asc' }); return r.items.length > 0 && r.items.every((p) => (p.discount_price ?? p.price) <= 100); });
await t('product details', async () => (await productApi.get(1)).sku === 'EL-HP-001');
try { await authApi.login({ email: 'alice@demo.com', password: 'wrong-pass' }); ok(false, 'bad login rejected'); } catch (e) { ok(errMsg(e) === 'Invalid email or password', `bad login shows friendly message: "${errMsg(e)}"`); }
await t('register validation message is readable', async () => { try { await authApi.register({ name: 'X', email: 'a@b.co', password: 'short' }); } catch (e) { return errMsg(e).length > 0 && !errMsg(e).includes('Traceback'); } });
const reg = await authApi.register({ name: 'Integration Tester', email: `it${Date.now()}@shoply.dev`, password: 'Secret123!' });
ok(reg.user.role === 'USER', 'new registration is always USER');
localStorage.setItem('token', reg.access_token);
await t('cart: add -> update -> remove', async () => { let c = await cartApi.add(1, 2); const id = c.items[0].id; c = await cartApi.update(id, 3); if (c.item_count !== 3) return false; c = await cartApi.remove(id); return c.items.length === 0; });
await t('checkout creates order and empties cart', async () => { await cartApi.add(2, 1); const o = await orderApi.create({ full_name: 'Integration Tester', address: '1 Test Road', city: 'Ludhiana', postal_code: '141001', phone: '9999999999' }); return (await cartApi.get()).items.length === 0 && (await orderApi.get(o.id)).items[0].product_name === 'Smart Watch Series 5'; });
await t('profile update + password change', async () => { const u = await authApi.update({ name: 'Renamed Tester', email: reg.user.email }); await authApi.changePassword({ current_password: 'Secret123!', new_password: 'Secret456!' }); return u.name === 'Renamed Tester'; });
try { await adminApi.stats(); ok(false, 'USER blocked from admin API'); } catch (e) { ok(e.response?.status === 403, 'USER blocked from admin API (403)'); }
const adm = await authApi.login({ email: process.env.ADMIN_EMAIL, password: process.env.ADMIN_PASSWORD });
localStorage.setItem('token', adm.access_token);
ok(adm.user.role === 'ADMIN', 'admin login works');
await t('admin dashboard stats agree with product lists', async () => {
  const s = await adminApi.stats();
  const all = await adminApi.products({ limit: 100 });
  const pub = await productApi.list({ limit: 100 });
  const inactive = all.items.filter((p) => !p.is_active).length;
  return s.total_products === all.total && pub.total === all.total - inactive && s.total_users >= 3 && Array.isArray(s.recent_orders);
});
await t('admin product create/edit/deactivate', async () => { const before = (await adminApi.stats()).total_products; const p = await adminApi.createProduct({ name: 'IT Product', price: 10, stock: 3, sku: `IT-${Date.now()}`, image_urls: ['https://x/y.jpg'] }); if ((await adminApi.stats()).total_products !== before + 1) return false; await adminApi.updateProduct(p.id, { name: 'IT Product 2', price: 10, stock: 4, sku: p.sku, image_urls: [] }); await adminApi.deleteProduct(p.id); const pub = await productApi.list({ search: 'IT Product 2', limit: 10 }); return pub.total === 0; });
await t('admin orders + users lists', async () => (await adminApi.orders()).length >= 3 && (await adminApi.users()).length >= 4);
const pre = await fetch(`${process.env.VITE_API_URL}/api/products`, { method: 'OPTIONS', headers: { Origin: 'http://localhost:5173', 'Access-Control-Request-Method': 'GET' } });
ok(pre.headers.get('access-control-allow-origin') === 'http://localhost:5173', 'CORS allows the Vite dev origin');
console.log(fail ? `\n${fail} FAILED` : '\nAll integration checks passed'); process.exit(fail ? 1 : 0);
