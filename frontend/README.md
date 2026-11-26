# 自营后台管理系统 · 前端

基于 Vue 3 + TypeScript + Tailwind CSS v4 + Vite 构建的企业级后台管理系统前端。

## 技术栈

| 类别 | 技术 |
| --- | --- |
| 框架 | Vue 3.5（`<script setup>` + Composition API） |
| 语言 | TypeScript 6 |
| 构建 | Vite 8 |
| 路由 | Vue Router 5 |
| 状态 | Pinia 4 |
| 样式 | Tailwind CSS v4（`@tailwindcss/vite` 插件，零配置文件） |
| 图标 | Lucide Vue Next |
| 类型检查 | vue-tsc |
| 代码规范 | ESLint + OxLint + Prettier |

## 环境要求

- **Node.js**：`^22.18.0` 或 `>=24.12.0`
- **包管理器**：pnpm（推荐）/ npm / yarn

检查 Node 版本：

```sh
node -v
```

## 快速启动

### 1. 安装依赖

```sh
# 进入前端目录
cd frontend

# 使用 pnpm（推荐）
pnpm install

# 或者使用 npm
npm install
```

### 2. 开发模式（热更新）

```sh
pnpm dev
```

默认监听 `http://localhost:5173`，启动后在浏览器打开该地址即可。

如需自定义 host / port：

```sh
# 指定 host 和 port
pnpm dev --host 127.0.0.1 --port 5173

# 允许局域网访问
pnpm dev --host 0.0.0.0
```

### 3. 生产构建

```sh
# 先做类型检查，再构建
pnpm build

# 仅构建（跳过类型检查）
pnpm build-only
```

构建产物输出到 `dist/` 目录。

### 4. 预览生产构建

```sh
pnpm preview
```

### 5. 其他脚本

```sh
# 类型检查
pnpm type-check

# 代码检查与自动修复
pnpm lint

# 代码格式化
pnpm format
```

## 功能页面

| 路由 | 页面 | 说明 |
| --- | --- | --- |
| `/login` | 登录页 | 品牌展示 + 登录表单，支持记住密码、Caps Lock 提示 |
| `/dashboard` | 仪表盘 | KPI 卡片、销售趋势图、订单列表、渠道分布、待办事项 |

### 演示账号

| 用户名 | 密码 |
| --- | --- |
| `admin` | `admin123` |

## 项目结构

```
frontend/
├── src/
│   ├── assets/           # 静态资源
│   │   └── main.css      # Tailwind 主题定义 + 全局样式 + 动画
│   ├── components/       # 公共组件
│   │   └── BrandLogo.vue # 品牌 Logo（登录页 / 仪表盘复用）
│   ├── router/
│   │   └── index.ts      # 路由配置 + 鉴权守卫
│   ├── views/
│   │   ├── LoginView.vue    # 登录页
│   │   └── DashboardView.vue # 仪表盘
│   ├── App.vue
│   └── main.ts
├── index.html
├── vite.config.ts        # 已集成 @tailwindcss/vite + vue-devtools
├── tsconfig.json
└── package.json
```

## 设计规范

- **Tailwind v4**：主题 token 直接写在 `src/assets/main.css` 的 `@theme { ... }` 块中，**不需要** `tailwind.config.js`。
- **路径别名**：`@` → `src/`（如 `import BrandLogo from '@/components/BrandLogo.vue'`）。
- **字体**：Manrope（标题展示） + Noto Sans SC（中文正文）。
- **鉴权**：登录成功后后端返回 JWT，前端将其存入 `localStorage`（勾选"记住我"）或 `sessionStorage`（键名 `self-operated-token`）；路由守卫以 token 是否存在判定登录态，未登录访问受保护路由自动跳转 `/login`；axios 请求拦截器自动携带 `Authorization: Bearer <token>`，响应拦截器收到 401 时清理登录态并跳回登录页。

## 开发小贴士

- **VS Code 插件**：[Vue - Official (Volar)](https://marketplace.visualstudio.com/items?itemName=Vue.volar)（请先禁用 Vetur，避免冲突）。
- **浏览器扩展**：[Vue.js devtools](https://chromewebstore.google.com/detail/vuejs-devtools/nhdogjmejiglipccpnnnanhbledajbpd) 方便调试组件树和 Pinia 状态。
- **Windows 用户**：如果 PowerShell 执行 `.ps1` 脚本被策略拦截，可以改用 `pnpm.cmd` 或 `npm.cmd`，或在当前会话执行 `Set-ExecutionPolicy -Scope Process Bypass`。

## 与后端联调

登录功能已对接后端真实接口；仪表盘数据目前仍为前端 mock，可按同样方式扩展。

- **接口基址**：axios 实例（`src/api/request.ts`）的 `baseURL` 默认 `http://localhost:8000/api`，可用环境变量 `VITE_API_BASE_URL` 覆盖。后端已配置 CORS 放行 `http://localhost:5173` 与 `http://127.0.0.1:5173`，开发环境可直接跨域调用，无需额外配 proxy。
- **统一响应壳**：后端返回 `{ code, message, data }`；响应拦截器在 `code !== 0` 或 HTTP 非 2xx 时抛错并透传 `message`，业务侧用 `try/catch` 展示错误即可（见 `LoginView.vue` 的 `handleSubmit`）。
- **登录接口**：`POST /api/auth/login`，body `{ "username", "password" }`，成功返回 `data.access_token` + `data.user`，封装在 `src/api/auth.ts`。
- **智能客服**：仪表盘右上角悬浮机器人入口（`src/components/CustomerServiceWidget.vue`），点击弹出对话窗口，直接调用后端 `POST /chat/stream` 的 SSE 流式接口，解析 `sources` / `token` / `error` 事件；地址可用 `VITE_CHAT_URL` 覆盖（默认 `http://localhost:8000/chat/stream`）。
- **启动后端**：默认 `http://localhost:8000`，详见 [backend/README.md](../backend/README.md)；演示账号 `admin / admin123` 由后端启动时自动 seed。
