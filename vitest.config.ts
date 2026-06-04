import { defineConfig } from 'vitest/config'

// Vitest config is kept separate from vite.config.ts. Tests cover pure
// functions only (no React rendering), so no jsdom environment is needed.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/__tests__/**/*.test.ts'],
  },
})
