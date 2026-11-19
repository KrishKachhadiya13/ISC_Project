import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The browser only talks to the frontend origin; /api is forwarded to the
// backend, so no CORS setup is needed in development or in `vite preview`.
const apiProxy = {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
};

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: apiProxy },
  // `npm run preview` serves the production build with the same API proxy.
  preview: { port: 5173, strictPort: true, proxy: apiProxy },
});
