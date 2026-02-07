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
            // Studio Backend API - 独立后端提供完整的 SAGE 框架能力
            // 支持环境变量配置端口，避免 8080 冲突
            '/api': {
                target: `http://localhost:${process.env.VITE_BACKEND_PORT || process.env.STUDIO_BACKEND_PORT || '8080'}`,
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
            // Studio Backend API
            '/api': {
                target: `http://localhost:${process.env.VITE_BACKEND_PORT || process.env.STUDIO_BACKEND_PORT || '8080'}`,
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
