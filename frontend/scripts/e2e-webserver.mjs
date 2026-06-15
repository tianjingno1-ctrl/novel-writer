/**
 * Playwright webServer：先起 API，再起 Vite，并等待两者可访问。
 */
import { spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(here, '..')
const repoRoot = path.resolve(frontendRoot, '..')

const apiPort = process.env.NOVEL_WEB_PORT ?? '18765'
const webPort = process.env.PLAYWRIGHT_WEB_PORT ?? '5175'
const apiBase = `http://127.0.0.1:${apiPort}`
const webBase = `http://127.0.0.1:${webPort}`

const children = []

async function waitFor(url, label, attempts = 90) {
  for (let i = 0; i < attempts; i += 1) {
    try {
      const res = await fetch(url)
      if (res.ok) {
        console.log(`[e2e-webserver] ${label} ready: ${url}`)
        return
      }
    } catch {
      // retry
    }
    await new Promise((r) => setTimeout(r, 1000))
  }
  throw new Error(`[e2e-webserver] timeout waiting for ${label}: ${url}`)
}

function run(label, command, args, options) {
  console.log(`[e2e-webserver] start ${label}: ${command} ${args.join(' ')}`)
  const child = spawn(command, args, {
    stdio: 'inherit',
    ...options,
  })
  child.on('error', (err) => {
    console.error(`[e2e-webserver] ${label} spawn error`, err)
    shutdown(1)
  })
  child.on('exit', (code, signal) => {
    if (signal) {
      console.error(`[e2e-webserver] ${label} killed (${signal})`)
    } else if (code !== 0) {
      console.error(`[e2e-webserver] ${label} exited ${code}`)
    }
    shutdown(code ?? 1)
  })
  children.push(child)
  return child
}

function shutdown(code = 0) {
  for (const child of children) {
    if (!child.killed) {
      child.kill()
    }
  }
  process.exit(code)
}

process.on('SIGINT', () => shutdown(0))
process.on('SIGTERM', () => shutdown(0))

const viteBin = path.join(frontendRoot, 'node_modules', 'vite', 'bin', 'vite.js')

run(
  'api',
  'python',
  ['web_app.py'],
  {
    cwd: repoRoot,
    env: {
      ...process.env,
      NOVEL_WEB_PORT: apiPort,
      NOVEL_WEB_NO_BROWSER: '1',
      NOVEL_WEB_TOKEN: '',
    },
  },
)

await waitFor(`${apiBase}/api/status`, 'api')

run(
  'vite',
  process.execPath,
  [viteBin, '--port', webPort, '--strictPort', '--host', '127.0.0.1'],
  {
    cwd: frontendRoot,
    env: {
      ...process.env,
      NOVEL_WEB_PORT: apiPort,
    },
  },
)

await waitFor(webBase, 'vite')

console.log('[e2e-webserver] both servers up; holding for Playwright…')
await new Promise(() => {})
