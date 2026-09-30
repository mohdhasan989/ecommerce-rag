const fmt = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
export const money = (n) => fmt.format(Number(n || 0));
export const dateStr = (s) => new Date(s.endsWith('Z') ? s : s + 'Z').toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
// The schema has no rating column; a stable placeholder keeps the UI complete until one is added.
export const ratingOf = (id) => Math.round((4 + ((id * 7) % 10) / 10) * 10) / 10;
export const isEmail = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
