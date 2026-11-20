import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Le proxy ne sert qu'à l'aperçu web local. L'extension utilise ses permissions Chrome.
const proxy = {
    '/__api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/__api/, ''),
    },
};

export default defineConfig({
    base: './',
    plugins: [react()],
    server: { port: 5173, strictPort: true, proxy, fs: { allow: ['..'] } },
    preview: { port: 4173, strictPort: true, proxy },
    build: {
        target: 'chrome120',
        rolldownOptions: {
            input: { app: 'index.html', lab: 'controller-lab.html', design: 'design-assets.html' },
        },
    },
    test: { environment: 'node', restoreMocks: true },
});
