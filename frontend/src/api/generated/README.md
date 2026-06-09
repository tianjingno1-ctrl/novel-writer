# OpenAPI 生成类型

后端启动后，在 `frontend/` 目录执行：

```bash
npx openapi-typescript http://127.0.0.1:8765/openapi.json -o src/api/generated/schema.ts
```

当前阶段使用 `src/types/api.ts` 手写最小类型；生成后可逐步替换 import。
