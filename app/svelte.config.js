import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      pages: 'build',
      assets: 'build',
      fallback: '404.html',
      precompress: false,
      strict: true
    }),
    // Project Pages live under /<repo-name>; CI sets BASE_PATH, local dev = ''.
    paths: {
      base: process.env.BASE_PATH || ''
    }
  }
};

export default config;
