import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    globals: true,
  },
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['assets/varagrill-logo.jpg'],
      devOptions: {
        enabled: false,
      },
      manifest: {
        name: 'Varagrill',
        short_name: 'Varagrill',
        description: 'Acceso rápido al sistema de restaurante Varagrill',
        theme_color: '#140606',
        background_color: '#140606',
        display: 'standalone',
        orientation: 'portrait',
        scope: '/',
        start_url: '/',
        id: '/',
        categories: ['food', 'business'],
        lang: 'es',
        dir: 'ltr',
        icons: [
          {
            src: '/assets/varagrill-logo.jpg',
            sizes: 'any',
            type: 'image/svg+xml',
            purpose: 'any maskable',
          },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,ico,png,svg,webmanifest}'],
        navigateFallback: null,
        cleanupOutdatedCaches: true,
        skipWaiting: true,
        clientsClaim: true,
        runtimeCaching: [
          {
            urlPattern: ({ request }) => request.mode === 'navigate',
            handler: 'NetworkFirst',
            options: {
              cacheName: 'navigations',
              networkTimeoutSeconds: 10,
            },
          },
        ],
      },
    }),
  ],
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
      '/admin': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8010',
        ws: true,
      },
    },
  },
});
