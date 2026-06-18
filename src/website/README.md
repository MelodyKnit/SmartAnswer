# 答题接入平台前端

本目录是答题接入平台的 Vue 3 + TypeScript 管理端，用于管理 API Key、导入脚本、用户钱包、兑换码、题库与大模型配置。

## 开发

```powershell
npm install
npm run dev
```

开发服务器默认运行在 `http://127.0.0.1:5173`，接口通过 `vite.config.ts` 代理到后端 `http://127.0.0.1:8765`。如需改后端地址，可设置 `VITE_API_TARGET`。

## 构建

```powershell
npm run build
```

构建产物会输出到后端静态资源目录 `src/study_qb_assistant/api/static`，由 FastAPI 服务统一托管。
