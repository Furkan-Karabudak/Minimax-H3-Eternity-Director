import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import cssInjectedByJsPlugin from 'vite-plugin-css-injected-by-js';
import path from 'path';

export default defineConfig({
  plugins: [
    svelte(),
    cssInjectedByJsPlugin(),
  ],
  build: {
    outDir: path.resolve(__dirname, '../../web/studio'),
    emptyOutDir: true,
    target: 'esnext',
    lib: {
      entry: path.resolve(__dirname, 'src/main.ts'),
      name: 'EternityStudio',
      fileName: () => 'eternity_studio.js',
      formats: ['es'],
    },
    rollupOptions: {
      external: [
        '/scripts/app.js',
        '../../../scripts/app.js',
      ],
      output: {
        format: 'es',
      },
    },
  },
});
