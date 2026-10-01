import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Set VITE_HMR_HOST only when opening the dev server from another device
// (e.g. a phone). Leave unset to let Vite auto-detect the current host.
const hmrHost = process.env.VITE_HMR_HOST;

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    ...(hmrHost ? { hmr: { host: hmrHost, port: 5173 } } : {}),
  },
});