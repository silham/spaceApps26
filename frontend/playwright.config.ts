import { defineConfig } from '@playwright/test'

// Visual checks against Figma frames (M2). Match viewport sizes to the supplied frames.
export default defineConfig({
  testDir: './tests',
  use: { baseURL: 'http://localhost:5173', viewport: { width: 1440, height: 900 } },
  webServer: { command: 'pnpm dev', port: 5173, reuseExistingServer: true },
})
