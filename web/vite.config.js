import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1', port: 5173, strictPort: false,
    proxy: {
      '/gateway': {
        target: process.env.REPLIC8_GATEWAY_URL || 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/gateway/, ''),
      },
    },
  },
  build: {
    target: 'es2022',
    rollupOptions: { output: { manualChunks: { 'three-scene': ['three'], 'react-vendor': ['react', 'react-dom'] } } },
  },
});
