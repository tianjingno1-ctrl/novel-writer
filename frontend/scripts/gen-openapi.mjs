/**
 * 从运行中的 FastAPI 生成 OpenAPI 类型。
 * 用法：python web_app.py 后执行 npm run gen:api
 */
import { execSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.dirname(fileURLToPath(import.meta.url))
const out = path.join(root, '../src/api/generated/schema.ts')
const url = process.env.OPENAPI_URL ?? 'http://127.0.0.1:8765/openapi.json'

fs.mkdirSync(path.dirname(out), { recursive: true })

try {
  execSync(
    `npx openapi-typescript "${url}" -o "${out}"`,
    { stdio: 'inherit', cwd: path.join(root, '..') },
  )
  console.log('Wrote', out)
} catch {
  console.error(
    '生成失败：请先启动 python web_app.py，或设置 OPENAPI_URL',
  )
  process.exit(1)
}
