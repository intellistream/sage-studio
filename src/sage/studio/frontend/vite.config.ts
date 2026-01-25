import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
        },
    },
    server: {
        port: parseInt(process.env.PORT || '5173'),
        // Allow all external hosts (Cloudflare Tunnel, custom domains, etc.)
        // 'true' means allow any host - necessary for reverse proxy setups
        allowedHosts: true,
        proxy: {
            // Studio Backend API - 从环境变量或默认配置读取
            // VITE_BACKEND_PORT 默认 8080 (对应 SagePorts.STUDIO_BACKEND)
            '/api': {
                target: `http://localhost:${process.env.VITE_BACKEND_PORT || '8080'}`,
                changeOrigin: true,
                rewrite: (path) => path,
            },
        },
    },
    build: {
        outDir: 'dist',
        sourcemap: true,
    },
    // Preview server config (for production mode: vite preview)
    preview: {
        port: parseInt(process.env.PORT || '5173'),
        // Allow all external hosts (Cloudflare Tunnel, custom domains, etc.)
        allowedHosts: true,
        proxy: {
            // Studio Backend API - 从环境变量或默认配置读取
            '/api': {
                target: `http://localhost:${process.env.VITE_BACKEND_PORT || '8080'}`,
                changeOrigin: true,
                rewrite: (path) => path,
            },
        },
    },
    test: {
        globals: true,
        environment: 'jsdom',
        setupFiles: './src/test/setup.ts',
    },
})
