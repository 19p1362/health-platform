import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3001,
    proxy: {
      '/api': 'http://localhost:8080',
      '/fhir': 'http://localhost:8080',
      '/docs': 'http://localhost:8080',
      '/redoc': 'http://localhost:8080',
      '/openapi.json': 'http://localhost:8080',
      '/health': 'http://localhost:8080',
    },
  },
  build: {
    outDir: 'build',
    sourcemap: false,
  },
});
