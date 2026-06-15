import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { defineConfig, devices } from '@playwright/test'

const here = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(here, '..')

const apiPort = process.env.NOVEL_WEB_PORT ?? '18765'
const webPort = process.env.PLAYWRIGHT_WEB_PORT ?? '5175'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? 'github' : 'list',
  timeout: 60_000,
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // 优先用本机 Chrome，避免 CI 外首次下载 Chromium（npm run e2e:install）
        channel: process.env.PW_CHANNEL ?? 'chrome',
      },
    },
  ],
  webServer: {
    command: 'node scripts/e2e-webserver.mjs',
    cwd: here,
    url: `http://127.0.0.1:${webPort}`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: {
      ...process.env,
      NOVEL_WEB_PORT: apiPort,
      PLAYWRIGHT_WEB_PORT: webPort,
    },
  },
})
